import { computed } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'
import type { ActiveFilter } from '@/components/custom/ActiveFilters.vue'
import { formatLifeDate, parseIsoDate } from '@/lib/life-dates'

/**
 * Inclusive birth/death date ranges for People (#123). URL values are calendar
 * dates (`YYYY-MM-DD`) passed unchanged to the API; unknown dates never match.
 */
export const LIFE_DATE_FILTERS = [
  { key: 'born_from', param: 'birth_date_from', label: 'Born from' },
  { key: 'born_to', param: 'birth_date_to', label: 'Born to' },
  { key: 'died_from', param: 'death_date_from', label: 'Died from' },
  { key: 'died_to', param: 'death_date_to', label: 'Died to' },
] as const
export type LifeDateKey = (typeof LIFE_DATE_FILTERS)[number]['key']
export type LifeDateQuery = Partial<
  Record<`filter.${(typeof LIFE_DATE_FILTERS)[number]['param']}`, string>
>
export const LIFE_DATE_KEYS: LifeDateKey[] = LIFE_DATE_FILTERS.map(({ key }) => key)

const raw = (value: LocationQuery[string] | undefined) =>
  (Array.isArray(value) ? value[0] : value) ?? undefined

export function readLifeDates(query: LocationQuery) {
  const params: LifeDateQuery = {},
    tags: ActiveFilter[] = [],
    values = {} as Record<LifeDateKey, string>
  let error: string | undefined
  for (const { key, param, label } of LIFE_DATE_FILTERS) {
    const value = raw(query[key])
    const date = parseIsoDate(value)
    values[key] = date ?? ''
    if (!value) continue
    if (date) params[`filter.${param}`] = date
    else error = 'Enter dates as YYYY-MM-DD.'
    tags.push({
      key,
      value,
      label: `${label}: ${date ? formatLifeDate(date) : `${value} (invalid)`}`,
    })
  }
  for (const [from, to, label] of [
    ['born_from', 'born_to', 'Born'],
    ['died_from', 'died_to', 'Died'],
  ] as const) {
    if (values[from] && values[to] && values[from] > values[to])
      error = `${label}: the start date must not be after the end date.`
  }
  return { params, tags, values, error }
}

export function usePeopleLifeDates() {
  const route = useRoute(),
    router = useRouter()
  const state = computed(() => readLifeDates(route.query))
  function set(key: LifeDateKey, value: string) {
    void router.push({ query: { ...route.query, [key]: value || undefined, cursor: undefined } })
  }
  function remove(tag: ActiveFilter) {
    void router.push({ query: { ...route.query, [tag.key]: undefined, cursor: undefined } })
  }
  return {
    params: computed(() => state.value.params),
    tags: computed(() => state.value.tags),
    values: computed(() => state.value.values),
    error: computed(() => state.value.error),
    set,
    remove,
  }
}
