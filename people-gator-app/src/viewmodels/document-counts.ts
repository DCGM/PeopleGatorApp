import { computed } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'
import { parseMinimum } from './annotation-counts'
import type { ActiveFilter } from '@/components/custom/ActiveFilters.vue'

/** Documents filter each annotation count, and their linked people, by an inclusive range. */
export const DOCUMENT_COUNT_CATEGORIES = [
  { value: 'annotations', label: 'All annotations' },
  { value: 'faces', label: 'Faces' },
  { value: 'mentions', label: 'Text mentions' },
] as const
export type DocumentCountCategory = (typeof DOCUMENT_COUNT_CATEGORIES)[number]['value']
export const DOCUMENT_COUNT_STATES = [
  { value: 'total', label: 'All' },
  { value: 'automatic', label: 'Automatic' },
  { value: 'manual', label: 'Manual' },
  { value: 'verified', label: 'Verified' },
  { value: 'unassigned', label: 'Unassigned' },
] as const
export type DocumentCountState = (typeof DOCUMENT_COUNT_STATES)[number]['value']
export const LINKED_PEOPLE_FIELD = 'linked_entity_count'
export type DocumentCountField =
  `${DocumentCountCategory}_${DocumentCountState}_count` | typeof LINKED_PEOPLE_FIELD
export const DOCUMENT_COUNT_OPTIONS: { value: DocumentCountField; label: string }[] = [
  ...DOCUMENT_COUNT_CATEGORIES.flatMap(({ value: category, label }) =>
    DOCUMENT_COUNT_STATES.map(({ value: state, label: stateLabel }) => ({
      value: `${category}_${state}_count` as DocumentCountField,
      label: state === 'total' ? label : `${label}: ${stateLabel}`,
    })),
  ),
  { value: LINKED_PEOPLE_FIELD, label: 'People' },
]
export type DocumentCountKey = `${'min' | 'max'}_${DocumentCountField}`
export type DocumentCountQuery = Partial<Record<`filter.${DocumentCountKey}`, number>>
export const DOCUMENT_COUNT_KEYS = DOCUMENT_COUNT_OPTIONS.flatMap(
  ({ value }) => [`min_${value}`, `max_${value}`] as DocumentCountKey[],
)

export function readDocumentCounts(query: LocationQuery) {
  const params: DocumentCountQuery = {},
    tags: ActiveFilter[] = []
  let error: string | undefined
  for (const { value: field, label } of DOCUMENT_COUNT_OPTIONS) {
    const lower = parseMinimum(query[`min_${field}`])
    const upper = parseMinimum(query[`max_${field}`])
    for (const bound of ['min', 'max'] as const) {
      const key = `${bound}_${field}` as DocumentCountKey
      const raw = query[key]
      if (raw === undefined) continue
      const value = parseMinimum(raw)
      if (value === undefined) error = 'Enter non-negative whole counts up to 9007199254740991.'
      else params[`filter.${key}`] = value
      tags.push({
        key,
        value: String(raw),
        label: `${label} ${bound === 'min' ? '≥' : '≤'} ${String(raw)}${value === undefined ? ' (invalid)' : ''}`,
      })
    }
    if (lower !== undefined && upper !== undefined && lower > upper)
      error = `${label}: minimum must not exceed maximum.`
  }
  // The API rejects a reversed range, so send none of an invalid configuration.
  return { params: error ? {} : params, tags, error }
}

export function useDocumentCounts() {
  const route = useRoute(),
    router = useRouter()
  const counts = computed(() => readDocumentCounts(route.query))
  function set(field: DocumentCountField, lower: string, upper: string) {
    void router.push({
      query: {
        ...route.query,
        [`min_${field}`]: lower || undefined,
        [`max_${field}`]: upper || undefined,
        cursor: undefined,
      },
    })
  }
  function remove(tag: ActiveFilter) {
    void router.push({ query: { ...route.query, [tag.key]: undefined, cursor: undefined } })
  }
  return {
    params: computed(() => counts.value.params),
    tags: computed(() => counts.value.tags),
    error: computed(() => counts.value.error),
    set,
    remove,
  }
}
