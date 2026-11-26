import { restartPeoplePages } from './people-count-invalidation'
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  createTextMentionRouteApiV1TextMentionsPost,
  createTextMentionBatchRouteApiV1TextMentionsBatchPost,
  deleteTextMentionBatchRouteApiV1TextMentionsBatchDelete,
  getTextMentionRouteApiV1TextMentionsMentionIdGet,
  listTextMentionGroupsRouteApiV1TextMentionGroupsGet,
  listTextMentionsRouteApiV1TextMentionsGet,
  patchTextMentionBatchRouteApiV1TextMentionsBatchPatch,
  patchTextMentionRouteApiV1TextMentionsMentionIdPatch,
  type ListTextMentionGroupsRouteApiV1TextMentionGroupsGetData,
  type ListTextMentionsRouteApiV1TextMentionsGetData,
  type TextMentionCreateRequest,
  type TextMentionResponse,
} from '@/client'
import { responseData } from '@/query/api'
import { initialCursor, nextCursor, withCursor, useFirstPageOnFilterChange } from '@/query/cursor'
import { queryKeys } from '@/query/keys'

export type TextMentionListParams = NonNullable<
  ListTextMentionsRouteApiV1TextMentionsGetData['query']
>

export function fetchTextMentions(params?: TextMentionListParams, signal?: AbortSignal) {
  return responseData(
    listTextMentionsRouteApiV1TextMentionsGet({ query: params, signal, throwOnError: true }),
  )
}

export function useTextMentionListQuery(
  params?: MaybeRefOrGetter<TextMentionListParams | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const key = computed(() => queryKeys.textMentions.infinite(toValue(params)))
  useFirstPageOnFilterChange(key)
  return useInfiniteQuery({
    queryKey: key,
    queryFn: ({ pageParam, signal }) =>
      fetchTextMentions(withCursor(toValue(params), pageParam), signal),
    initialPageParam: computed(() => initialCursor(params)),
    getNextPageParam: (lastPage, _pages, lastPageParam) => nextCursor(lastPage, lastPageParam),
    enabled: computed(() => toValue(enabled)),
  })
}

export type TextMentionGroupParams = NonNullable<
  ListTextMentionGroupsRouteApiV1TextMentionGroupsGetData['query']
>

export function fetchTextMentionGroups(params?: TextMentionGroupParams, signal?: AbortSignal) {
  return responseData(
    listTextMentionGroupsRouteApiV1TextMentionGroupsGet({
      query: params,
      signal,
      throwOnError: true,
    }),
  )
}

/** Exact recorded-text groups over the complete filtered mention set. */
export function useTextMentionGroupsQuery(
  params?: MaybeRefOrGetter<TextMentionGroupParams | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const key = computed(() => queryKeys.textMentions.groups(toValue(params)))
  useFirstPageOnFilterChange(key)
  return useInfiniteQuery({
    queryKey: key,
    queryFn: ({ pageParam, signal }) =>
      fetchTextMentionGroups(withCursor(toValue(params), pageParam), signal),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage, _pages, lastPageParam) => nextCursor(lastPage, lastPageParam),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useTextMentionQuery(mentionId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.textMentions.detail(toValue(mentionId))),
    queryFn: ({ signal }) =>
      responseData(
        getTextMentionRouteApiV1TextMentionsMentionIdGet({
          path: { mention_id: toValue(mentionId) },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(toValue(mentionId))),
  })
}

/** Every view that shows mentions, their people or their counts. */
export async function invalidateMentionEdits(queryClient: QueryClient) {
  restartPeoplePages(queryClient)
  await Promise.all(
    [
      queryKeys.textMentions.all,
      queryKeys.entities.all,
      queryKeys.pages.all,
      queryKeys.search.all,
      queryKeys.documents.all,
      queryKeys.sources.all,
      queryKeys.images.all,
      queryKeys.faces.all,
    ].map((queryKey) => queryClient.invalidateQueries({ queryKey })),
  )
}

/** A link state needs an entity: unlinked mentions are sent without one. */
function createBody(body: TextMentionCreateRequest): TextMentionCreateRequest {
  return body.entity_id ? { ...body, entity_link_state: 'manual' } : body
}

export function useCreateTextMentionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TextMentionCreateRequest) =>
      responseData(
        createTextMentionRouteApiV1TextMentionsPost({ body: createBody(body), throwOnError: true }),
      ),
    onSuccess: (mention) => {
      queryClient.setQueryData(queryKeys.textMentions.detail(mention.mention_id), mention)
      void invalidateMentionEdits(queryClient)
    },
  })
}

