import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  createTextMentionRouteApiV1TextMentionsPost,
  createTextMentionBatchRouteApiV1TextMentionsBatchPost,
  getTextMentionRouteApiV1TextMentionsMentionIdGet,
  listTextMentionGroupsRouteApiV1TextMentionGroupsGet,
  listTextMentionsRouteApiV1TextMentionsGet,
  patchTextMentionRouteApiV1TextMentionsMentionIdPatch,
  type ListTextMentionGroupsRouteApiV1TextMentionGroupsGetData,
  type ListTextMentionsRouteApiV1TextMentionsGetData,
  type TextMentionCreateRequest,
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

export function useCreateTextMentionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TextMentionCreateRequest) =>
      responseData(
        createTextMentionRouteApiV1TextMentionsPost({
          body: {
            ...body,
            entity_link_state: 'manual',
          },
          throwOnError: true,
        }),
      ),
    onSuccess: (mention) => {
      queryClient.setQueryData(queryKeys.textMentions.detail(mention.mention_id), mention)
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.pages.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.sources.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.images.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.pages.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.faces.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.all })
    },
  })
}

export function useCreateTextMentionsMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TextMentionCreateRequest[]) =>
      responseData(
        createTextMentionBatchRouteApiV1TextMentionsBatchPost({
          body: body.map((item) => ({
            ...item,
            entity_link_state: 'manual',
          })),
          throwOnError: true,
        }),
      ),
    onSuccess: (mentions) => {
      for (const mention of mentions) {
        queryClient.setQueryData(queryKeys.textMentions.detail(mention.mention_id), mention)
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.pages.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.sources.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.images.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.pages.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.faces.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.all })
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.pages.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.sources.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.images.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.pages.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.faces.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.all })
    },
  })
}
