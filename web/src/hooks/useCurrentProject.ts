import { useMatch } from 'react-router'

/**
 * The project of the current URL (`/projects/My%20Project/...` gives `My Project`), or null on
 * pages outside a project.
 */
export function useCurrentProject(): string | null {
  const match = useMatch('/projects/:project/*')
  return match?.params.project || null
}
