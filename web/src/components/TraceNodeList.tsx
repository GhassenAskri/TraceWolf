import { compactJson, formatDuration } from '../lib/format'
import { callTokens, type TraceGroup, type TraceNode, type TraceSummary } from '../lib/traces'
import NodeIcon, { type Tone } from './NodeIcon'

/** The key of the row for the trace itself (the rows below it use `TraceNode.key`). */
export const ROOT = 'trace'

const tokenText = (n: number | null) => (n === null ? null : `${n.toLocaleString('en-US')} tok`)
const join = (parts: (string | null)[]) => parts.filter(Boolean).join(', ')

interface RowProps {
  tone: Tone
  title: string
  subtitle: string
  selected: boolean
  onSelect: () => void
}

function Row({ tone, title, subtitle, selected, onSelect }: RowProps) {
  return (
    <button
      type="button"
      className={selected ? 'tnode tnode--selected' : 'tnode'}
      aria-current={selected ? 'true' : undefined}
      title={`${title}\n${subtitle}`}
      onClick={onSelect}
    >
      <NodeIcon tone={tone} />
      <span className="tnode-text">
        <span className="tnode-title">{title}</span>
        <span className="tnode-sub">{subtitle}</span>
      </span>
    </button>
  )
}

function nodeRow(node: TraceNode): Omit<RowProps, 'selected' | 'onSelect'> {
  if (node.kind === 'tool') {
    const args = node.tool.arguments
    return {
      tone: 'tool',
      title: node.tool.name ?? 'tool call',
      subtitle: args === null || args === undefined ? 'tool call' : compactJson(args),
    }
  }
  const { call } = node
  const duration = call.latency_ms !== null ? formatDuration(call.latency_ms) : null
  const failed = call.status === 'error'
  return {
    tone: failed ? 'error' : 'llm',
    title: call.step_name ?? 'LLM call',
    subtitle: failed
      ? join([call.error_type ?? 'failed', duration])
      : join([duration, tokenText(callTokens(call)), call.response_model ?? call.request_model]),
  }
}

interface Props {
  group: TraceGroup
  summary: TraceSummary
  nodes: TraceNode[]
  selected: string
  onSelect: (key: string) => void
}

/** The tree: the trace with its totals, then one row per call and per tool it asked for. */
export default function TraceNodeList({ group, summary, nodes, selected, onSelect }: Props) {
  const rootSubtitle = join([
    summary.durationMs !== null ? formatDuration(summary.durationMs) : null,
    tokenText(summary.tokens),
    summary.errors > 0 ? `${summary.errors} failed` : null,
  ])

  return (
    <>
      <Row
        tone="trace"
        title={group.name ?? 'Trace'}
        subtitle={rootSubtitle || `${group.calls.length} calls`}
        selected={selected === ROOT}
        onSelect={() => onSelect(ROOT)}
      />
      <ol className="tnodes">
        {nodes.map((node) => (
          <li key={node.key}>
            <Row {...nodeRow(node)} selected={selected === node.key} onSelect={() => onSelect(node.key)} />
          </li>
        ))}
      </ol>
    </>
  )
}
