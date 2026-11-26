import { BadgeCheck, CircleDashed, FileText, ScanFace, TextQuote } from '@lucide/vue'
import type { Component } from 'vue'
import type { EntityLinkStateCounts, VerificationState } from '@/client'
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

/** One counted state in a progress tooltip; `tone` colours its icon and bar segment. */
export type ProgressRow = {
  key: string
  label: string
  icon: Component
  count: number
  tone: 'verified' | 'manual' | 'automatic' | 'rest'
}
/** What a progress ring measures and how its total splits up. */
export type ProgressBreakdown = {
  title: string
  icon: Component
  total: number
  rows: ProgressRow[]
}

/** Registered pages of a document: verified, then the remainder. */
export function pageProgressBreakdown(verified: number, total: number): ProgressBreakdown {
  return {
    title: 'Pages',
    icon: FileText,
    total,
    rows: [
      {
        key: 'verified',
        label: verificationVisuals.verified.label,
        icon: verificationVisuals.verified.icon,
        count: verified,
        tone: 'verified',
      },
      {
        key: 'not_verified',
        label: verificationVisuals.not_verified.label,
        icon: verificationVisuals.not_verified.icon,
        count: Math.max(0, total - verified),
        tone: 'rest',
      },
    ],
  }
}

/** A document's faces or mentions split by link state. */
export function linkProgressBreakdown(
  kind: 'faces' | 'mentions',
  counts?: EntityLinkStateCounts,
): ProgressBreakdown {
  return {
    title: kind === 'faces' ? 'Faces' : 'Mentions',
    icon: kind === 'faces' ? ScanFace : TextQuote,
    total: counts?.total ?? 0,
    rows: (['verified', 'manual', 'automatic', 'unassigned'] as const).map((state) => ({
      key: state,
      label: linkStateVisuals[state].label,
      icon: linkStateVisuals[state].icon,
      count: counts?.[state] ?? 0,
      tone: state === 'unassigned' ? 'rest' : state,
    })),
  }
}
