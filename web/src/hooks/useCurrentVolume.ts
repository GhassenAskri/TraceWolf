import { useMatch } from 'react-router'

/**
 * The conversation (volume) shown by the current URL, or null on other pages.
 * `/projects/p/volumes/team%2Fsupport` and `/projects/p/volumes/team/support` both give
 * `team/support`.
 */
export function useCurrentVolume(): string | null {
  const match = useMatch('/projects/:project/volumes/*')
  return match?.params['*'] || null
}
