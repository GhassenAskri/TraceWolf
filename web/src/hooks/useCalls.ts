import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { CallSummary } from '../api/types'

const PAGE_SIZE = 50
const POLL_MS = 2000

export type CallsStatus = 'loading' | 'ready' | 'notfound' | 'error'

interface State {
  /** Which project, conversation and attempt this state belongs to. */
  key: string
  status: CallsStatus
  calls: CallSummary[]
  /** More calls exist after the last one loaded ("Load more" is offered). */
  hasMore: boolean
  /** Why the first page failed (status "error" or "notfound"). */
  error: string | null
  loadingMore: boolean
  /** The last failed "Load more" or periodic refresh; cleared by the next success. */
  refreshError: string | null
}

const blank = (key: string): State => ({
  key,
  status: 'loading',
  calls: [],
  hasMore: false,
  error: null,
  loadingMore: false,
  refreshError: null,
})

/** One load of a conversation, and where the next page starts. */
interface Session {
  key: string
  controller: AbortController
  project: string
  volume: string
  cursor: string | null
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e))

/**
 * The calls of a conversation, oldest first.
 *
 * Loads the first page, then more on `loadMore()`. Once everything is loaded it asks for new
 * calls every 2 seconds (after the last cursor), so a live chat shows up by itself. Changing the
 * project or conversation starts over.
 */
export function useCalls(project: string, volume: string) {
  const [attempt, setAttempt] = useState(0)
  const key = `${project}\u0000${volume}\u0000${attempt}`
  const [stored, setStored] = useState<State>(() => blank(key))
  // A new conversation or retry shows "loading" at once, derived while rendering, so no
  // state has to be reset inside an effect.
  const state = stored.key === key ? stored : blank(key)
  const session = useRef<Session | null>(null)

  // Updates the state of one session; a result that arrives after the session ended is dropped.
  const update = useCallback((current: Session, change: (s: State) => State) => {
    if (current.controller.signal.aborted) return
    setStored((s) => (s.key === current.key ? change(s) : s))
  }, [])

  // First page; also starts over when the conversation or the attempt changes.
  useEffect(() => {
    const controller = new AbortController()
    const current: Session = { key, controller, project, volume, cursor: null }
    session.current = current

    api
      .calls(project, volume, { limit: PAGE_SIZE }, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return
        current.cursor = page.next_cursor
        setStored({ ...blank(key), status: 'ready', calls: page.items, hasMore: page.has_more })
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return
        const notFound = e instanceof ApiError && e.status === 404
        setStored({ ...blank(key), status: notFound ? 'notfound' : 'error', error: message(e) })
      })

    return () => controller.abort()
  }, [key, project, volume])

  // Everything is loaded: look for new calls every 2 seconds.
  const { status, hasMore } = state
  useEffect(() => {
    const current = session.current
    if (status !== 'ready' || hasMore || !current || current.key !== key) return
    let busy = false

    const timer = setInterval(async () => {
      if (busy) return
      busy = true
      try {
        const page = await api.calls(
          current.project,
          current.volume,
          { limit: PAGE_SIZE, cursor: current.cursor ?? undefined },
          current.controller.signal,
        )
        if (current.controller.signal.aborted) return
        current.cursor = page.next_cursor
        update(current, (s) => ({
          ...s,
          calls: page.items.length > 0 ? [...s.calls, ...page.items] : s.calls,
          hasMore: page.items.length > 0 ? page.has_more : s.hasMore,
          refreshError: null,
        }))
      } catch (e) {
        update(current, (s) => ({ ...s, refreshError: message(e) }))
      } finally {
        busy = false
      }
    }, POLL_MS)

    return () => clearInterval(timer)
  }, [status, hasMore, key, update])

  const loadMore = useCallback(async () => {
    const current = session.current
    if (!current) return
    update(current, (s) => ({ ...s, loadingMore: true }))
    try {
      const page = await api.calls(
        current.project,
        current.volume,
        { limit: PAGE_SIZE, cursor: current.cursor ?? undefined },
        current.controller.signal,
      )
      if (current.controller.signal.aborted) return
      current.cursor = page.next_cursor
      update(current, (s) => ({
        ...s,
        calls: [...s.calls, ...page.items],
        hasMore: page.has_more,
        loadingMore: false,
        refreshError: null,
      }))
    } catch (e) {
      update(current, (s) => ({ ...s, loadingMore: false, refreshError: message(e) }))
    }
  }, [update])

  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  return { ...state, loadMore, retry }
}
