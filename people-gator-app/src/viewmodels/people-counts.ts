import { computed } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'
import { parseMinimum } from './annotation-counts'
import type { ActiveFilter } from '@/components/custom/ActiveFilters.vue'

export const PEOPLE_COUNT_CATEGORIES = [
  { value: 'faces', label: 'Faces' },
  { value: 'mentions', label: 'Text mentions' },
] as const
export type PeopleCountCategory = (typeof PEOPLE_COUNT_CATEGORIES)[number]['value']
export type PeopleCountKey = `${'min' | 'max'}_${PeopleCountCategory}_total_count`
export type PeopleCountQuery = Partial<Record<`filter.${PeopleCountKey}`, number>>
export const PEOPLE_COUNT_KEYS = PEOPLE_COUNT_CATEGORIES.flatMap(
  ({ value }) => [`min_${value}_total_count`, `max_${value}_total_count`] as PeopleCountKey[],
)

export function readPeopleCounts(query: LocationQuery) {
  const params: PeopleCountQuery = {},
    tags: ActiveFilter[] = []
  let error: string | undefined
  for (const { value: category, label } of PEOPLE_COUNT_CATEGORIES) {
    const lower = parseMinimum(query[`min_${category}_total_count`])
    const upper = parseMinimum(query[`max_${category}_total_count`])
    for (const bound of ['min', 'max'] as const) {
      const key = `${bound}_${category}_total_count` as PeopleCountKey
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
  function set(category: PeopleCountCategory, lower: string, upper: string) {
    void router.push({
      query: {
        ...route.query,
        [`min_${category}_total_count`]: lower || undefined,
        [`max_${category}_total_count`]: upper || undefined,
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
