import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  createTextMentionRouteApiV1TextMentionsPost,
  createTextMentionBatchRouteApiV1TextMentionsBatchPost,
  getTextMentionRouteApiV1TextMentionsMentionIdGet,
  listTextMentionsRouteApiV1TextMentionsGet,
  reassignTextMentionEntityRouteApiV1TextMentionsMentionIdPatch,
  type ListTextMentionsRouteApiV1TextMentionsGetData,
  type TextMentionCreateRequest,
} from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'

export type TextMentionListParams = NonNullable<
  ListTextMentionsRouteApiV1TextMentionsGetData['query']
>

export function fetchTextMentions(params?: TextMentionListParams, signal?: AbortSignal) {
  return responseData(
    listTextMentionsRouteApiV1TextMentionsGet({ query: params, signal, throwOnError: true }),
  )
}

export function useTextMentionsQuery(
  params?: MaybeRefOrGetter<TextMentionListParams | undefined>,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.textMentions.list(toValue(params))),
    queryFn: ({ signal }) => fetchTextMentions(toValue(params), signal),
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
      responseData(createTextMentionRouteApiV1TextMentionsPost({ body, throwOnError: true })),
    onSuccess: (mention) => {
      queryClient.setQueryData(queryKeys.textMentions.detail(mention.mention_id), mention)
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.all })
    },
  })
}

export function useCreateTextMentionsMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TextMentionCreateRequest[]) =>
      responseData(createTextMentionBatchRouteApiV1TextMentionsBatchPost({ body, throwOnError: true })),
    onSuccess: (mentions) => {
      for (const mention of mentions) {
        queryClient.setQueryData(queryKeys.textMentions.detail(mention.mention_id), mention)
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.all })
    },
  })
}

export function useReassignTextMentionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ mentionId, entityId }: { mentionId: string; entityId: string }) =>
      responseData(
        reassignTextMentionEntityRouteApiV1TextMentionsMentionIdPatch({
          path: { mention_id: mentionId },
          body: { entity_id: entityId },
          throwOnError: true,
        }),
      ),
    onSuccess: (mention) => {
      queryClient.setQueryData(queryKeys.textMentions.detail(mention.mention_id), mention)
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.all })
    },
  })
}
