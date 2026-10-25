import { Tag } from '@carbon/react'
import type { Message as MessageData } from '../api/types'
import { compactJson } from '../lib/format'

const ROLE_TAG: Record<string, 'blue' | 'cool-gray' | 'purple' | 'teal'> = {
  user: 'blue',
  assistant: 'cool-gray',
  system: 'purple',
  tool: 'teal',
}

/** One chat message: role, text, and any tool calls. Everything is rendered as text. */
export default function Message({ message }: { message: MessageData }) {
  const role = message.role ?? 'unknown'

  return (
    <div className={`msg msg--${role}`}>
      <div className="msg-role">
        <Tag type={ROLE_TAG[role] ?? 'gray'} size="sm">
          {role}
        </Tag>
        {message.tool_call_id && <code>{message.tool_call_id}</code>}
      </div>
      {message.content && <div className="msg-content">{message.content}</div>}
      {(message.tool_calls ?? []).map((call, i) => (
        <div className="msg-tool-call" key={i}>
          <Tag type="outline" size="sm">
            tool call
          </Tag>
          <code>{`${call.name}(${compactJson(call.arguments)})`}</code>
        </div>
      ))}
    </div>
  )
}
