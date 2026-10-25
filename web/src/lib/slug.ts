// The same rules as the API (api/app/slugs.py), so the dialog can show the slug a name will get
// before the project exists. The API stays the authority: it generates the real slug (and a
// request that races another one may get the next number).

export const MAX_SLUG_LENGTH = 64
const FALLBACK = 'project' // for a name without any letter or digit

/** `Support Desk` → `support-desk`; accents are folded (`Café` → `cafe`). */
export function slugify(name: string): string {
  // Keep only the ASCII characters (accents were split off by NFKD, so `é` leaves its `e`).
  const ascii = Array.from(name.normalize('NFKD'))
    .filter((char) => char.charCodeAt(0) < 128)
    .join('')
  const slug = ascii
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_SLUG_LENGTH)
    .replace(/-+$/g, '')
  return slug || FALLBACK
}

/** `base` if it is free, else `base-2`, `base-3`… (the smallest number that is free). */
export function nextFreeSlug(base: string, taken: ReadonlySet<string>): string {
  if (!taken.has(base)) return base
  for (let number = 2; ; number++) {
    const suffix = `-${number}`
    const candidate = base.slice(0, MAX_SLUG_LENGTH - suffix.length).replace(/-+$/g, '') + suffix
    if (!taken.has(candidate)) return candidate
  }
}
