/** Total counts registered pages, including partial imports and gaps. */
export function pagePosition(number?: number | null, total?: number | null) {
  return `${number ?? '–'}/${total ?? '–'}`
}

/** Spoken form of {@link pagePosition}. */
export function pagePositionLabel(number?: number | null, total?: number | null) {
  return `Page ${number ?? 'unknown'} of ${total ?? 'unknown'} registered pages`
}
