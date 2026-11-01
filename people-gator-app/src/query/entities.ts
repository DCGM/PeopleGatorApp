import { restartPeoplePages } from './people-count-invalidation'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  createEntityRouteApiV1EntitiesPost,
  createEntityBatchRouteApiV1EntitiesBatchPost,
  deleteEntitiesRouteApiV1EntitiesDelete,
  deleteEntityRouteApiV1EntitiesEntityIdDelete,
  getEntityRouteApiV1EntitiesEntityIdGet,
  listEntitiesRouteApiV1EntitiesGet,
  mergeEntityBatchRouteApiV1EntitiesTargetEntityIdMergeBatchPost,
  mergeEntityRouteApiV1EntitiesTargetEntityIdMergePost,
  patchEntityRouteApiV1EntitiesEntityIdPatch,
  type EntityCreateRequest,
  type EntityDeleteManyRequest,
  type EntityPatchRequest,
  type ListEntitiesRouteApiV1EntitiesGetData,
} from '@/client'
import { responseData } from '@/query/api'
import { initialCursor, nextCursor, withCursor } from '@/query/cursor'
import { queryKeys } from '@/query/keys'

export type EntityListParams = NonNullable<ListEntitiesRouteApiV1EntitiesGetData['query']>

export function fetchEntities(params?: EntityListParams, signal?: AbortSignal) {
  return responseData(
    listEntitiesRouteApiV1EntitiesGet({ query: params, signal, throwOnError: true }),
  )
}

export function fetchEntity(entityId: string, signal?: AbortSignal) {
  return responseData(
    getEntityRouteApiV1EntitiesEntityIdGet({
      path: { entity_id: entityId },
      signal,
      throwOnError: true,
    }),
  )
}

export function useEntityListQuery(
  params?: MaybeRefOrGetter<EntityListParams | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.entities.infinite(toValue(params))),
    queryFn: ({ pageParam, signal }) =>
      fetchEntities(withCursor(toValue(params), pageParam), signal),
    initialPageParam: computed(() => initialCursor(params)),
    getNextPageParam: (lastPage, _pages, lastPageParam) => nextCursor(lastPage, lastPageParam),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useEntityQuery(entityId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.entities.detail(toValue(entityId))),
    queryFn: ({ signal }) => fetchEntity(toValue(entityId), signal),
    enabled: computed(() => Boolean(toValue(entityId))),
  })
}

export function useCreateEntityMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: EntityCreateRequest) =>
      responseData(createEntityRouteApiV1EntitiesPost({ body, throwOnError: true })),
    onSuccess: (entity) => {
      restartPeoplePages(queryClient)
      queryClient.setQueryData(queryKeys.entities.detail(entity.entity_id), entity)
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.lists() })
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

export function useCreateEntitiesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: EntityCreateRequest[]) =>
      responseData(createEntityBatchRouteApiV1EntitiesBatchPost({ body, throwOnError: true })),
    onSuccess: (entities) => {
      restartPeoplePages(queryClient)
      for (const entity of entities) {
        queryClient.setQueryData(queryKeys.entities.detail(entity.entity_id), entity)
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.lists() })
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

export function usePatchEntityMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ entityId, body }: { entityId: string; body: EntityPatchRequest }) =>
      responseData(
        patchEntityRouteApiV1EntitiesEntityIdPatch({
          path: { entity_id: entityId },
          body,
          throwOnError: true,
        }),
      ),
    onSuccess: (entity) => {
      restartPeoplePages(queryClient)
      queryClient.setQueryData(queryKeys.entities.detail(entity.entity_id), entity)
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.lists() })
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

export function useMergeEntitiesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      targetEntityId,
      sourceEntityIds,
    }: {
      targetEntityId: string
      sourceEntityIds: string[]
    }) => {
      if (sourceEntityIds.length === 1) {
        return await responseData(
          mergeEntityRouteApiV1EntitiesTargetEntityIdMergePost({
            path: { target_entity_id: targetEntityId },
            body: { source_entity_id: sourceEntityIds[0]! },
            throwOnError: true,
          }),
        )
      }
      return await responseData(
        mergeEntityBatchRouteApiV1EntitiesTargetEntityIdMergeBatchPost({
          path: { target_entity_id: targetEntityId },
          body: { source_entity_ids: sourceEntityIds },
          throwOnError: true,
        }),
      )
    },
    onSuccess: (result, { sourceEntityIds }) => {
      restartPeoplePages(queryClient)
      for (const sourceEntityId of sourceEntityIds) {
        queryClient.removeQueries({ queryKey: queryKeys.entities.detail(sourceEntityId) })
      }
      queryClient.setQueryData(
        queryKeys.entities.detail(result.target_entity_id),
        result.merged_entity,
      )
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.entities.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.faces.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.search.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.documents.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.sources.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.images.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.pages.all }),
      ])
    },
  })
}

export function useDeleteEntityMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (entityId: string) =>
      responseData(
        deleteEntityRouteApiV1EntitiesEntityIdDelete({
          path: { entity_id: entityId },
          throwOnError: true,
        }),
      ),
    onSuccess: (_data, entityId) => {
      restartPeoplePages(queryClient)
      queryClient.removeQueries({ queryKey: queryKeys.entities.detail(entityId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.lists() })
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

export function useDeleteEntitiesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: EntityDeleteManyRequest) =>
      responseData(deleteEntitiesRouteApiV1EntitiesDelete({ body, throwOnError: true })),
    onSuccess: () => {
      restartPeoplePages(queryClient)
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.faces.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.all })
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
