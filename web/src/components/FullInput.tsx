import { Accordion, AccordionItem, CodeSnippet, InlineLoading, InlineNotification } from '@carbon/react'
import { useCallDetail } from '../hooks/useCallDetail'
import { prettyJson } from '../lib/format'
import Message from './Message'

/** The whole input sent to the model for one call, plus its output, from the full trace in S3. */
export default function FullInput({ callId }: { callId: number }) {
  const state = useCallDetail(callId)

  if (state.status === 'loading') return <InlineLoading description="Loading…" />
  if (state.status === 'error') {
    return (
      <InlineNotification
        kind="error"
        lowContrast
        hideCloseButton
        title="Could not load the full input"
        subtitle={state.message}
      />
    )
  }

  const { call } = state
  const { trace } = call
  if (!trace) {
    return (
      <InlineNotification
        kind="error"
        lowContrast
        hideCloseButton
        title="The full trace is not available"
        subtitle={call.trace_error ?? ''}
      />
    )
  }

  const input = trace.input_messages ?? []
  const output = trace.output_messages ?? []
  const tools = Array.isArray(trace.tool_definitions) ? trace.tool_definitions : []

  return (
    <section className="full-trace">
      <h3 className="section-label">{`Input (${input.length} messages)`}</h3>
      <div className="messages">
        {input.map((message, i) => (
          <Message key={i} message={message} />
        ))}
      </div>
      <h3 className="section-label">Output</h3>
      {output.length > 0 ? (
        <div className="messages">
          {output.map((message, i) => (
            <Message key={i} message={message} />
          ))}
        </div>
      ) : (
        <p className="muted">{`No output${trace.status_message ? `: ${trace.status_message}` : ''}`}</p>
      )}
      <Accordion>
        {tools.length > 0 && (
          <AccordionItem title={`Tool definitions (${tools.length})`}>
            <CodeSnippet type="multi" feedback="Copied">
              {prettyJson(tools)}
            </CodeSnippet>
          </AccordionItem>
        )}
        <AccordionItem title="All attributes">
          <CodeSnippet type="multi" feedback="Copied">
            {prettyJson(trace.raw_attributes)}
          </CodeSnippet>
        </AccordionItem>
      </Accordion>
      <p className="trace-key">
        S3: <code>{call.trace_key}</code>
      </p>
    </section>
  )
}
