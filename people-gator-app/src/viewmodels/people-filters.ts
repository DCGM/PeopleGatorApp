import { computed } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import { normalizeAssignmentFilter, type AssignmentFilter } from './assignment'

// People-only search and assignment state; the shared configuration lives in shared-filters.ts.
export const ASSIGNMENT_LABELS = { faces: 'Assigned faces', mentions: 'Assigned mentions' } as const

export function usePeopleFilters() {
  const route = useRoute()
  const router = useRouter()
  function update(changes: LocationQueryRaw) {
    void router.push({ query: { ...route.query, ...changes, cursor: undefined } })
  }
  const searchTerm = computed({
    get: () => (typeof route.query.q === 'string' ? route.query.q : ''),
    set: (q: string) => update({ q: q || undefined }),
  })
  const assignment = computed({
    get: () => normalizeAssignmentFilter(route.query.assignment ?? route.query.filters),
    set: (value: AssignmentFilter) =>
      update({ assignment: value === 'all' ? undefined : value, filters: undefined }),
  })
  return { searchTerm, assignment }
}
