// All times are shown in UTC, like the rest of AIControl.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const pad = (n: number) => String(n).padStart(2, '0')

function parse(iso: string | null): Date | null {
  if (!iso) return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date
}

/** `2026-10-04 10:35:00` */
export function formatUtc(iso: string | null): string {
  const d = parse(iso)
  if (!d) return ''
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`
  )
}

/** `Oct 4, 10:35`: short enough for the sidebar (the full time goes in a tooltip). */
export function formatShortUtc(iso: string | null): string {
  const d = parse(iso)
  if (!d) return ''
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
}

/** JSON on one line with a space after `:` and `,` (`{"city": "Paris"}`), easier to read in a chat. */
export function compactJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(compactJson).join(', ')}]`
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value).map(([k, v]) => `${JSON.stringify(k)}: ${compactJson(v)}`)
    return `{${entries.join(', ')}}`
  }
  return JSON.stringify(value) ?? 'null'
}

/** Indented JSON for the "All attributes" style panels. */
export function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? 'null'
}

/** `4bf92f35…`: the start of a trace or span id (the full id goes in a tooltip). */
export function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id
}

/** `850 ms`, `1.2 s`, `2 min 5 s` */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  const seconds = Math.round(ms / 1000)
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`
}
