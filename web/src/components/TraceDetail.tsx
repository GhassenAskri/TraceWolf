import {
  Button,
  CodeSnippet,
  InlineLoading,
  InlineNotification,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
} from '@carbon/react'
import { ChevronDown, ChevronUp } from '@carbon/icons-react'
import { Fragment, useState, type ReactNode } from 'react'
import type { CallSummary } from '../api/types'
import { useCallDetail } from '../hooks/useCallDetail'
import { formatDuration, formatUtc, prettyJson } from '../lib/format'
import type { TraceGroup, TraceNode, TraceSummary } from '../lib/traces'
import FullInput from './FullInput'
import Message from './Message'
import NodeIcon, { type Tone } from './NodeIcon'

/** Which tab is open; kept by the panel so it stays the same while you pick other rows. */
interface TabState {
  tab: number
  onTab: (tab: number) => void
}

const count = (n: number | null) => (n === null ? null : n.toLocaleString('en-US'))

function Header({ tone, title }: { tone: Tone; title: string }) {
  return (
    <div className="detail-head">
      <NodeIcon tone={tone} />
      <h2 className="detail-title">{title}</h2>
    </div>
  )
}

/** Messages / Details / Raw. A tab's content is only built while it is open (Raw fetches). */
function Tabbed({ tab, onTab, messages, details, raw }: TabState & Record<'messages' | 'details' | 'raw', ReactNode>) {
  return (
    <Tabs selectedIndex={tab} onChange={({ selectedIndex }) => onTab(selectedIndex)}>
      <TabList aria-label="Details of the selected row">
        <Tab>Messages</Tab>
        <Tab>Details</Tab>
        <Tab>Raw</Tab>
      </TabList>
      <TabPanels>
        <TabPanel>{tab === 0 && messages}</TabPanel>
        <TabPanel>{tab === 1 && details}</TabPanel>
        <TabPanel>{tab === 2 && raw}</TabPanel>
      </TabPanels>
    </Tabs>
  )
}

type Field = [label: string, value: ReactNode]

/** Label / value pairs; the ones without a value are left out. */
function Fields({ items }: { items: Field[] }) {
  return (
    <dl className="fields">
      {items
        .filter(([, value]) => value !== null && value !== undefined && value !== '')
        .map(([label, value]) => (
          <Fragment key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </Fragment>
        ))}
    </dl>
  )
}

function Json({ value }: { value: unknown }) {
  return (
    <CodeSnippet type="multi" feedback="Copied">
      {prettyJson(value)}
    </CodeSnippet>
  )
}

function RawCall({ callId }: { callId: number }) {
  const state = useCallDetail(callId)
  if (state.status === 'loading') return <InlineLoading description="Loading…" />
  if (state.status === 'error') {
    return (
      <InlineNotification
        kind="error"
        lowContrast
        hideCloseButton
        title="Could not load the call"
        subtitle={state.message}
      />
    )
  }
  return <Json value={state.call} />
}

// --- The trace itself -------------------------------------------------------------------------

interface OverviewProps extends TabState {
  group: TraceGroup
  summary: TraceSummary
}

/** The whole trace: every call's new messages in order, its totals, and the calls as JSON. */
export function TraceOverview({ group, summary, tab, onTab }: OverviewProps) {
  const { calls } = group
  return (
    <>
      <Header tone="trace" title={group.name ?? 'Trace'} />
      <Tabbed
        tab={tab}
        onTab={onTab}
        messages={calls.map((call) => (
          <section className="detail-section" key={call.id}>
            <h3 className="section-label">{call.step_name ?? 'LLM call'}</h3>
            <div className="messages">
              {call.new_messages.map((message, i) => (
                <Message key={i} message={message} />
              ))}
            </div>
          </section>
        ))}
        details={
          <Fields
            items={[
              ['Name', group.name],
              ['Trace id', <code key="id">{group.traceId}</code>],
              ['Project', calls[0]?.project],
              ['Started', calls[0] ? `${formatUtc(calls[0].started_at)} UTC` : null],
              ['Duration', summary.durationMs !== null ? formatDuration(summary.durationMs) : null],
              ['Calls', calls.length],
              ['Tokens', count(summary.tokens)],
              ['Failed calls', summary.errors > 0 ? summary.errors : null],
            ]}
          />
        }
        raw={<Json value={calls} />}
      />
    </>
  )
}

// --- One LLM call -----------------------------------------------------------------------------

function CallMessages({ call }: { call: CallSummary }) {
  const [showFull, setShowFull] = useState(false)
  return (
    <>
      {call.status === 'error' && (
        <InlineNotification
          kind="error"
          lowContrast
          hideCloseButton
          title={call.error_type ?? 'The call failed'}
        />
      )}
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
    </>
  )
}

function callFields(call: CallSummary): Field[] {
  const { tokens } = call
  const model = call.response_model ?? call.request_model
  return [
    ['Project', call.project],
    ['Step', call.step_name],
    ['Trace', call.trace_name],
    ['Span id', <code key="span">{call.span_id}</code>],
    ['Trace id', <code key="trace">{call.trace_id}</code>],
    ['Status', call.error_type ? `${call.status}: ${call.error_type}` : call.status],
    ['Model', model],
    ['Requested model', call.request_model !== model ? call.request_model : null],
    ['Provider', call.provider],
    ['Operation', call.operation],
    ['Started', `${formatUtc(call.started_at)} UTC`],
    ['Duration', call.latency_ms !== null ? formatDuration(call.latency_ms) : null],
    ['Streaming', call.is_streaming === null ? null : call.is_streaming ? 'yes' : 'no'],
    ['Input tokens', count(tokens.input)],
    ['Output tokens', count(tokens.output)],
    ['Total tokens', count(tokens.total)],
    ['Cached input tokens', count(tokens.cached_input)],
    ['Reasoning tokens', count(tokens.reasoning)],
    ['Finish reasons', call.finish_reasons?.join(', ')],
    ['Temperature', call.temperature],
    ['Max tokens', call.max_tokens],
    ['Top p', call.top_p],
    ['Tools offered', call.tools_offered],
    ['Tool calls made', call.tool_calls_made?.join(', ')],
    ['Response id', call.response_id],
    ['API base', call.api_base],
  ]
}

export function CallPane({ call, tab, onTab }: TabState & { call: CallSummary }) {
  return (
    <>
      <Header tone={call.status === 'error' ? 'error' : 'llm'} title={call.step_name ?? 'LLM call'} />
      <Tabbed
        tab={tab}
        onTab={onTab}
        messages={<CallMessages key={call.id} call={call} />}
        details={<Fields items={callFields(call)} />}
        raw={<RawCall callId={call.id} />}
      />
    </>
  )
}

// --- One tool call ----------------------------------------------------------------------------

export function ToolPane({ node }: { node: Extract<TraceNode, { kind: 'tool' }> }) {
  const { tool, result, call } = node
  return (
    <>
      <Header tone="tool" title={tool.name ?? 'tool call'} />
      <Fields
        items={[
          ['Requested by', call.step_name ?? 'LLM call'],
          ['Tool call id', tool.id ? <code key="id">{tool.id}</code> : null],
        ]}
      />
      <section className="detail-section">
        <h3 className="section-label">Parameters</h3>
        <Json value={tool.arguments ?? {}} />
      </section>
      <section className="detail-section">
        <h3 className="section-label">Result</h3>
        {result ? (
          <div className="messages">
            <Message message={result} />
          </div>
        ) : (
          <p className="muted">No result for this tool call was found in the trace.</p>
        )}
      </section>
    </>
  )
}
