/** Total counts registered pages, including partial imports and gaps. */
export function pagePosition(number?: number | null, total?: number | null) {
  return `${number ?? '–'}/${total ?? '–'}`
}
