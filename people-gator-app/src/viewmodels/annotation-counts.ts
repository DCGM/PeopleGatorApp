import { computed } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'
import { DOCUMENT_ANNOTATION_GROUPS, DOCUMENT_ANNOTATION_STATES } from './document-table'
import type { SortOption } from '@/lib/sorting'
import type { ActiveFilter } from '@/components/custom/ActiveFilters.vue'

type Category = 'annotations' | 'faces' | 'mentions'
type State = (typeof DOCUMENT_ANNOTATION_STATES)[number]['id']
export type AnnotationCountField = `${Category}_${State}_count`
export const COUNT_OPTIONS = DOCUMENT_ANNOTATION_GROUPS.flatMap((group) =>
  DOCUMENT_ANNOTATION_STATES.map((state) => ({
    value:
      `${group.scope === 'all' ? 'annotations' : group.scope}_${state.id}_count` as AnnotationCountField,
    label: `${group.label}: ${state.label}`,
    group: group.label,
    kind: 'number' as const,
  })),
) satisfies SortOption<AnnotationCountField>[]
export const COUNT_KEYS = COUNT_OPTIONS.map((option) => `min_${option.value}`)
export type AnnotationCountQuery = Partial<Record<`filter.min_${AnnotationCountField}`, number>>

/** Decimal integers only: no fractional, negative, exponential or blank counts. */
export function parseMinimum(value: unknown): number | undefined {
  if (typeof value !== 'string' || !/^[0-9]+$/.test(value)) return undefined
  const number = Number(value)
  return Number.isSafeInteger(number) ? number : undefined
}

export function readCountFilters(query: LocationQuery) {
  const params: AnnotationCountQuery = {}
  const tags: ActiveFilter[] = []
  let error: string | undefined
  for (const option of COUNT_OPTIONS) {
    const key = `min_${option.value}`
    const raw = query[key]
    if (raw === undefined) continue
    const value = parseMinimum(raw)
    if (value === undefined) error = 'Enter a non-negative whole number for each minimum count.'
    else params[`filter.min_${option.value}`] = value
    tags.push({
      key,
      value: String(raw),
      label: `${option.label} ≥ ${String(raw)}${value === undefined ? ' (invalid)' : ''}`,
    })
  }
  return { params, tags, error }
}

export function useAnnotationCounts() {
  const route = useRoute(),
    router = useRouter()
  const counts = computed(() => readCountFilters(route.query))
  function set(field: AnnotationCountField, value: number) {
    void router.push({
      query: {
        ...route.query,
        [`min_${field}`]: String(value),
        cursor: undefined,
        page_cursor: undefined,
      },
    })
  }
  function remove(tag: ActiveFilter) {
    void router.push({
      query: { ...route.query, [tag.key]: undefined, cursor: undefined, page_cursor: undefined },
    })
  }
  return {
    params: computed(() => counts.value.params),
    tags: computed(() => counts.value.tags),
    error: computed(() => counts.value.error),
    set,
    remove,
  }
}
