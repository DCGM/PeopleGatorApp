import { Bot, Hand, BadgeCheck, UserRoundX } from '@lucide/vue'
import type { EntityLinkState } from '@/client'
import type { FaceListParams } from '@/query/faces'

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
/**
 * Text mentions use their link state's badge hue for text and underline, and
 * the same hue in overview marks, instead of an inline state icon.
 */
export const mentionStateClasses = {
  automatic: 'text-sky-700 decoration-sky-500 dark:text-sky-300 dark:decoration-sky-400',
  manual: 'text-amber-700 decoration-amber-500 dark:text-amber-300 dark:decoration-amber-400',
  verified:
    'text-emerald-700 decoration-emerald-500 dark:text-emerald-300 dark:decoration-emerald-400',
  unassigned: 'text-muted-foreground decoration-dashed decoration-muted-foreground',
}
export const mentionStateFillClasses = {
  automatic: 'fill-sky-500',
  manual: 'fill-amber-500',
  verified: 'fill-emerald-500',
  unassigned: 'fill-muted-foreground',
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

/** A link state, or no link at all. An empty selection means every annotation. */
export type AnnotationState = EntityLinkState | 'unassigned'
export const annotationStates: readonly AnnotationState[] = [...linkStates, 'unassigned']
export function parseAnnotationStates(value: unknown): AnnotationState[] {
  const values = Array.isArray(value) ? value : [value]
  return annotationStates.filter((state) => values.includes(state))
}

/** An unlinked annotation, or a link without a recorded state, counts as unassigned. */
export function annotationState(record: {
  entity_id?: string | null
  entity_link_state?: EntityLinkState | null
}): AnnotationState {
  return record.entity_id ? (record.entity_link_state ?? 'unassigned') : 'unassigned'
}

export type FaceStateFilter = Pick<
  FaceListParams,
  'filter.entity_link_state' | 'filter.is_assigned'
>
/**
 * Face list filters for the chosen states. The API cannot combine link states
 * with unassigned faces in one request, so a mixed selection is the union of
 * two: the linked faces, then the unassigned ones.
 */
export function faceStateFilters(states: readonly AnnotationState[]): FaceStateFilter[] {
  const linked = linkStates.filter((state) => states.includes(state))
  const unassigned = states.includes('unassigned')
  if (!states.length || (unassigned && linked.length === linkStates.length)) return [{}]
  return [
    ...(linked.length ? [{ 'filter.entity_link_state': linked }] : []),
    ...(unassigned ? [{ 'filter.is_assigned': false }] : []),
  ]
}
