/** Calendar dates of birth and death (#123): plain `YYYY-MM-DD`, never times. */

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/

/** A real calendar date in `YYYY-MM-DD`, or undefined. */
export function parseIsoDate(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const parts = value.match(ISO_DATE)
  if (!parts) return undefined
  const [, year, month, day] = parts
  const date = new Date(Date.UTC(+year!, +month! - 1, +day!))
  date.setUTCFullYear(+year!)
  return +year! >= 1 && date.getUTCMonth() + 1 === +month! && date.getUTCDate() === +day!
    ? value
    : undefined
}

const year = (value: string) => String(+value.slice(0, 4))

/** Compact life span for cards: `1890–1962`, `b. 1948`, `d. 1931` or empty. */
export function lifeSpan(birth?: string | null, death?: string | null): string {
  if (birth && death) return `${year(birth)}–${year(death)}`
  if (birth) return `b. ${year(birth)}`
  if (death) return `d. ${year(death)}`
  return ''
}

/** A readable full date, independent of the viewer's time zone. */
export function formatLifeDate(value: string): string {
  const parsed = parseIsoDate(value)
  if (!parsed) return value
  const date = new Date(`${parsed}T00:00:00Z`)
  date.setUTCFullYear(+parsed.slice(0, 4))
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

/**
 * Editor input to a stored date (#123): empty clears, a bare year (1–9999) means
 * 1 January of that year, and a full `YYYY-MM-DD` date is kept. Anything else,
 * such as a year and month only, is rejected (undefined) and must not be sent.
 */
export function normalizeLifeDateInput(input: string): string | undefined {
  const value = input.trim()
  if (!value) return ''
  if (/^\d{1,4}$/.test(value)) {
    const year = Number(value)
    return year >= 1 ? `${String(year).padStart(4, '0')}-01-01` : undefined
  }
  return parseIsoDate(value)
}

export const LIFE_DATE_FORMAT_ERROR = 'Enter a date as YYYY-MM-DD or a year.'

/** Death must not precede birth; ISO dates compare as text. */
export function lifeDatesError(birth: string, death: string): string | undefined {
  if ((birth && !parseIsoDate(birth)) || (death && !parseIsoDate(death)))
    return LIFE_DATE_FORMAT_ERROR
  if (birth && death && death < birth) return 'Death date must not be before birth date.'
  return undefined
}
