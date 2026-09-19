import { useInfiniteQuery, useQueries, type InfiniteData, type QueryKey } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { EntityResponse, SearchEntitiesResult } from '@/client'
import { fetchEntities } from '@/query/entities'
import { fetchFaces } from '@/query/faces'
import { queryKeys } from '@/query/keys'
import { fetchEntitySearch } from '@/query/search'
import { fetchTextMentions } from '@/query/text-mentions'

export type PeopleSearchItem = {
  id: string
  name: string
  aliases: string[]
  faces: number
  names: number
}

type PersonRecord = EntityResponse | SearchEntitiesResult
type PeoplePage = {
  items: PersonRecord[]
  totalCount: number
  nextPage: string | number | undefined
}

const PEOPLE_CACHE_TIME = 10 * 60_000
const PEOPLE_GC_TIME = 60 * 60_000

export function usePeopleSearch(
  searchTerm: MaybeRefOrGetter<string>,
  filter: MaybeRefOrGetter<string>,
  pageSize = 12,
) {
  const normalizedSearch = computed(() => toValue(searchTerm).trim())
  const peopleQuery = useInfiniteQuery<
    PeoplePage,
    Error,
    InfiniteData<PeoplePage, string | number>,
    QueryKey,
    string | number
  >({
    queryKey: computed(() =>
      normalizedSearch.value
        ? queryKeys.search.infiniteEntities({ q: normalizedSearch.value, limit: pageSize })
        : queryKeys.entities.infinite({ limit: pageSize }),
    ),
    queryFn: async ({ pageParam, signal }): Promise<PeoplePage> => {
      if (normalizedSearch.value) {
        // The search endpoint currently ignores `after_id` and reports only the
        // requested limit as its total. Grow the request by one page and retain
        // only the new slice so TanStack Query can still provide load-more data.
        const pageIndex = typeof pageParam === 'number' ? pageParam : 0
        const pageEnd = (pageIndex + 1) * pageSize
        const response = await fetchEntitySearch(
          { q: [normalizedSearch.value], limit: pageEnd + 1 },
          signal,
        )
        const hasNextPage = response.items.length > pageEnd

        return {
          items: response.items.slice(pageIndex * pageSize, pageEnd),
          totalCount: hasNextPage ? pageEnd + 1 : response.items.length,
          nextPage: hasNextPage ? pageIndex + 1 : undefined,
        }
      }

      const response = await fetchEntities(
        {
          limit: pageSize,
          after_id: typeof pageParam === 'string' ? pageParam : undefined,
        },
        signal,
      )
      return {
        items: response.items,
        totalCount: response.total_count,
        nextPage: response.after_id ?? undefined,
      }
    },
    initialPageParam: 0 as string | number,
    getNextPageParam: (lastPage) => lastPage.nextPage,
    staleTime: PEOPLE_CACHE_TIME,
    gcTime: PEOPLE_GC_TIME,
    refetchOnWindowFocus: false,
  })

  const pageRecords = computed<PersonRecord[]>(() => {
    const uniquePeople = new Map<string, PersonRecord>()
    for (const page of peopleQuery.data.value?.pages ?? []) {
      for (const person of page.items) uniquePeople.set(person.entity_id, person)
    }
    return [...uniquePeople.values()]
  })

  const faceCountQueries = useQueries({
    queries: computed(() =>
      pageRecords.value.map((person) => ({
        queryKey: queryKeys.faces.list({ entity_id: person.entity_id, limit: 1 }),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          fetchFaces({ entity_id: person.entity_id, limit: 1 }, signal),
        staleTime: PEOPLE_CACHE_TIME,
        gcTime: PEOPLE_GC_TIME,
      })),
    ),
  })
  const mentionCountQueries = useQueries({
    queries: computed(() =>
      pageRecords.value.map((person) => ({
        queryKey: queryKeys.textMentions.list({ entity_id: person.entity_id, limit: 1 }),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          fetchTextMentions({ entity_id: person.entity_id, limit: 1 }, signal),
        staleTime: PEOPLE_CACHE_TIME,
        gcTime: PEOPLE_GC_TIME,
      })),
    ),
  })

  const people = computed<PeopleSearchItem[]>(() =>
    pageRecords.value
      .map((person, index) => ({
        id: person.entity_id,
        name: person.name || 'Unnamed person',
        aliases: person.aliases ?? [],
        faces: faceCountQueries.value[index]?.data?.total_count ?? 0,
        names: mentionCountQueries.value[index]?.data?.total_count ?? 0,
      }))
      .filter((person) => {
        if (toValue(filter) === 'faces') return person.faces > 0
        if (toValue(filter) === 'names') return person.names > 0
        return true
      }),
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
