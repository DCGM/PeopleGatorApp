import {
  PEOPLE_COUNT_OPTIONS,
  type PeopleCountQuery,
  type PeopleCountField,
  type PeopleCountState,
} from './people-counts'
import type { SharedQuery } from './shared-filters'
import type { EntitySortField } from '@/client'
import type { SortState } from '@/lib/sorting'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { assignmentEntityFilter, type AssignmentFilter } from '@/viewmodels/assignment'
import { useEntityResultsQuery, type EntitySearchRecord } from '@/query/search'

export type PeopleSearchItem = {
  thumbnailFaceId?: string | null
  id: string
  version: number
  name: string
  aliases: string[]
  faces: number | null
  names: number | null
  countDetails: { field: string; label: string; value: number | null }[]
}

export function usePeopleSearch(
  searchTerm: MaybeRefOrGetter<string>,
  filter: MaybeRefOrGetter<AssignmentFilter>,
  pageSize = 12,
  shared: MaybeRefOrGetter<SharedQuery & PeopleCountQuery> = {},
  enabled: MaybeRefOrGetter<boolean> = true,
  sort?: MaybeRefOrGetter<SortState<EntitySortField>>,
) {
  const normalizedSearch = computed(() => toValue(searchTerm).trim())
  const assignment = computed(() => assignmentEntityFilter(toValue(filter)))
  const peopleQuery = useEntityResultsQuery(
    computed(() => ({
      query: normalizedSearch.value,
      ...assignment.value,
      processingFilters: { ...toValue(shared), 'filter.entity_type': ['person'] },
      limit: pageSize,
      sort: sort && toValue(sort),
    })),
    enabled,
  )

  const pageRecords = computed<EntitySearchRecord[]>(() => {
    const uniquePeople = new Map<string, EntitySearchRecord>()
    for (const page of peopleQuery.data.value?.pages ?? []) {
      for (const person of page.items) uniquePeople.set(person.entity_id, person)
    }
    return [...uniquePeople.values()]
  })

  // Totals are always displayed; expose any state counts used by filters or sorting.
  const countOptions = computed(() =>
    PEOPLE_COUNT_OPTIONS.filter(
      ({ value }) =>
        !value.endsWith('_total_count') &&
        (toValue(shared)[`filter.min_${value}`] !== undefined ||
          toValue(shared)[`filter.max_${value}`] !== undefined ||
          (sort && toValue(sort).field === value)),
    ),
  )
  function stateCount(person: EntitySearchRecord, field: PeopleCountField): number | null {
    const [category, state] = field.split('_') as [string, PeopleCountState]
    const stats = person.entity_link_stats
    const faces = stats?.faces?.[state],
      mentions = stats?.mentions?.[state]
    if (category === 'annotations')
      return faces != null && mentions != null ? faces + mentions : null
    return (category === 'faces' ? faces : mentions) ?? null
  }

  const people = computed<PeopleSearchItem[]>(() =>
    pageRecords.value.map((person) => ({
      id: person.entity_id,
      version: person.version,
      thumbnailFaceId: person.thumbnail_face_id,
      name: person.name || 'Unnamed person',
      aliases: person.aliases ?? [],
      faces: person.entity_link_stats?.faces?.total ?? null,
      names: person.entity_link_stats?.mentions?.total ?? null,
      countDetails: countOptions.value.map(({ value: field, label }) => ({
        field,
        label,
        value: stateCount(person, field),
      })),
    })),
  )

  return {
    error: peopleQuery.error,
    hasNextPage: peopleQuery.hasNextPage,
    isFetching: peopleQuery.isFetching,
    isFetchingNextPage: peopleQuery.isFetchingNextPage,
    isLoading: computed(() => peopleQuery.isPending.value && toValue(enabled)),
    loadMore: () => {
      if (!toValue(enabled) || peopleQuery.isFetching.value || !peopleQuery.hasNextPage.value)
        return Promise.resolve()
      return peopleQuery.fetchNextPage({ cancelRefetch: false })
    },
    people,
    resultCount: computed(() => {
      return peopleQuery.data.value?.pages[0]?.totalCount ?? 0
    }),
  }
}
