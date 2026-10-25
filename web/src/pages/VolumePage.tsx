import { ActionableNotification, Button, InlineLoading, InlineNotification } from '@carbon/react'
import { useMemo } from 'react'
import { Link } from 'react-router'
import CallCard from '../components/CallCard'
import TraceTree from '../components/TraceTree'
import { useCalls } from '../hooks/useCalls'
import { useCurrentProject } from '../hooks/useCurrentProject'
import { useCurrentVolume } from '../hooks/useCurrentVolume'
import { useTitle } from '../hooks/useTitle'
import { groupByTrace } from '../lib/traces'

export default function VolumePage() {
  const project = useCurrentProject() ?? ''
  const volume = useCurrentVolume() ?? ''
  useTitle(`${volume} · ${project} · AIControl`)

  const timeline = useCalls(project, volume)
  const groups = useMemo(() => groupByTrace(timeline.calls), [timeline.calls])

  return (
    <>
      {/* The conversation is named by the highlighted entry of the column; the heading is for screen readers. */}
      <h1 className="cds--visually-hidden">{volume}</h1>
      {timeline.status === 'loading' && <InlineLoading description="Loading…" />}

      {timeline.status === 'notfound' && (
        <>
          <p className="muted">
            {timeline.error ?? `Conversation “${volume}” not found in project “${project}”.`}
          </p>
          <Button as={Link} to="/" kind="tertiary">
            Back to the start
          </Button>
        </>
      )}

      {timeline.status === 'error' && (
        <ActionableNotification
          kind="error"
          inline
          lowContrast
          hideCloseButton
          title="Could not load the calls"
          subtitle={timeline.error ?? ''}
          actionButtonLabel="Retry"
          onActionButtonClick={timeline.retry}
        />
      )}

      {timeline.status === 'ready' && (
        <>
          <ol className="timeline">
            {groups.map((group) =>
              group.tree ? (
                <TraceTree key={group.traceId} group={group} />
              ) : (
                <CallCard key={group.calls[0].id} call={group.calls[0]} />
              ),
            )}
          </ol>
          {timeline.hasMore && (
            <div className="more">
              <Button kind="tertiary" disabled={timeline.loadingMore} onClick={timeline.loadMore}>
                Load more
              </Button>
            </div>
          )}
          {timeline.calls.length === 0 && (
            <p className="muted">
              No calls yet. New calls appear automatically.
            </p>
          )}
          {timeline.refreshError && (
            <InlineNotification
              kind="error"
              lowContrast
              hideCloseButton
              title="Refresh failed"
              subtitle={timeline.refreshError}
            />
          )}
        </>
      )}
    </>
  )
}
