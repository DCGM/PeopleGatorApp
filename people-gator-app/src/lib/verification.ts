import { BadgeCheck, CircleDashed } from '@lucide/vue'
import type { VerificationState } from '@/client'
import { linkStateVisuals } from '@/lib/entity-links'

/** Page/document review state (#149), coloured like the verified link-state label. */
export const verificationVisuals: Record<
  VerificationState,
  { icon: typeof BadgeCheck; label: string; classes: string }
> = {
  verified: { icon: BadgeCheck, label: 'Verified', classes: linkStateVisuals.verified.classes },
  not_verified: {
    icon: CircleDashed,
    label: 'Not verified',
    classes: linkStateVisuals.unassigned.classes,
  },
}

/** Share of verified registered pages, 0–1; unknown or empty documents count as 0. */
export function verificationProgress(verified?: number | null, total?: number | null) {
  return total ? Math.min(1, Math.max(0, (verified ?? 0) / total)) : 0
}

/** Whole verified percentage, rounded down so only complete documents read 100%. */
export function verifiedPercentLabel(verified?: number | null, total?: number | null) {
  return verified == null || !total
    ? '—'
    : `${Math.floor(verificationProgress(verified, total) * 100)}%`
}
