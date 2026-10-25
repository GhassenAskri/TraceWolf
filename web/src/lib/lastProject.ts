const KEY = 'aicontrol.lastProject'

// localStorage can be unavailable or throw (private windows, blocked site data): the app must
// work without it, so every access is guarded.

/** The project the user last had open in this browser, if it was remembered. */
export function readLastProject(): string | null {
  try {
    return window.localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function rememberProject(name: string): void {
  try {
    window.localStorage.setItem(KEY, name)
  } catch {
    // not remembered: the user just picks again next time
  }
}
