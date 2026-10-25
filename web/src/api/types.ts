// Response shapes of the AIControl JSON API (mirrors api/app/schemas.py).

export interface Project {
  /** A label for people. */
  name: string
  /** The identifier: what the SDK, the addresses and the API use. Generated from the name, never changes. */
  slug: string
  volume_count: number
  call_count: number
  created_at: string
  last_activity_at: string | null
}

export interface Volume {
  name: string
  call_count: number
  created_at: string
  last_activity_at: string | null
}

export interface ConversationPage {
  items: Volume[]
  has_more: boolean
}

export interface Tokens {
  input: number | null
  output: number | null
  total: number | null
  cached_input: number | null
  reasoning: number | null
}

export interface ToolCall {
  id: string | null
  name: string | null
  arguments: unknown
}

/** A message as stored by the API: `{role, parts}` normalised to text content and tool calls. */
export interface Message {
  role: string | null
  content: string | null
  tool_calls?: ToolCall[]
  tool_call_id?: string
  finish_reason?: string
  parts?: unknown[]
}

export interface CallSummary {
  id: number
  project: string
  volume: string
  trace_id: string
  span_id: string
  /** Set with `aicontrol.trace(...)`: the name of the piece of work the call belongs to. */
  trace_name: string | null
  /** Set with `aicontrol.step(...)`: what this call does within its trace. */
  step_name: string | null
  operation: string | null
  provider: string | null
  request_model: string | null
  response_model: string | null
  api_base: string | null
  response_id: string | null
  started_at: string
  ended_at: string | null
  latency_ms: number | null
  is_streaming: boolean | null
  tokens: Tokens
  status: string
  error_type: string | null
  finish_reasons: string[] | null
  temperature: number | null
  max_tokens: number | null
  top_p: number | null
  tools_offered: number | null
  tool_calls_made: string[] | null
  new_messages: Message[]
  trace_size_bytes: number | null
}

export interface CallPage {
  project: string
  volume: string
  items: CallSummary[]
  next_cursor: string | null
  has_more: boolean
}

/** The full trace document stored in S3 for one call. */
export interface Trace {
  input_messages: Message[]
  output_messages: Message[]
  tool_definitions: unknown
  raw_attributes: Record<string, unknown>
  status_message: string | null
}

export interface CallDetail extends CallSummary {
  trace: Trace | null
  /** Why `trace` is null (the object is missing from storage). */
  trace_error: string | null
  /** Where the full trace lives in S3. */
  trace_key: string
}
