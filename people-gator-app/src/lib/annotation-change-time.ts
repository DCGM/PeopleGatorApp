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
