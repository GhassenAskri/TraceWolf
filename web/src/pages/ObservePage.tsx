import { InlineLoading } from '@carbon/react'
import { Outlet } from 'react-router'
import ConversationColumn from '../components/ConversationColumn'
import { useCurrentProject } from '../hooks/useCurrentProject'
import { useCurrentVolume } from '../hooks/useCurrentVolume'
import { useProjects } from '../hooks/useProjects'

/**
 * Everything under `/projects/<project>`: the observability of the project. A column with its
 * conversations sits beside the page, which shows the selected conversation (or, with none
 * selected, the project's overview).
 */
export default function ObservePage() {
  const project = useCurrentProject() ?? ''
  const current = useCurrentVolume()
  const { status, projects } = useProjects()

  // A project that is not created yet has no conversations: the page alone offers to create it.
  if (status === 'ready' && !projects.some((p) => p.slug === project)) return <Outlet />

  return (
    <div className="observe">
      {status === 'loading' ? (
        <aside className="conv-column" aria-label="Conversations">
          <div className="conv-column-inner">
            <InlineLoading description="Loading…" />
          </div>
        </aside>
      ) : (
        // `key` starts the column over (limit, data) when another project is chosen.
        <ConversationColumn key={project} project={project} current={current} />
      )}
      <div className="observe-main">
        <Outlet />
      </div>
    </div>
  )
}
