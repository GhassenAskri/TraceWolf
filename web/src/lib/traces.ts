import type { CallSummary, Message, ToolCall } from '../api/types'

/** The calls that share one trace id, in the order they were made. */
export interface TraceGroup {
  traceId: string
  /** The name given with `aicontrol.trace(...)`, if any call carries one. */
  name: string | null
  calls: CallSummary[]
  /**
   * Drawn as a tree. A lone call that nobody named is just a call, so it keeps its plain card:
   * apps that don't use `aicontrol.trace` / `aicontrol.step` look exactly as before.
   */
  tree: boolean
}

/**
 * Groups calls by trace id. Groups keep the order of their first call, so a live conversation
 * still reads oldest first, and a call that arrives later joins its group in place.
 */
export function groupByTrace(calls: CallSummary[]): TraceGroup[] {
  const groups = new Map<string, TraceGroup>()
  for (const call of calls) {
    let group = groups.get(call.trace_id)
    if (!group) {
      group = { traceId: call.trace_id, name: null, calls: [], tree: false }
      groups.set(call.trace_id, group)
    }
    group.calls.push(call)
    group.name ??= call.trace_name
    group.tree ||= group.calls.length > 1 || call.trace_name !== null || call.step_name !== null
  }
  return [...groups.values()]
}

export interface TraceSummary {
  /** From the first call's start to the last call's end. */
  durationMs: number | null
  /** Tokens of all the calls; null when none of them reports any. */
  tokens: number | null
  errors: number
}

export function summarizeTrace(calls: CallSummary[]): TraceSummary {
  let start = Infinity
  let end = -Infinity
  let tokens: number | null = null
  let errors = 0
  for (const call of calls) {
    const startedAt = Date.parse(call.started_at)
    const endedAt = call.ended_at ? Date.parse(call.ended_at) : startedAt + (call.latency_ms ?? 0)
    if (!Number.isNaN(startedAt)) start = Math.min(start, startedAt)
    if (!Number.isNaN(endedAt)) end = Math.max(end, endedAt)

    const used = callTokens(call)
    if (used !== null) tokens = (tokens ?? 0) + used
    if (call.status === 'error') errors += 1
  }
  return { durationMs: end >= start ? end - start : null, tokens, errors }
}

/** Tokens of one call: the reported total, else input + output; null when it reports none. */
export function callTokens(call: CallSummary): number | null {
  const t = call.tokens
  if (t.total !== null) return t.total
  return t.input !== null || t.output !== null ? (t.input ?? 0) + (t.output ?? 0) : null
}

/** A row of the trace tree below the trace itself. */
export type TraceNode =
  | { kind: 'call'; key: string; call: CallSummary }
  /** A tool the model asked for during `call`; `result` is the tool message answering it. */
  | { kind: 'tool'; key: string; call: CallSummary; tool: ToolCall; result: Message | null }

/**
 * The rows of a trace in the order things happened: each call, then the tools it asked for.
 * Tools are not spans of their own (only LLM calls are stored), so they are read from the
 * messages: the request is in the call's output, the result in a later call's input.
 */
export function traceNodes(calls: CallSummary[]): TraceNode[] {
  const nodes: TraceNode[] = []
  calls.forEach((call, i) => {
    nodes.push({ kind: 'call', key: `call-${call.id}`, call })
    const requested = call.new_messages.flatMap((m) => m.tool_calls ?? [])
    requested.forEach((tool, n) => {
      const result = tool.id ? findToolResult(calls.slice(i + 1), tool.id) : null
      nodes.push({ kind: 'tool', key: `tool-${call.id}-${n}`, call, tool, result })
    })
  })
  return nodes
}

function findToolResult(calls: CallSummary[], toolCallId: string): Message | null {
  for (const call of calls) {
    for (const message of call.new_messages) {
      if (message.role === 'tool' && message.tool_call_id === toolCallId) return message
    }
  }
  return null
}
