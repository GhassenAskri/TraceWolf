import type { CallDetail, CallPage, ConversationPage, Project } from './types'

const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '')

/** A failed API call. `status` is 0 when the API could not be reached at all. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type Params = Record<string, string | number | undefined>

interface Options {
  params?: Params
  body?: unknown
  signal?: AbortSignal
}

async function request<T>(method: 'GET' | 'POST', path: string, options: Options = {}): Promise<T> {
  const { params = {}, body, signal } = options
  const url = new URL(API_URL + path)
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') url.searchParams.set(key, String(value))
  }

  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(url, {
      method,
      signal,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (error) {
    if (signal?.aborted) throw error // a cancelled request is not an API error
    throw new ApiError(0, `Cannot reach the API at ${API_URL}`)
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const parsed = await response.json()
      if (typeof parsed?.detail === 'string') detail = parsed.detail
      // a validation error (422) lists what is wrong with each field
      else if (Array.isArray(parsed?.detail)) {
        detail = parsed.detail.map((d: { msg?: string }) => d.msg ?? 'invalid').join('; ')
      }
    } catch {
      // not a JSON error body: keep the status text
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

const get = <T>(path: string, params: Params = {}, signal?: AbortSignal) =>
  request<T>('GET', path, { params, signal })

const projectPath = (project: string) => `/api/projects/${encodeURIComponent(project)}`

export const api = {
  /** Every project, alphabetically. */
  projects: (signal?: AbortSignal) => get<Project[]>('/api/projects', {}, signal),

  /** Create a project. Fails with status 409 if the name is taken, 422 if it is not valid. */
  createProject: (name: string, signal?: AbortSignal) =>
    request<Project>('POST', '/api/projects', { body: { name }, signal }),

  /** The `limit` most recently active conversations (volumes) of a project, newest first. */
  conversations: (project: string, limit: number, signal?: AbortSignal) =>
    get<ConversationPage>(`${projectPath(project)}/conversations`, { limit }, signal),

  /** Calls of a volume, oldest first; pass `cursor` to get the calls after a previous page. */
  calls: (
    project: string,
    volume: string,
    query: { limit?: number; cursor?: string } = {},
    signal?: AbortSignal,
  ) =>
    get<CallPage>(
      `${projectPath(project)}/volumes/${encodeURIComponent(volume)}/calls`,
      query,
      signal,
    ),

  /** One call with its full trace from S3. */
  call: (id: number, signal?: AbortSignal) => get<CallDetail>(`/api/calls/${id}`, {}, signal),
}
