import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { api } from '../api/client'
import type { Project } from '../api/types'
import { ProjectsContext, type ProjectsApi } from '../hooks/useProjects'
import { useCurrentProject } from '../hooks/useCurrentProject'
import { rememberProject } from '../lib/lastProject'
import NewProjectModal from './NewProjectModal'

interface Loaded {
  status: ProjectsApi['status']
  projects: Project[]
  error: string | null
}

/** Loads the projects once for the whole app and hosts the "New project" dialog. */
export default function ProjectsProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const current = useCurrentProject()
  const [state, setState] = useState<Loaded>({ status: 'loading', projects: [], error: null })
  const [attempt, setAttempt] = useState(0)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    api
      .projects(controller.signal)
      .then((projects) => {
        if (!controller.signal.aborted) setState({ status: 'ready', projects, error: null })
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return
        const error = e instanceof Error ? e.message : String(e)
        setState((s) => ({ ...s, status: 'error', error }))
      })
    return () => controller.abort()
  }, [attempt])

  // The last project that exists and was opened is where "/" takes you next time.
  useEffect(() => {
    if (current && state.projects.some((p) => p.slug === current)) rememberProject(current)
  }, [current, state.projects])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  const createProject = useCallback(async (name: string) => {
    const project = await api.createProject(name)
    setAttempt((n) => n + 1)
    return project
  }, [])

  const value = useMemo<ProjectsApi>(
    () => ({ ...state, reload, openNewProject: () => setCreating(true), createProject }),
    [state, reload, createProject],
  )

  return (
    <ProjectsContext.Provider value={value}>
      {children}
      {creating && (
        <NewProjectModal
          onClose={() => setCreating(false)}
          create={createProject}
          onCreated={(project) => {
            setCreating(false)
            navigate(`/projects/${encodeURIComponent(project.slug)}`)
          }}
        />
      )}
    </ProjectsContext.Provider>
  )
}
