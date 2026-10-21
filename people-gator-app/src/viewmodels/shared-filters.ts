import { computed, ref, watch } from 'vue'
import {
  useRoute,
  useRouter,
  type LocationQuery,
  type LocationQueryRaw,
  type RouteLocationNormalizedLoaded,
} from 'vue-router'
import type { EntityLinkState } from '@/client'
import { parseLinkStates } from '@/lib/entity-links'

// One transferable filter configuration (#52). Every list applies it to its own
// records: source scope through real library/document/page relationships, and
// "modified" criteria through each record's own latest recorded change.

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

export function localTimeToUtc(value: string): string | undefined {
  if (!value) return undefined
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return undefined
  const utc = date.toISOString()
  const fraction = value.match(/\.(\d{4,6})$/)?.[1]
  return fraction ? utc.replace(/\.\d{3}Z$/, `.${fraction}Z`) : utc
}

export function utcToLocalTime(value: unknown): string {
  if (typeof value !== 'string' || !/T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  const fraction = value.match(/\.(\d+)(?:Z|[+-]\d{2}:\d{2})$/i)?.[1]
  const seconds = `${pad(date.getSeconds())}.${fraction?.padEnd(3, '0') ?? String(date.getMilliseconds()).padStart(3, '0')}`
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${seconds}`
}

export const sharedKeys = [
  'library',
  'document',
  'page',
  'link_state',
  'touched_by',
  'api_key',
  'touched_from',
  'touched_to',
] as const

export type SharedFilters = {
  libraries: string[]
  /** Internal registered document source UUIDs. */
  documentIds: string[]
  /** Internal page source UUIDs. */
  pageIds: string[]
  linkStates: EntityLinkState[]
  userIds: string[]
  apiKeyIds: string[]
  touchedFrom: string
  touchedTo: string
}

export function readSharedFilters(query: LocationQuery): SharedFilters {
  return {
    libraries: queryValues(query.library),
    documentIds: ids(query.document),
    pageIds: ids(query.page),
    linkStates: parseLinkStates(query.link_state),
    userIds: ids(query.touched_by),
    apiKeyIds: ids(query.api_key),
    touchedFrom: utcToLocalTime(queryValues(query.touched_from)[0]),
    touchedTo: utcToLocalTime(queryValues(query.touched_to)[0]),
  }
}

export function emptySharedFilters(): SharedFilters {
  return readSharedFilters({})
}

export function hasSharedFilters(filters: SharedFilters) {
  return Object.values(filters).some((value) => (Array.isArray(value) ? value.length : !!value))
}

export type SharedQuery = {
  'filter.library'?: string[]
  'filter.document_source_id'?: string[]
  'filter.page_source_id'?: string[]
  'filter.entity_link_state'?: EntityLinkState[]
  'filter.last_touched_by_user_id'?: string[]
  'filter.last_touched_by_api_key_id'?: string[]
  'filter.last_touched_from'?: string
  'filter.last_touched_to'?: string
}

export function sharedFiltersQuery(f: SharedFilters): SharedQuery {
  return {
    ...(f.libraries.length && { 'filter.library': f.libraries }),
    ...(f.documentIds.length && { 'filter.document_source_id': f.documentIds }),
    ...(f.pageIds.length && { 'filter.page_source_id': f.pageIds }),
    ...(f.linkStates.length && { 'filter.entity_link_state': f.linkStates }),
    ...(f.userIds.length && { 'filter.last_touched_by_user_id': f.userIds }),
    ...(f.apiKeyIds.length && { 'filter.last_touched_by_api_key_id': f.apiKeyIds }),
    ...(f.touchedFrom && { 'filter.last_touched_from': localTimeToUtc(f.touchedFrom) }),
    ...(f.touchedTo && { 'filter.last_touched_to': localTimeToUtc(f.touchedTo) }),
  }
}

export function sharedFiltersUrl(f: SharedFilters): LocationQueryRaw {
  const list = (values: string[]) => (values.length ? [...values].sort() : undefined)
  return {
    library: list(f.libraries),
    document: list(f.documentIds),
    page: list(f.pageIds),
    link_state: f.linkStates.length ? f.linkStates : undefined,
    touched_by: list(f.userIds),
    api_key: list(f.apiKeyIds),
    touched_from: localTimeToUtc(f.touchedFrom),
    touched_to: localTimeToUtc(f.touchedTo),
  }
}

export function sharedFilterError(f: Pick<SharedFilters, 'touchedFrom' | 'touchedTo'>) {
  const from = localTimeToUtc(f.touchedFrom)
  const to = localTimeToUtc(f.touchedTo)
  if ((f.touchedFrom && !from) || (f.touchedTo && !to)) return 'Enter a valid date and time.'
  const comparable = (value: string) =>
    value.replace(/\.(\d+)Z$/, (_, fraction: string) => `.${fraction.padEnd(6, '0')}Z`)
  if (from && to && comparable(from) > comparable(to))
    return 'The start time must be before or equal to the end time.'
  return undefined
}

/** Invalid copied values stay visible and block requests until removed. */
export function invalidSharedValues(query: LocationQuery) {
  const invalid: { key: string; value: string }[] = []
  for (const key of ['document', 'page', 'touched_by', 'api_key'])
    for (const value of queryValues(query[key])) if (!uuid.test(value)) invalid.push({ key, value })
  for (const value of queryValues(query.link_state))
    if (!parseLinkStates(value).length) invalid.push({ key: 'link_state', value })
  for (const key of ['touched_from', 'touched_to']) {
    const values = queryValues(query[key])
    for (const value of values)
      if (values.length > 1 || !utcToLocalTime(value)) invalid.push({ key, value })
  }
  return invalid
}

export function sharedUrlError(query: LocationQuery): string | undefined {
  if (invalidSharedValues(query).length)
    return 'This link contains an invalid filter. Remove or correct it.'
  return sharedFilterError(readSharedFilters(query))
}

export function useSharedFilters() {
  const route = useRoute(),
    router = useRouter()
  // The URL is the source of truth, so Back/Forward and copied links restore it.
  // Local state applies consecutive edits before the pushed URL resolves.
  const state = ref(readSharedFilters(route.query))
  watch(
    () => route.query,
    (query) => {
      state.value = readSharedFilters(query)
    },
  )
  const filters = computed({
    get: () => state.value,
    set: (value: SharedFilters) => {
      const next = sharedFiltersUrl(value)
      const fields: Record<string, keyof SharedFilters> = {
        document: 'documentIds',
        page: 'pageIds',
        touched_by: 'userIds',
        api_key: 'apiKeyIds',
        link_state: 'linkStates',
        touched_from: 'touchedFrom',
        touched_to: 'touchedTo',
      }
      // Editing a different criterion must not silently erase invalid copied values.
      for (const { key, value: invalid } of invalidSharedValues(route.query)) {
        const field = fields[key]!
        if (JSON.stringify(state.value[field]) === JSON.stringify(value[field]))
          next[key] = [...new Set([...queryValues(next[key] as LocationQuery[string]), invalid])]
      }
      state.value = value
      void router.push({
        query: { ...route.query, ...next, cursor: undefined, page_cursor: undefined },
      })
    },
  })
  const error = computed(() => sharedUrlError(route.query))
  return {
    filters,
    error,
    params: computed(() => sharedFiltersQuery(filters.value)),
    clear: () => {
      filters.value = emptySharedFilters()
    },
  }
}

/**
 * Query for a related view: the same shared configuration, applied there to that
 * view's records. View-specific choices, search text, sort and cursors stay behind.
 */
export function relatedQuery(
  route: Pick<RouteLocationNormalizedLoaded, 'name' | 'query'> | undefined,
  extra: LocationQueryRaw = {},
): LocationQueryRaw {
  if (!route) return extra
  const result: LocationQueryRaw = Object.fromEntries(
    Object.entries(sharedFiltersUrl(readSharedFilters(route.query))).filter(
      ([, value]) => value !== undefined,
    ),
  )
  // Invalid values remain visible on the destination rather than disappearing.
  for (const { key, value } of invalidSharedValues(route.query))
    result[key] = [...queryValues(result[key] as LocationQuery[string]), value]
  if (route.name === 'people-search' && route.query.assignment === 'mentions')
    result.tab = 'mentions'
  return { ...result, ...extra }
}

// Removed #31 keys. Same-meaning keys are renamed; annotation-edit keys keep
// their meaning only where the listed records are those annotations (#52).
const renamed: Record<string, string> = {
  evidence_library: 'library',
  evidence_document: 'document',
  evidence_source: 'page',
}
const annotationEdits: Record<string, string> = {
  evidence_user: 'touched_by',
  evidence_key: 'api_key',
  evidence_from: 'touched_from',
  evidence_to: 'touched_to',
}
const annotationRoutes = new Set(['person-detail', 'document-page'])
export const legacyFilterLabels: Record<string, string> = {
  evidence_user: 'annotation user',
  evidence_key: 'annotation API key',
  evidence_from: 'annotation from',
  evidence_to: 'annotation to',
}

/** Returns a migrated query and removed criteria, or undefined when already current. */
export function migrateLegacyFilters(
  name: unknown,
  query: LocationQuery,
): { query: LocationQuery; dropped: string[] } | undefined {
  const keys = Object.keys(query)
  const obsolete = (key: string) =>
    key in renamed ||
    key in annotationEdits ||
    key === 'origin_text' ||
    key === 'origin_return' ||
    /^origin_(person|source|discovery)_/.test(key)
  if (!keys.some(obsolete)) return undefined
  const next: LocationQuery = {}
  const dropped: string[] = []
  const merge = (key: string, value: LocationQuery[string] | undefined) => {
    if (['touched_from', 'touched_to'].includes(key)) {
      // A current single bound wins over a legacy one.
      if (!(key in next) && value !== undefined) next[key] = value
      return
    }
    next[key] = [...new Set([...queryValues(next[key]), ...queryValues(value)])].sort()
  }
  for (const key of keys) if (!obsolete(key)) next[key] = query[key]!
  for (const key of keys) {
    if (key in renamed) merge(renamed[key]!, query[key])
    else if (key in annotationEdits) {
      if (annotationRoutes.has(String(name))) merge(annotationEdits[key]!, query[key])
      else dropped.push(legacyFilterLabels[key]!)
    }
  }
  return { query: next, dropped }
}

// Shown once after a copied legacy link lost criteria that would otherwise
// silently change meaning on this view.
export const legacyFilterNotice = ref<string[]>([])
