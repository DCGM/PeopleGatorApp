import { computed } from 'vue'
import { useRoute, type LocationQuery, type LocationQueryRaw } from 'vue-router'

import type { TextMentionGroupSortField, TextMentionSortField, FaceSortField } from '@/client'
import { readSort, sortUrl, type SortOption, type SortState } from '@/lib/sorting'
import { useRouteQueryPatch } from '@/composables/route-query'
import {
  FACE_DEFAULT,
  FACE_SORT_KEYS,
  MENTION_DEFAULT,
  MENTION_GROUP_DEFAULT,
  MENTION_GROUP_SORT_KEYS,
  MENTION_GROUP_SORTS,
  MENTION_SORT_KEYS,
  MENTION_SORTS,
  WORKSPACE_FACE_SORTS,
} from '@/viewmodels/sort-options'

/**
 * Scan sidebar settings live only in the URL (#103): reload, shared links and
 * Back/Forward restore them, and every tab keeps its own keys while another is
 * open. Absent or invalid values resolve to the agreed defaults.
 */
export const SIDEBAR_TABS = ['people', 'faces', 'mentions', 'info'] as const
export type SidebarTab = (typeof SIDEBAR_TABS)[number]

export type PeopleScope = 'all' | 'document' | 'page'
export const PEOPLE_SCOPES: { value: PeopleScope; label: string }[] = [
  { value: 'all', label: 'All people' },
  { value: 'document', label: 'This document' },
  { value: 'page', label: 'This page' },
]

/** Context ranks this page, then this document, then everyone else. */
export type PeopleOrder = 'context' | 'relevance' | 'name' | 'last_touched_at'
export const PEOPLE_ORDERS: { value: PeopleOrder; label: string; scored?: boolean }[] = [
  { value: 'context', label: 'Page, document, others' },
  { value: 'relevance', label: 'Similarity', scored: true },
  { value: 'name', label: 'Name A–Z' },
  { value: 'last_touched_at', label: 'Last change' },
]

export type EvidenceScope = 'page' | 'document'
export const EVIDENCE_SCOPES: { value: EvidenceScope; label: string }[] = [
  { value: 'page', label: 'This page' },
  { value: 'document', label: 'This document' },
]
export type FaceView = 'flat' | 'person'
export const FACE_VIEWS: { value: FaceView; label: string }[] = [
  { value: 'flat', label: 'Flat' },
  { value: 'person', label: 'Group by person' },
]
export type MentionView = 'group' | 'flat'
export const MENTION_VIEWS: { value: MentionView; label: string }[] = [
  { value: 'group', label: 'Group by text' },
  { value: 'flat', label: 'Flat' },
]
export type ActivityDirection = 'desc' | 'asc'

/** A page lists one source, so source order adds nothing to its faces. */
export const SCAN_MENTION_SORTS: SortOption<TextMentionSortField>[] = MENTION_SORTS

export type ScanSidebarState = {
  tab: SidebarTab
  peopleText: string
  searchFaceId: string | null
  peopleScope: PeopleScope
  peopleOrder: PeopleOrder
  faceScope: EvidenceScope
  faceView: FaceView
  faceSort: SortState<FaceSortField>
  mentionScope: EvidenceScope
  mentionView: MentionView
  mentionSort: SortState<TextMentionSortField>
  mentionGroupSort: SortState<TextMentionGroupSortField>
  activityDirection: ActivityDirection
}

function single(value: unknown) {
  return typeof value === 'string' ? value : undefined
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback
}

export function readTab(query: LocationQuery, hash = ''): SidebarTab {
  const panel = single(query.panel)
  // Former Activity/Statistics links and the statistics anchor open Info.
  if (panel === 'activity' || panel === 'statistics' || hash === '#link-statistics') return 'info'
  return oneOf(panel, SIDEBAR_TABS, 'people')
}