export function useCreateTextMentionsMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TextMentionCreateRequest[]) =>
      responseData(
        createTextMentionBatchRouteApiV1TextMentionsBatchPost({
          body: body.map(createBody),
          throwOnError: true,
        }),
      ),
    onSuccess: (mentions) => {
      for (const mention of mentions)
        queryClient.setQueryData(queryKeys.textMentions.detail(mention.mention_id), mention)
      void invalidateMentionEdits(queryClient)
    },
  })
}

export function useReassignTextMentionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ mentionId, entityId }: { mentionId: string; entityId: string | null }) =>
      responseData(
        patchTextMentionRouteApiV1TextMentionsMentionIdPatch({
          path: { mention_id: mentionId },
          body: { entity_id: entityId, entity_link_state: entityId ? 'manual' : null },
          throwOnError: true,
        }),
      ),
    onSuccess: (mention) => {
      queryClient.setQueryData(queryKeys.textMentions.detail(mention.mention_id), mention)
      void invalidateMentionEdits(queryClient)
    },
  })
}

/** The API's default batch limit is larger; smaller chunks report partial progress. */
const MENTION_CHUNK = 50

function chunks<T>(items: readonly T[]) {
  const result: T[][] = []
  for (let index = 0; index < items.length; index += MENTION_CHUNK)
    result.push(items.slice(index, index + MENTION_CHUNK))
  return result
}

/** Link mentions to a person (manual), or unlink them with null, in batches. */
export async function assignTextMentions(mentionIds: readonly string[], entityId: string | null) {
  const records: TextMentionResponse[] = []
  for (const ids of chunks([...new Set(mentionIds)])) {
    const updated = await responseData(
      patchTextMentionBatchRouteApiV1TextMentionsBatchPatch({
        body: ids.map((mention_id) => ({
          mention_id,
          entity_id: entityId,
          entity_link_state: entityId ? ('manual' as const) : null,
        })),
        throwOnError: true,
      }),
    )
    if (updated.some((record) => !record)) throw new Error('Mention unavailable')
    records.push(...(updated as TextMentionResponse[]))
  }
  return records
}

export function useAssignTextMentionsMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ mentionIds, entityId }: { mentionIds: readonly string[]; entityId: string | null }) =>
      assignTextMentions(mentionIds, entityId),
    onSuccess: (mentions) => {
      for (const mention of mentions)
        queryClient.setQueryData(queryKeys.textMentions.detail(mention.mention_id), mention)
    },
    onSettled: () => invalidateMentionEdits(queryClient),
  })
}

export function useDeleteTextMentionsMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (mentionIds: readonly string[]) => {
      let deleted = 0
      for (const ids of chunks([...new Set(mentionIds)]))
        deleted += await responseData(
          deleteTextMentionBatchRouteApiV1TextMentionsBatchDelete({
            body: ids,
            throwOnError: true,
          }),
        )
      return deleted
    },
    onSuccess: (_deleted, mentionIds) => {
      for (const id of mentionIds)
        queryClient.removeQueries({ queryKey: queryKeys.textMentions.detail(id), exact: true })
    },
    onSettled: () => invalidateMentionEdits(queryClient),
  })
}

/** Change which words a mention covers; its person link and verification stay. */
export function usePatchTextMentionTextMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ mentionId, name, context }: { mentionId: string; name: string; context: string }) =>
      responseData(
        patchTextMentionRouteApiV1TextMentionsMentionIdPatch({
          path: { mention_id: mentionId },
          body: { name, context },
          throwOnError: true,
        }),
      ),
    onSuccess: (mention) => {
      queryClient.setQueryData(queryKeys.textMentions.detail(mention.mention_id), mention)
      void invalidateMentionEdits(queryClient)
    },
  })
}
