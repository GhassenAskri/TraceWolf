import { ActionableNotification, Button, ClickableTile, InlineLoading } from '@carbon/react'
import { Add } from '@carbon/icons-react'
import { Navigate, useNavigate } from 'react-router'
import { useProjects } from '../hooks/useProjects'
import { useTitle } from '../hooks/useTitle'
import { formatUtc } from '../lib/format'
import { readLastProject } from '../lib/lastProject'

export default function Landing() {
  useTitle('AIControl')
  const { status, projects, error, reload, openNewProject } = useProjects()
  const navigate = useNavigate()

  if (status === 'loading') return <InlineLoading description="Loading…" />
  if (status === 'error' && projects.length === 0) {
    return (
      <ActionableNotification
        kind="error"
        inline
        lowContrast
        hideCloseButton
        title="Could not load the projects"
        subtitle={error ?? ''}
        actionButtonLabel="Retry"
        onActionButtonClick={reload}
      />
    )
  }

  // Back to where you were: the last project that was opened and still exists.
  const last = readLastProject()
  if (last !== null && projects.some((p) => p.slug === last)) {
    return <Navigate replace to={`/projects/${encodeURIComponent(last)}`} />
  }

  if (projects.length === 0) {
    return (
      <>
        <h1 className="page-title">Create your first project</h1>
        <p className="muted">
          Calls are grouped by project. Create one here: its slug, generated from the name, is what
          your code passes to the SDK, and the dialog gives you the code to copy. Calls for a project
          that does not exist are rejected.
        </p>
        <Button renderIcon={Add} onClick={openNewProject}>
          New project
        </Button>
      </>
    )
  }

  return (
    <>
      <h1 className="page-title">Choose a project</h1>
      <div className="project-list">
        {projects.map((project) => {
          const path = `/projects/${encodeURIComponent(project.slug)}`
          return (
            <ClickableTile
              key={project.slug}
              href={path}
              onClick={(event) => {
                event.preventDefault()
                navigate(path)
              }}
            >
              <span className="project-name">{project.name}</span>
              <span className="project-meta">
                {`${project.slug} · ${project.volume_count} conversation${project.volume_count === 1 ? '' : 's'} · ${project.call_count} call${project.call_count === 1 ? '' : 's'}`}
                {project.last_activity_at ? ` · last ${formatUtc(project.last_activity_at)} UTC` : ''}
              </span>
            </ClickableTile>
          )
        })}
      </div>
      <Button kind="tertiary" renderIcon={Add} onClick={openNewProject}>
        New project
      </Button>
    </>
  )
}