export function readSidebarState(query: LocationQuery, hash = ''): ScanSidebarState {
  // Former "Similar faces" links attached the selected face to the candidate search.
  const legacyFace = single(query.candidate_mode) === 'face' ? single(query.person) : undefined
  return {
    tab: readTab(query, hash),
    peopleText: single(query.candidate_text) ?? '',
    searchFaceId: single(query.candidate_face) || legacyFace || null,
    peopleScope: oneOf(
      single(query.people_scope),
      PEOPLE_SCOPES.map((scope) => scope.value),
      'all',
    ),
    peopleOrder: oneOf(
      single(query.candidate_sort),
      PEOPLE_ORDERS.map((order) => order.value),
      'context',
    ),
    faceScope: oneOf(single(query.face_scope), ['page', 'document'] as const, 'page'),
    faceView: oneOf(single(query.face_view), ['flat', 'person'] as const, 'flat'),
    faceSort: readSort(query, FACE_SORT_KEYS, WORKSPACE_FACE_SORTS, FACE_DEFAULT),
    mentionScope: oneOf(single(query.mention_scope), ['page', 'document'] as const, 'page'),
    mentionView: oneOf(single(query.mention_view), ['group', 'flat'] as const, 'group'),
    mentionSort: readSort(query, MENTION_SORT_KEYS, SCAN_MENTION_SORTS, MENTION_DEFAULT),
    mentionGroupSort: readSort(
      query,
      MENTION_GROUP_SORT_KEYS,
      MENTION_GROUP_SORTS,
      MENTION_GROUP_DEFAULT,
    ),
    activityDirection: oneOf(single(query.activity_dir), ['desc', 'asc'] as const, 'desc'),
  }
}

/** Similarity needs a name or face to score; without one, Context applies. */
export function effectivePeopleOrder(order: PeopleOrder, scored: boolean): PeopleOrder {
  return order === 'relevance' && !scored ? 'context' : order
}

/** URL values for a changed setting; defaults are omitted so links stay short. */
export function sidebarQuery(changes: Partial<ScanSidebarState>): LocationQueryRaw {
  const query: LocationQueryRaw = {}
  if ('tab' in changes) {
    query.panel = changes.tab === 'people' ? undefined : changes.tab
  }
  if ('peopleText' in changes) query.candidate_text = changes.peopleText || undefined
  if ('searchFaceId' in changes) {
    query.candidate_face = changes.searchFaceId ?? undefined
    query.candidate_mode = undefined
  }
  if ('peopleScope' in changes)
    query.people_scope = changes.peopleScope === 'all' ? undefined : changes.peopleScope
  if ('peopleOrder' in changes) {
    query.candidate_sort = changes.peopleOrder === 'context' ? undefined : changes.peopleOrder
    query.candidate_dir = undefined
  }
  if ('faceScope' in changes)
    query.face_scope = changes.faceScope === 'page' ? undefined : changes.faceScope
  if ('faceView' in changes)
    query.face_view = changes.faceView === 'flat' ? undefined : changes.faceView
  if (changes.faceSort)
    Object.assign(query, sortUrl(changes.faceSort, FACE_DEFAULT, FACE_SORT_KEYS))
  if ('mentionScope' in changes)
    query.mention_scope = changes.mentionScope === 'page' ? undefined : changes.mentionScope
  if ('mentionView' in changes)
    query.mention_view = changes.mentionView === 'group' ? undefined : changes.mentionView
  if (changes.mentionSort)
    Object.assign(query, sortUrl(changes.mentionSort, MENTION_DEFAULT, MENTION_SORT_KEYS))
  if (changes.mentionGroupSort)
    Object.assign(
      query,
      sortUrl(changes.mentionGroupSort, MENTION_GROUP_DEFAULT, MENTION_GROUP_SORT_KEYS),
    )
  if ('activityDirection' in changes)
    query.activity_dir =
      changes.activityDirection === 'desc' ? undefined : changes.activityDirection
  return query
}

export function useScanSidebarState() {
  const route = useRoute()
  const patch = useRouteQueryPatch()
  const state = computed(() => readSidebarState(route.query, route.hash))
  // A former "Similar faces" link attaches its face once; later selections leave it.
  if (route.query.candidate_mode !== undefined)
    patch({ candidate_mode: undefined, candidate_face: state.value.searchFaceId ?? undefined })

  /** Settings changes are history entries; typing replaces the current entry. */
  function update(changes: Partial<ScanSidebarState>, history: 'push' | 'replace' = 'push') {
    // Opening a tab from the statistics anchor leaves the anchor behind.
    const hash = 'tab' in changes && route.hash === '#link-statistics' ? '' : undefined
    patch(sidebarQuery(changes), history, hash)
  }

  /**
   * Face Search: the face becomes the sole reference, name text clears and
   * Similarity ranks the results. The selected scope is kept.
   */
  function searchByFace(faceId: string) {
    update({ tab: 'people', searchFaceId: faceId, peopleText: '', peopleOrder: 'relevance' })
  }

  return { state, update, searchByFace, patch }
}
