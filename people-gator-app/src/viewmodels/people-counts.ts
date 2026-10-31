import { computed } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'
import { parseMinimum } from './annotation-counts'
import type { ActiveFilter } from '@/components/custom/ActiveFilters.vue'

export const PEOPLE_COUNT_CATEGORIES = [
  { value: 'annotations', label: 'All annotations' },
  { value: 'faces', label: 'Faces' },
  { value: 'mentions', label: 'Text mentions' },
] as const
export type PeopleCountCategory = (typeof PEOPLE_COUNT_CATEGORIES)[number]['value']
export const PEOPLE_COUNT_STATES = [
  { value: 'total', label: 'All' },
  { value: 'verified', label: 'Verified' },
  { value: 'manual', label: 'Manual' },
  { value: 'automatic', label: 'Automatic' },
] as const
export type PeopleCountState = (typeof PEOPLE_COUNT_STATES)[number]['value']
export type PeopleCountField = `${PeopleCountCategory}_${PeopleCountState}_count`
export const PEOPLE_COUNT_OPTIONS = PEOPLE_COUNT_CATEGORIES.flatMap(({ value: category, label }) =>
  PEOPLE_COUNT_STATES.map(({ value: state, label: stateLabel }) => ({
    value: `${category}_${state}_count` as PeopleCountField,
    label: state === 'total' ? label : `${label}: ${stateLabel}`,
    group: label,
    kind: 'number' as const,
  })),
)
export type PeopleCountKey = `${'min' | 'max'}_${PeopleCountField}`
export type PeopleCountQuery = Partial<Record<`filter.${PeopleCountKey}`, number>>
export const PEOPLE_COUNT_KEYS = PEOPLE_COUNT_OPTIONS.flatMap(
  ({ value }) => [`min_${value}`, `max_${value}`] as PeopleCountKey[],
)

export function readPeopleCounts(query: LocationQuery) {
  const params: PeopleCountQuery = {},
    tags: ActiveFilter[] = []
  let error: string | undefined
  for (const { value: field, label } of PEOPLE_COUNT_OPTIONS) {
    const lower = parseMinimum(query[`min_${field}`])
    const upper = parseMinimum(query[`max_${field}`])
    for (const bound of ['min', 'max'] as const) {
      const key = `${bound}_${field}` as PeopleCountKey
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
  return { params, tags, error }
}

export function usePeopleCounts() {
  const route = useRoute(),
    router = useRouter()
  const counts = computed(() => readPeopleCounts(route.query))
  function set(
    category: PeopleCountCategory,
    lower: string,
    upper: string,
    state: PeopleCountState = 'total',
  ) {
    const field: PeopleCountField = `${category}_${state}_count`
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
