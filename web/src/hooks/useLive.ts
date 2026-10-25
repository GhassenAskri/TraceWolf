import { useEffect, useState } from 'react'

export interface Live<T> {
  /** The last result, kept while a refresh is in flight so the screen never blanks. */
  data: T | null
  /** The last failure; cleared by the next success. */
  error: Error | null
}

/**
 * Calls `load` immediately and then every `intervalMs`, but only while `enabled`.
 *
 * - Nothing is requested while disabled (a collapsed sidebar costs the API nothing).
 * - A tick is skipped while the previous call is still running.
 * - Changing `load` (keep it stable with useCallback) or `enabled` aborts the call in flight and
 *   restarts, so a new `limit` is fetched at once.
 */
export function useLive<T>(
  load: (signal: AbortSignal) => Promise<T>,
  intervalMs: number,
  enabled: boolean,
): Live<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    let running = false

    const tick = async () => {
      if (running) return
      running = true
      try {
        const result = await load(controller.signal)
        if (!controller.signal.aborted) {
          setData(result)
          setError(null)
        }
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e : new Error(String(e)))
      } finally {
        running = false
      }
    }

    void tick()
    const timer = setInterval(tick, intervalMs)
    return () => {
      controller.abort()
      clearInterval(timer)
    }
  }, [load, intervalMs, enabled])

  return { data, error }
}
