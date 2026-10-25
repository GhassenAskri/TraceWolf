import { Button, Layer, Tag, Tile } from '@carbon/react'
import { ChevronDown, ChevronUp } from '@carbon/icons-react'
import { useState } from 'react'
import type { CallSummary } from '../api/types'
import { formatUtc } from '../lib/format'
import FullInput from './FullInput'
import Message from './Message'

/** One call of the timeline: monitoring fields, then the messages that are new in this call. */
export default function CallCard({ call }: { call: CallSummary }) {
  const tokens = call.tokens
  const [showFull, setShowFull] = useState(false)
  const failed = call.status === 'error'

  return (
    <li className={failed ? 'call call--error' : 'call'} id={`call-${call.id}`}>
      <Tile>
        <div className="call-meta">
          <time className="call-time" dateTime={call.started_at}>
            {formatUtc(call.started_at)}
          </time>
          <span className="call-model">{call.response_model || call.request_model || 'unknown model'}</span>
          <span title="input / output tokens">
            <Tag type="outline" size="sm">{`${tokens.input ?? '?'} → ${tokens.output ?? '?'} tok`}</Tag>
          </span>
          {tokens.cached_input ? (
            <span title="cached input tokens">
              <Tag type="outline" size="sm">{`${tokens.cached_input} cached`}</Tag>
            </span>
          ) : null}
          {tokens.reasoning ? (
            <span title="reasoning tokens">
              <Tag type="outline" size="sm">{`${tokens.reasoning} reasoning`}</Tag>
            </span>
          ) : null}
          {call.latency_ms !== null && (
            <Tag type="outline" size="sm">{`${call.latency_ms} ms`}</Tag>
          )}
          {call.is_streaming && (
            <Tag type="cool-gray" size="sm">
              stream
            </Tag>
          )}
          {(call.finish_reasons ?? []).map((reason, i) => (
            <Tag type="cool-gray" size="sm" key={i}>
              {reason}
            </Tag>
          ))}
          {call.tools_offered ? (
            <span title="tools offered to the model">
              <Tag type="cool-gray" size="sm">{`${call.tools_offered} tool${call.tools_offered === 1 ? '' : 's'}`}</Tag>
            </span>
          ) : null}
          <Tag type={failed ? 'red' : call.status === 'ok' ? 'green' : 'gray'} size="sm">
            {`${call.status}${call.error_type ? `: ${call.error_type}` : ''}`}
          </Tag>
        </div>
        <Layer>
          <div className="messages">
            {call.new_messages.map((message, i) => (
              <Message key={i} message={message} />
            ))}
          </div>
          <Button
            kind="ghost"
            size="sm"
            renderIcon={showFull ? ChevronUp : ChevronDown}
            aria-expanded={showFull}
            onClick={() => setShowFull((open) => !open)}
          >
            {showFull ? 'Hide full input' : 'Show full input'}
          </Button>
          {showFull && <FullInput callId={call.id} />}
        </Layer>
      </Tile>
    </li>
  )
}
