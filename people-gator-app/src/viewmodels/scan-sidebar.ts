import { computed, watch, type InjectionKey, type Ref } from 'vue'
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
/** The mention selected on the scan, so listed mentions can show it. */
export const SCAN_SELECTED_MENTION: InjectionKey<Readonly<Ref<string | null>>> =
  Symbol('scan-selected-mention')

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
export type MentionView = 'group' | 'person' | 'flat'
export const MENTION_VIEWS: { value: MentionView; label: string }[] = [
  { value: 'group', label: 'Group by text' },
  { value: 'person', label: 'Group by person' },
  { value: 'flat', label: 'Flat' },
]
export type ActivityDirection = 'desc' | 'asc'

/** A page lists one source, so source order adds nothing to its faces. */
export const SCAN_MENTION_SORTS: SortOption<TextMentionSortField>[] = MENTION_SORTS

export type ScanSidebarState = {
  tab: SidebarTab
  peopleText: string
  searchFaceId: string | null
  /** Embedding model for face search; the face's first model when unset or unavailable. */
  searchModel: string | null
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
  const peopleText = single(query.candidate_text) ?? ''
  const searchFaceId = single(query.candidate_face) || legacyFace || null
  const defaults = peopleDefaults({ peopleText, searchFaceId })
  return {
    tab: readTab(query, hash),
    peopleText,
    searchFaceId,
    searchModel: single(query.face_model) || null,
    peopleScope: oneOf(
      single(query.people_scope),
      PEOPLE_SCOPES.map((scope) => scope.value),
      defaults.peopleScope,
    ),
    peopleOrder: oneOf(
      single(query.candidate_sort),
      PEOPLE_ORDERS.map((order) => order.value),
      defaults.peopleOrder,
    ),
    faceScope: oneOf(single(query.face_scope), ['page', 'document'] as const, 'page'),
    faceView: oneOf(single(query.face_view), ['flat', 'person'] as const, 'flat'),
    faceSort: readSort(query, FACE_SORT_KEYS, WORKSPACE_FACE_SORTS, FACE_DEFAULT),
    mentionScope: oneOf(single(query.mention_scope), ['page', 'document'] as const, 'page'),
    mentionView: oneOf(single(query.mention_view), ['group', 'person', 'flat'] as const, 'group'),
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

/** URL keys of the sidebar's own settings, never evidence or shared filters. */
export const SIDEBAR_QUERY_KEYS = [
  'panel',
  'candidate_text',
  'candidate_face',
  'face_model',
  'people_scope',
  'candidate_sort',
  'candidate_dir',
  'face_scope',
  'face_view',
  'face_sort',
  'face_dir',
  'mention_scope',
  'mention_view',
  'mention_sort',
  'mention_dir',
  'group_sort',
  'group_dir',
  'activity_dir',
] as const

/**
 * Query for opening another scan page from the sidebar: the sidebar keeps its
 * tab and settings, while filters stay behind as for any navigation (#109).
 */
export function sidebarSettingsQuery(query: LocationQuery): LocationQueryRaw {
  return Object.fromEntries(
    SIDEBAR_QUERY_KEYS.flatMap((key) => (query[key] === undefined ? [] : [[key, query[key]]])),
  )
}

/** The chosen face-search model when the face has it, otherwise its first model. */
export function resolveSearchModel(chosen: string | null, available: readonly string[]) {
  return chosen && available.includes(chosen) ? chosen : (available[0] ?? null)
}

/** Similarity needs a name or face to score; without one, Context applies. */
export function effectivePeopleOrder(order: PeopleOrder, scored: boolean): PeopleOrder {
  return order === 'relevance' && !scored ? 'context' : order
}

type PeopleInput = Pick<ScanSidebarState, 'peopleText' | 'searchFaceId'>

export function hasPeopleSearch(input: Partial<PeopleInput>): boolean {
  return Boolean(input.peopleText?.trim() || input.searchFaceId)
}

function peopleDefaults(
  input: Partial<PeopleInput>,
): Pick<ScanSidebarState, 'peopleScope' | 'peopleOrder'> {
  return hasPeopleSearch(input)
    ? { peopleScope: 'all', peopleOrder: 'relevance' }
    : { peopleScope: 'document', peopleOrder: 'context' }
}

/** Entering/leaving search changes defaults once, preserving later explicit choices. */
export function peopleSearchChanges(
  current: ScanSidebarState,
  changes: Partial<ScanSidebarState>,
): Partial<ScanSidebarState> {
  const next = { ...current, ...changes }
  return hasPeopleSearch(current) === hasPeopleSearch(next)
    ? changes
    : { ...peopleDefaults(next), ...changes }
}

/** URL defaults depend on whether a name or face search is active. */
export function sidebarQuery(
  changes: Partial<ScanSidebarState>,
  next: Partial<PeopleInput> = changes,
): LocationQueryRaw {
  const query: LocationQueryRaw = {}
  const defaults = peopleDefaults(next)
  if ('tab' in changes) {
    query.panel = changes.tab === 'people' ? undefined : changes.tab
  }
  if ('peopleText' in changes) query.candidate_text = changes.peopleText || undefined
  if ('searchModel' in changes) query.face_model = changes.searchModel ?? undefined
  if ('searchFaceId' in changes) {
    query.candidate_face = changes.searchFaceId ?? undefined
    query.candidate_mode = undefined
  }
  if ('peopleScope' in changes)
    query.people_scope =
      changes.peopleScope === defaults.peopleScope ? undefined : changes.peopleScope
  if ('peopleOrder' in changes) {
    query.candidate_sort =
      changes.peopleOrder === defaults.peopleOrder ? undefined : changes.peopleOrder
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

  // Several controls may update before navigation commits; base the next change
  // on already-requested settings so a second event cannot undo a mode transition.
  let requested: ScanSidebarState | null = null
  watch(
    () => route.query,
    () => {
      requested = null
    },
    { flush: 'sync' },
  )

  /** Settings changes are history entries; typing replaces the current entry. */
  function update(changes: Partial<ScanSidebarState>, history: 'push' | 'replace' = 'push') {
    // Opening a tab from the statistics anchor leaves the anchor behind.
    const hash = 'tab' in changes && route.hash === '#link-statistics' ? '' : undefined
    const current = requested ?? state.value
    const adjusted = peopleSearchChanges(current, changes)
    requested = { ...current, ...adjusted }
    patch(sidebarQuery(adjusted, requested), history, hash)
  }

  /**
   * Face Search: the face becomes the sole reference, name text clears and
   * Similarity ranks all people, including when replacing an existing search.
   */
  function searchByFace(faceId: string) {
    update({
      tab: 'people',
      searchFaceId: faceId,
      peopleText: '',
      peopleScope: 'all',
      peopleOrder: 'relevance',
    })
  }

  return { state, update, searchByFace, patch }
}
