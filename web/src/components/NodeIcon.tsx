import { Chat, ErrorFilled, Flow, Tools } from '@carbon/icons-react'

export type Tone = 'trace' | 'llm' | 'tool' | 'error'

const ICONS = { trace: Flow, llm: Chat, tool: Tools, error: ErrorFilled }

/** The coloured square in front of a trace, an LLM call, a tool call or a failed call. */
export default function NodeIcon({ tone }: { tone: Tone }) {
  const Icon = ICONS[tone]
  return (
    <span className={`tnode-icon tnode-icon--${tone}`} aria-hidden="true">
      <Icon size={16} />
    </span>
  )
}
