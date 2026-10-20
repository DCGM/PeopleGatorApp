/** Short annotation timestamps; never substitute creation or verification time. */
export function annotationChangeTime(
  value: string | null | undefined,
  now = new Date(),
): string | null {
  if (!value) return null
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return null
  const elapsed = now.getTime() - date.getTime()
  if (elapsed < 0) return date.toLocaleDateString()
  if (elapsed < 60_000) return 'just now'
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)} min ago`
  if (elapsed < 86_400_000) return `${Math.floor(elapsed / 3_600_000)}h ago`
  if (elapsed < 604_800_000) return `${Math.floor(elapsed / 86_400_000)}d ago`
  return date.toLocaleDateString()
}

const pad = (value: number) => String(value).padStart(2, '0')

/**
 * Person "Last change" wording. Under 24 hours the age is relative; from exactly
 * 24 hours it is the browser-local calendar date. Clock skew up to a minute in
 * the future reads as "just now"; later future values show their date.
 */
export function lastChangeLabel(value: string | null | undefined, now = new Date()): string | null {
  if (!value) return null
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return null
  const elapsed = now.getTime() - date.getTime()
  if (elapsed >= -60_000 && elapsed < 60_000) return 'modified just now'
  if (elapsed >= 60_000 && elapsed < 3_600_000) {
    return `modified ${Math.floor(elapsed / 60_000)} min ago`
  }
  if (elapsed >= 3_600_000 && elapsed < 86_400_000) {
    const hours = Math.floor(elapsed / 3_600_000)
    return `modified ${hours} ${hours === 1 ? 'hour' : 'hours'} ago`
  }
  return `modified on ${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}
