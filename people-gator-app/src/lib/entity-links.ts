import { Bot, Hand, BadgeCheck, UserRoundX } from '@lucide/vue'
import type { EntityLinkState } from '@/client'

export const linkStates: EntityLinkState[] = ['automatic', 'manual', 'verified']
export const linkStateVisuals = {
  automatic: {
    icon: Bot,
    label: 'Automatic',
    accessible: 'Automatically linked',
    classes: 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200',
  },
  manual: {
    icon: Hand,
    label: 'Manual',
    accessible: 'Manually linked',
    classes: 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200',
  },
  verified: {
    icon: BadgeCheck,
    label: 'Verified',
    accessible: 'Verified link',
    classes: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  },
  unassigned: {
    icon: UserRoundX,
    label: 'Unassigned',
    accessible: 'Unassigned',
    classes: 'bg-muted text-muted-foreground',
  },
}
export type LinkMetadata = {
  linkState?: EntityLinkState | null
  verifiedBy?: string | null
  verifiedAt?: string | null
}
export function linkMetadata(record: {
  entity_link_state?: EntityLinkState | null
  entity_link_verified_by_user_id?: string | null
  entity_link_verified_at?: string | null
}): LinkMetadata {
  return {
    linkState: record.entity_link_state ?? null,
    verifiedBy: record.entity_link_verified_by_user_id ?? null,
    verifiedAt: record.entity_link_verified_at ?? null,
  }
}
export function linkTooltip(link: LinkMetadata) {
  if (link.linkState === 'verified' && link.verifiedBy && link.verifiedAt)
    return `Verified by ${link.verifiedBy} · ${new Date(link.verifiedAt).toLocaleString()} (UTC: ${link.verifiedAt})`
  return linkStateVisuals[link.linkState ?? 'unassigned'].accessible
}
export function parseLinkStates(value: unknown): EntityLinkState[] {
  const values = Array.isArray(value) ? value : [value]
  return linkStates.filter((state) => values.includes(state))
}
