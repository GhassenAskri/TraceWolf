import { useMemo, useState } from 'react'
import { summarizeTrace, traceNodes, type TraceGroup } from '../lib/traces'
import { CallPane, ToolPane, TraceOverview } from './TraceDetail'
import TraceNodeList, { ROOT } from './TraceNodeList'

/**
 * One trace as a tree with a detail pane: the rows of its calls (and the tools they asked for)
 * on the left, and on the right whatever is selected: the whole trace, a call, or a tool call.
 */
export default function TraceTree({ group }: { group: TraceGroup }) {
  const nodes = useMemo(() => traceNodes(group.calls), [group.calls])
  const summary = useMemo(() => summarizeTrace(group.calls), [group.calls])
  const [selected, setSelected] = useState(ROOT)
  const [tab, setTab] = useState(0)
  const node = nodes.find((n) => n.key === selected)

  return (
    <li className="trace" id={`trace-${group.traceId}`}>
      <div className="trace-panel">
        <nav className="trace-nav" aria-label={`${group.name ?? 'Trace'}: calls`}>
          <TraceNodeList
            group={group}
            summary={summary}
            nodes={nodes}
            selected={node ? node.key : ROOT}
            onSelect={setSelected}
          />
        </nav>
        <div className="trace-detail">
          {node?.kind === 'call' && <CallPane call={node.call} tab={tab} onTab={setTab} />}
          {node?.kind === 'tool' && <ToolPane node={node} />}
          {!node && <TraceOverview group={group} summary={summary} tab={tab} onTab={setTab} />}
        </div>
      </div>
    </li>
  )
}
