import { Button } from '@carbon/react'
import { useCallback, useState } from 'react'
import { Link } from 'react-router'
import { api } from '../api/client'
import { useLive } from '../hooks/useLive'
import { formatShortUtc, formatUtc } from '../lib/format'

const PAGE_SIZE = 30 // conversations added by each "Load more"
const MAX = 500 // the most the API returns
const REFRESH_MS = 5000

interface Props {
  project: string
  /** The conversation being viewed (highlighted), or null. */
  current: string | null
}

/** The conversations (volumes) of a project, newest activity first: the column beside the page. */
export default function ConversationColumn({ project, current }: Props) {
  // "Load more" raises the limit and the whole list is re-requested, so the periodic refresh and
  // Load more always show one consistent list (no cursors that drift while it refreshes).
  const [limit, setLimit] = useState(PAGE_SIZE)
  const load = useCallback(
    (signal: AbortSignal) => api.conversations(project, limit, signal),
    [project, limit],
  )
  const { data, error } = useLive(load, REFRESH_MS, true)

  return (
    <aside className="conv-column" aria-label="Conversations">
      <div className="conv-column-inner">
        <h2 className="conv-column-title">Conversations</h2>
        {data === null && !error && <p className="conversations-note">Loading…</p>}
        {data === null && error && (
          <p className="conversations-note error">{`Could not load conversations: ${error.message}`}</p>
        )}
        {data?.items.length === 0 && (
          <p className="conversations-note">
            No conversations yet. They appear here as soon as an app using the SDK sends calls.
          </p>
        )}
        <ul className="conv-list">
          {data?.items.map((volume) => (
            <li key={volume.name}>
              <Link
                className="conv-item"
                to={`/projects/${encodeURIComponent(project)}/volumes/${encodeURIComponent(volume.name)}`}
                aria-current={volume.name === current ? 'page' : undefined}
                title={volume.name}
              >
                <span className="conv-name">{volume.name}</span>
                <span className="conv-meta">
                  {`${volume.call_count} call${volume.call_count === 1 ? '' : 's'}${volume.last_activity_at ? ' · ' : ''}`}
                  {volume.last_activity_at && (
                    <time dateTime={volume.last_activity_at} title={`${formatUtc(volume.last_activity_at)} UTC`}>
                      {formatShortUtc(volume.last_activity_at)}
                    </time>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
        {data?.has_more && limit < MAX && (
          <Button kind="ghost" size="sm" onClick={() => setLimit((n) => Math.min(n + PAGE_SIZE, MAX))}>
            Load more
          </Button>
        )}
        {data?.has_more && limit >= MAX && (
          <p className="conversations-note">{`Showing the latest ${limit} conversations.`}</p>
        )}
        {data && error && <p className="conversations-note error">{`Refresh failed: ${error.message}`}</p>}
      </div>
    </aside>
  )
}
