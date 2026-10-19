import { computed } from 'vue'
import { useRoute, useRouter, type LocationQuery, type LocationQueryRaw } from 'vue-router'
import type { EntityLinkState } from '@/client'
import type { DocumentListParams } from '@/query/media'
import { parseLinkStates } from '@/lib/entity-links'
import { localTimeToUtc, utcToLocalTime, processingFilterError } from './people-filters'

export type DocumentFilters = {
  touchedFrom: string
  touchedTo: string
  libraries: string[]
  userIds: string[]
  apiKeyIds: string[]
  linkStates: EntityLinkState[]
  unassigned: 'all' | 'yes' | 'no'
}
export function emptyDocumentFilters(): DocumentFilters {
  return {
    touchedFrom: '',
    touchedTo: '',
    libraries: [],
    userIds: [],
    apiKeyIds: [],
    linkStates: [],
    unassigned: 'all',
  }
}
function values(value: LocationQuery[string] | undefined): string[] {
  return [
    ...new Set(
      (Array.isArray(value) ? value : [value]).filter(
        (v): v is string => typeof v === 'string' && !!v,
      ),
    ),
  ].sort()
}
export function readDocumentFilters(query: LocationQuery): DocumentFilters {
  return {
    touchedFrom: utcToLocalTime(query.touched_from),
    touchedTo: utcToLocalTime(query.touched_to),
    libraries: values(query.library),
    userIds: values(query.touched_by),
    apiKeyIds: values(query.api_key),
    linkStates: parseLinkStates(query.link_state),
    unassigned: query.unassigned === 'yes' ? 'yes' : query.unassigned === 'no' ? 'no' : 'all',
  }
}
export function documentFilterError(filters: DocumentFilters) {
  return processingFilterError({ ...filters, documentIds: [] })
}
export function documentFiltersQuery(filters: DocumentFilters): DocumentListParams {
  return {
    ...(filters.touchedFrom && { 'filter.last_touched_from': localTimeToUtc(filters.touchedFrom) }),
    ...(filters.touchedTo && { 'filter.last_touched_to': localTimeToUtc(filters.touchedTo) }),
    ...(filters.libraries.length && { 'filter.library': [...filters.libraries].sort() }),
    ...(filters.userIds.length && {
      'filter.last_touched_by_user_id': [...filters.userIds].sort(),
    }),
    ...(filters.apiKeyIds.length && {
      'filter.last_touched_by_api_key_id': [...filters.apiKeyIds].sort(),
    }),
    ...(filters.linkStates.length && { 'filter.entity_link_state': filters.linkStates }),
    ...(filters.unassigned !== 'all' && {
      'filter.has_unassigned_faces': filters.unassigned === 'yes',
    }),
  }
}
export function documentFiltersUrl(filters: DocumentFilters): LocationQueryRaw {
  return {
    ...(filters.touchedFrom && { touched_from: localTimeToUtc(filters.touchedFrom) }),
    ...(filters.touchedTo && { touched_to: localTimeToUtc(filters.touchedTo) }),
    ...(filters.libraries.length && { library: [...filters.libraries].sort() }),
    ...(filters.userIds.length && { touched_by: [...filters.userIds].sort() }),
    ...(filters.apiKeyIds.length && { api_key: [...filters.apiKeyIds].sort() }),
    ...(filters.linkStates.length && { link_state: filters.linkStates }),
    ...(filters.unassigned !== 'all' && { unassigned: filters.unassigned }),
  }
}
export function useDocumentFilters() {
  const route = useRoute()
  const router = useRouter()
  const searchTerm = computed({
    get: () => (typeof route.query.q === 'string' ? route.query.q : ''),
    set: (q: string) => {
      void router.push({ query: { ...route.query, q: q || undefined } })
    },
  })
  // URL is the source of truth: back/forward never races a second watcher.
  const filters = computed({
    get: () => readDocumentFilters(route.query),
    set: (value: DocumentFilters) => {
      void router.push({
        query: {
          ...route.query,
          touched_from: undefined,
          touched_to: undefined,
          library: undefined,
          touched_by: undefined,
          api_key: undefined,
          link_state: undefined,
          unassigned: undefined,
          ...(searchTerm.value && { q: searchTerm.value }),
          ...documentFiltersUrl(value),
        },
      })
    },
  })
  return { searchTerm, filters }
}
