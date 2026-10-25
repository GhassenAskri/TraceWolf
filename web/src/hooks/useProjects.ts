import { createContext, useContext } from 'react'
import type { Project } from '../api/types'

export interface ProjectsApi {
  status: 'loading' | 'ready' | 'error'
  projects: Project[]
  /** Why the list could not be loaded (status "error"). */
  error: string | null
  reload: () => void
  /** Opens the "New project" dialog. */
  openNewProject: () => void
  /** Creates a project, refreshes the list and resolves with it. Rejects with an `ApiError`. */
  createProject: (name: string) => Promise<Project>
}

export const ProjectsContext = createContext<ProjectsApi | null>(null)

/** The projects, shared by the sidebar and the pages (see `ProjectsProvider`). */
export function useProjects(): ProjectsApi {
  const value = useContext(ProjectsContext)
  if (value === null) throw new Error('useProjects must be used inside <ProjectsProvider>')
  return value
}
