import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { CallDetail } from '../api/types'

export type CallDetailState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; call: CallDetail }

/** One call with its full trace from S3. Choosing another call starts loading again at once. */
export function useCallDetail(callId: number): CallDetailState {
  const [loaded, setLoaded] = useState<{ callId: number; state: CallDetailState } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const finish = (state: CallDetailState) => {
      if (!controller.signal.aborted) setLoaded({ callId, state })
    }
    api
      .call(callId, controller.signal)
      .then((call) => finish({ status: 'ready', call }))
      .catch((e: unknown) =>
        finish({ status: 'error', message: e instanceof Error ? e.message : String(e) }),
      )
    return () => controller.abort()
  }, [callId])

  return loaded?.callId === callId ? loaded.state : { status: 'loading' }
}
