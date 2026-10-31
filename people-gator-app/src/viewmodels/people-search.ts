import type { SharedQuery } from './shared-filters'
import type { EntitySortField } from '@/client'
import type { SortState } from '@/lib/sorting'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { assignmentEntityFilter, type AssignmentFilter } from '@/viewmodels/assignment'
import { useEntityResultsQuery, type EntitySearchRecord } from '@/query/search'

export type PeopleSearchItem = {
  thumbnailFaceId?: string | null
  id: string
  name: string
  aliases: string[]
  faces: number | null
  names: number | null
}

export function usePeopleSearch(
  searchTerm: MaybeRefOrGetter<string>,
  filter: MaybeRefOrGetter<AssignmentFilter>,
  pageSize = 12,
  shared: MaybeRefOrGetter<SharedQuery> = {},
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

  const people = computed<PeopleSearchItem[]>(() =>
    pageRecords.value.map((person) => ({
      id: person.entity_id,
      thumbnailFaceId: person.thumbnail_face_id,
      name: person.name || 'Unnamed person',
      aliases: person.aliases ?? [],
      faces: person.entity_link_stats?.faces?.total ?? null,
      names: person.entity_link_stats?.mentions?.total ?? null,
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
