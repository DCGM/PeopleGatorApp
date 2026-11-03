/** Append an inclusive range in display order, retaining existing insertion order. */
export function addSelectionRange(
  selected: ReadonlySet<string>,
  ids: string[],
  anchor: string | null,
  id: string,
): Set<string> | null {
  const start = ids.indexOf(anchor ?? '')
  const end = ids.indexOf(id)
  if (start < 0 || end < 0) return null
  return new Set([...selected, ...ids.slice(Math.min(start, end), Math.max(start, end) + 1)])
}
