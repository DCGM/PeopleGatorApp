import { computed, ref, watch } from 'vue'
import {
  useRoute,
  useRouter,
  type LocationQuery,
  type LocationQueryRaw,
  type RouteLocationNormalizedLoaded,
} from 'vue-router'
import type { FaceListParams } from '@/query/faces'
import { parseLinkStates } from '@/lib/entity-links'
import { localTimeToUtc, utcToLocalTime, processingFilterError } from './people-filters'

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
export function queryValues(value: LocationQuery[string] | undefined) {
  return [
    ...new Set(
      (Array.isArray(value) ? value : [value]).filter(
        (v): v is string => typeof v === 'string' && !!v,
      ),
    ),
  ].sort()
}
const ids = (value: LocationQuery[string] | undefined) =>
  queryValues(value).filter((v) => uuid.test(v))
export const evidenceKeys = [
  'link_state',
  'evidence_library',
  'evidence_document',
  'evidence_source',
  'evidence_from',
  'evidence_to',
  'evidence_user',
  'evidence_key',
] as const
export function readEvidenceFilters(query: LocationQuery) {
  return {
    states: parseLinkStates(query.link_state),
    libraries: queryValues(query.evidence_library),
    documentIds: ids(query.evidence_document),
    sourceIds: ids(query.evidence_source),
    touchedFrom: utcToLocalTime(query.evidence_from),
    touchedTo: utcToLocalTime(query.evidence_to),
    userIds: ids(query.evidence_user),
    apiKeyIds: ids(query.evidence_key),
  }
}
export type EvidenceFilters = ReturnType<typeof readEvidenceFilters>
export type EvidenceQuery = Pick<
  FaceListParams,
  | 'filter.entity_link_state'
  | 'filter.evidence_library'
  | 'filter.document_source_id'
  | 'filter.evidence_source_id'
  | 'filter.evidence_touched_from'
  | 'filter.evidence_touched_to'
  | 'filter.evidence_touched_by_user_id'
  | 'filter.evidence_touched_by_api_key_id'
>
export function evidenceFilterError(value: EvidenceFilters) {
  return processingFilterError(value)
}
export function evidenceFiltersQuery(f: EvidenceFilters): EvidenceQuery {
  return {
    ...(f.states.length && { 'filter.entity_link_state': f.states }),
    ...(f.libraries.length && { 'filter.evidence_library': f.libraries }),
    ...(f.documentIds.length && { 'filter.document_source_id': f.documentIds }),
    ...(f.sourceIds.length && { 'filter.evidence_source_id': f.sourceIds }),
    ...(f.touchedFrom && { 'filter.evidence_touched_from': localTimeToUtc(f.touchedFrom) }),
    ...(f.touchedTo && { 'filter.evidence_touched_to': localTimeToUtc(f.touchedTo) }),
    ...(f.userIds.length && { 'filter.evidence_touched_by_user_id': f.userIds }),
    ...(f.apiKeyIds.length && { 'filter.evidence_touched_by_api_key_id': f.apiKeyIds }),
  }
}
export function evidenceFiltersUrl(f: EvidenceFilters): LocationQueryRaw {
  return {
    link_state: f.states.length ? f.states : undefined,
    evidence_library: f.libraries.length ? f.libraries : undefined,
    evidence_document: f.documentIds.length ? f.documentIds : undefined,
    evidence_source: f.sourceIds.length ? f.sourceIds : undefined,
    evidence_from: localTimeToUtc(f.touchedFrom),
    evidence_to: localTimeToUtc(f.touchedTo),
    evidence_user: f.userIds.length ? f.userIds : undefined,
    evidence_key: f.apiKeyIds.length ? f.apiKeyIds : undefined,
  }
}
export function sharedEvidenceUrl(query: LocationQuery): LocationQueryRaw {
  return evidenceFiltersUrl(readEvidenceFilters(query))
}
export function withoutEvidence(query: LocationQuery): LocationQueryRaw {
  return Object.fromEntries(
    Object.entries(query).filter(
      ([key]) => !evidenceKeys.includes(key as (typeof evidenceKeys)[number]),
    ),
  )
}
export function evidenceUrlError(query: LocationQuery): string | undefined {
  for (const key of ['evidence_from', 'evidence_to']) {
    if (query[key] && !utcToLocalTime(query[key]))
      return 'Invalid annotation date in this link. Remove or correct the criterion.'
  }
  for (const key of ['evidence_document', 'evidence_source', 'evidence_user', 'evidence_key']) {
    if (queryValues(query[key]).some((value) => !uuid.test(value)))
      return 'Invalid evidence identifier in this link. Remove or correct the criterion.'
  }
  return evidenceFilterError(readEvidenceFilters(query))
}

export function useEvidenceFilters() {
  const route = useRoute(),
    router = useRouter()
  const state = ref(readEvidenceFilters(route.query))
  watch(
    () => route.query,
    (query) => {
      state.value = readEvidenceFilters(query)
    },
  )
  const filters = computed({
    get: () => state.value,
    set: (value: EvidenceFilters) => {
      state.value = value
      void router.push({
        query: { ...route.query, ...evidenceFiltersUrl(value), cursor: undefined },
      })
    },
  })
  const error = computed(() => evidenceUrlError(route.query) ?? evidenceFilterError(filters.value))
  return {
    filters,
    error,
    params: computed(() => evidenceFiltersQuery(filters.value)),
    clear: () => {
      filters.value = readEvidenceFilters({})
    },
  }
}

// Resource-specific predicates travel as explicitly scoped context. They are never
// reinterpreted as annotation edits. Related views use normal application navigation.
export function relatedEvidenceQuery(
  route: Pick<RouteLocationNormalizedLoaded, 'name' | 'query' | 'path'> | undefined,
  extra: LocationQueryRaw = {},
): LocationQueryRaw {
  if (!route) return extra
  const query = route.query
  const result: LocationQueryRaw = { ...sharedEvidenceUrl(query) }
  for (const [key, value] of Object.entries(query))
    if (key.startsWith('origin_') && key !== 'origin_return') result[key] = value
  if (typeof query.q === 'string' && query.q) result.origin_text = query.q
  const scope =
    route.name === 'people-search'
      ? 'person'
      : route.name === 'person-detail'
        ? 'discovery'
        : 'source'
  if (scope)
    for (const key of [
      'touched_from',
      'touched_to',
      'touched_by',
      'api_key',
      'assignment',
      'unassigned',
      'discovery_assignment',
      'candidate_mode',
      'candidate_text',
    ]) {
      if (query[key]) result[`origin_${scope}_${key}`] = query[key]
    }
  // Legacy people document selection is an evidence scope with an internal UUID.
  if (route.name === 'people-search' && ids(query.document).length)
    result.evidence_document = ids(query.document)
  if (
    route.name !== 'people-search' &&
    route.name !== 'person-detail' &&
    queryValues(query.library).length
  )
    result.evidence_library = queryValues(query.library)
  if (route.name === 'people-search' && query.assignment === 'mentions') result.tab = 'mentions'
  return { ...result, ...extra }
}
