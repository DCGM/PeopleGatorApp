import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { assignmentEntityFilter, type AssignmentFilter } from '@/viewmodels/assignment'
import { fetchFaces } from '@/query/faces'
import { queryKeys } from '@/query/keys'
import { useEntityResultsQuery, type EntitySearchRecord } from '@/query/search'
import { fetchTextMentions } from '@/query/text-mentions'

export type PeopleSearchItem = {
  id: string
  name: string
  aliases: string[]
  faces: number
  names: number
}

const PEOPLE_CACHE_TIME = 10 * 60_000
const PEOPLE_GC_TIME = 60 * 60_000

export function usePeopleSearch(
  searchTerm: MaybeRefOrGetter<string>,
  filter: MaybeRefOrGetter<AssignmentFilter>,
  pageSize = 12,
) {
  const normalizedSearch = computed(() => toValue(searchTerm).trim())
  const assignment = computed(() => assignmentEntityFilter(toValue(filter)))
  const peopleQuery = useEntityResultsQuery(
    computed(() => ({
      query: normalizedSearch.value,
      ...assignment.value,
      limit: pageSize,
    })),
  )

  const pageRecords = computed<EntitySearchRecord[]>(() => {
    const uniquePeople = new Map<string, EntitySearchRecord>()
    for (const page of peopleQuery.data.value?.pages ?? []) {
      for (const person of page.items) uniquePeople.set(person.entity_id, person)
    }
    return [...uniquePeople.values()]
  })

  const faceCountQueries = useQueries({
    queries: computed(() =>
      pageRecords.value.map((person) => ({
        queryKey: queryKeys.faces.list({
          'filter.entity_id': [person.entity_id],
          limit: 1,
          return_total_count: true,
        }),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          fetchFaces(
            {
              'filter.entity_id': [person.entity_id],
              limit: 1,
              return_total_count: true,
            },
            signal,
          ),
        staleTime: PEOPLE_CACHE_TIME,
        gcTime: PEOPLE_GC_TIME,
      })),
    ),
  })
  const mentionCountQueries = useQueries({
    queries: computed(() =>
      pageRecords.value.map((person) => ({
        queryKey: queryKeys.textMentions.list({
          'filter.entity_id': [person.entity_id],
          limit: 1,
          return_total_count: true,
        }),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          fetchTextMentions(
            {
              'filter.entity_id': [person.entity_id],
              limit: 1,
              return_total_count: true,
            },
            signal,
          ),
        staleTime: PEOPLE_CACHE_TIME,
        gcTime: PEOPLE_GC_TIME,
      })),
    ),
  })

  const people = computed<PeopleSearchItem[]>(() =>
    pageRecords.value.map((person, index) => ({
      id: person.entity_id,
      name: person.name || 'Unnamed person',
      aliases: person.aliases ?? [],
      faces: faceCountQueries.value[index]?.data?.total_count ?? 0,
      names: mentionCountQueries.value[index]?.data?.total_count ?? 0,
    })),
  )

  return {
    error: peopleQuery.error,
    hasNextPage: peopleQuery.hasNextPage,
    isFetchingNextPage: peopleQuery.isFetchingNextPage,
    isLoading: peopleQuery.isPending,
    loadMore: peopleQuery.fetchNextPage,
    people,
    resultCount: computed(() => {
      if (normalizedSearch.value) return pageRecords.value.length
      return peopleQuery.data.value?.pages[0]?.totalCount ?? 0
    }),
  }
}
