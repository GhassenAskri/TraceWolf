import { ActionableNotification, Button, InlineLoading, InlineNotification } from '@carbon/react'
import { Add } from '@carbon/icons-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useCurrentProject } from '../hooks/useCurrentProject'
import { useProjects } from '../hooks/useProjects'
import { useTitle } from '../hooks/useTitle'
import { formatUtc } from '../lib/format'
import { projectNameProblem } from '../lib/projectName'

/**
 * The home of one project: its slug (what the code passes to the SDK), how much it holds and how
 * to send calls to it. When the address names a slug that does not exist (for example the one an
 * SDK complained about) it offers to create the project.
 */
export default function ProjectPage() {
  const slug = useCurrentProject() ?? ''
  const { status, projects, error, reload, createProject } = useProjects()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const project = projects.find((p) => p.slug === slug)
  useTitle(`${project?.name ?? slug} · AIControl`)

  if (status === 'loading') return <InlineLoading description="Loading…" />
  if (status === 'error' && !project) {
    return (
      <ActionableNotification
        kind="error"
        inline
        lowContrast
        hideCloseButton
        title="Could not load the project"
        subtitle={error ?? ''}
        actionButtonLabel="Retry"
        onActionButtonClick={reload}
      />
    )
  }

  if (!project) {
    const create = async () => {
      setCreating(true)
      setCreateError(null)
      try {
        // The slug of a project is generated from its name: a name equal to the slug gives that slug.
        const created = await createProject(slug)
        navigate(`/projects/${encodeURIComponent(created.slug)}`, { replace: true })
      } catch (e) {
        // "already exists" means another tab created it first: the refreshed list shows it
        setCreateError(e instanceof Error ? e.message : String(e))
        reload()
      } finally {
        setCreating(false)
      }
    }
    return (
      <>
        <h1 className="page-title">{slug}</h1>
        <p className="muted">{`No project has the slug “${slug}” yet. Calls sent to it are rejected until the project is created.`}</p>
        {createError && (
          <InlineNotification kind="error" lowContrast hideCloseButton title={createError} />
        )}
        <Button
          renderIcon={Add}
          disabled={creating || projectNameProblem(slug) !== null}
          onClick={create}
        >
          {`Create “${slug}”`}
        </Button>{' '}
        <Button as={Link} to="/" kind="tertiary">
          Back to the start
        </Button>
      </>
    )
  }

  return (
    <>
      <h1 className="page-title">{project.name}</h1>
      <p className="muted">
        Slug: <code>{project.slug}</code>. Your code passes it to the SDK (<code>aicontrol.init(project=…)</code>);
        the name above is only a label.
      </p>
      <p className="muted">
        {`${project.volume_count} conversation${project.volume_count === 1 ? '' : 's'} · ${project.call_count} call${project.call_count === 1 ? '' : 's'}`}
        {project.last_activity_at ? ` · last activity ${formatUtc(project.last_activity_at)} UTC` : ''}
      </p>
      <p className="muted">Pick a conversation in the list beside this page to see its calls.</p>
    </>
  )
}
