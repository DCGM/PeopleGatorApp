import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { EntityResponse, TextMentionResponse } from '@/client'
import { fetchEntity } from '@/query/entities'
import { queryKeys } from '@/query/keys'
import { useTextMentionListQuery, type TextMentionListParams } from '@/query/text-mentions'

export const SCAN_MENTION_BATCH_SIZE = 25

export type MentionPersonGroup = {
  key: string
  personId: string | null
  records: TextMentionResponse[]
}

/**
 * Group mentions by linked person in arrival order; unlinked mentions form one
 * group. Person order keeps groups contiguous across batches, and a key that
 * arrives again joins its existing group, so no group section repeats.
 */
export function groupMentionsByPerson(records: TextMentionResponse[]): MentionPersonGroup[] {
  const groups = new Map<string, MentionPersonGroup>()
  for (const record of records) {
    const personId = record.entity_id ?? null
    const key = personId ?? 'unlinked'
    const group = groups.get(key) ?? { key, personId, records: [] }
    group.records.push(record)
    groups.set(key, group)
  }
  // Unlinked mentions are unknown to the person order and stay last.
  return [...groups.values()].sort(
    (left, right) => Number(left.personId === null) - Number(right.personId === null),
  )
}

/** The scope's mentions in person order, paged and grouped by linked person. */
export function useScanMentionsByPerson(
  filters: MaybeRefOrGetter<TextMentionListParams>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const query = useTextMentionListQuery(
    computed(() => ({
      ...toValue(filters),
      sort: 'person' as const,
      sort_direction: 'asc' as const,
      limit: SCAN_MENTION_BATCH_SIZE,
      return_total_count: true,
    })),
    enabled,
  )
  const records = computed(() => {
    const seen = new Set<string>()
    return (query.data.value?.pages ?? [])
      .flatMap((page) => page.items)
      .filter((record) => !seen.has(record.mention_id) && Boolean(seen.add(record.mention_id)))
  })
  const personIds = computed(() => [
    ...new Set(records.value.flatMap((record) => (record.entity_id ? [record.entity_id] : []))),
  ])
  const people = useQueries({
    queries: computed(() =>
      personIds.value.map((entityId) => ({
        queryKey: queryKeys.entities.detail(entityId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchEntity(entityId, signal),
        staleTime: 60_000,
      })),
    ),
  })
  const names = computed(() => {
    const result = new Map<string, EntityResponse>()
    personIds.value.forEach((entityId, index) => {
      const person = people.value[index]?.data
      if (person) result.set(entityId, person)
    })
    return result
  })
  return {
    groups: computed(() => groupMentionsByPerson(records.value)),
    personName: (personId: string | null) =>
      personId ? names.value.get(personId)?.name || 'Linked person' : 'Unlinked',
    totalCount: computed(() => query.data.value?.pages[0]?.total_count ?? undefined),
    loading: computed(() => query.isPending.value),
    hasNextPage: computed(() => query.hasNextPage.value),
    isFetching: computed(() => query.isFetching.value),
    error: computed(() => query.error.value),
    loadMore: () => query.fetchNextPage(),
    retry: () => query.refetch(),
  }
}
