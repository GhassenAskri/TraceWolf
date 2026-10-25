/** The same rules as the API: trimmed, 1-255 characters. The name is a label (the slug is generated from it). */
export function projectNameProblem(name: string): string | null {
  const trimmed = name.trim()
  if (trimmed === '') return 'Enter a name.'
  if (trimmed.length > 255) return 'Use at most 255 characters.'
  return null
}
