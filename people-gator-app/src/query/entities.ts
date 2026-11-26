import { isAxiosError } from 'axios'
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
import { invalidateEntityRecords, invalidateEvidence } from '@/query/invalidation'
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
      queryClient.setQueryData(queryKeys.entities.detail(entity.entity_id), entity)
      void invalidateEntityRecords(queryClient)
    },
  })
}

export function useCreateEntitiesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: EntityCreateRequest[]) =>
      responseData(createEntityBatchRouteApiV1EntitiesBatchPost({ body, throwOnError: true })),
    onSuccess: (entities) => {
      for (const entity of entities) {
        queryClient.setQueryData(queryKeys.entities.detail(entity.entity_id), entity)
      }
      void invalidateEntityRecords(queryClient)
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
      queryClient.setQueryData(queryKeys.entities.detail(entity.entity_id), entity)
      // The typed person record holds more fields; refetch it rather than overwrite.
      void invalidateEntityRecords(queryClient, [queryKeys.entities.person(entity.entity_id)])
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
      if (
        !targetEntityId ||
        !sourceEntityIds.length ||
        sourceEntityIds.some((id) => !id || id === targetEntityId) ||
        new Set(sourceEntityIds).size !== sourceEntityIds.length
      ) {
        throw new Error('Select distinct people and a target before merging.')
      }
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
    onError: async (error) => {
      if (!isAxiosError(error) || error.response?.status !== 404) return
      // Refetch every loaded page so valid later-page selections remain available.
      // Infinite queries derive fresh continuation cursors while refetching.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.entities.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.search.all }),
      ])
    },
    onSuccess: (result, { sourceEntityIds }) => {
      for (const sourceEntityId of sourceEntityIds) {
        queryClient.removeQueries({ queryKey: queryKeys.entities.detail(sourceEntityId) })
      }
      queryClient.setQueryData(
        queryKeys.entities.detail(result.target_entity_id),
        result.merged_entity,
      )
      return invalidateEvidence(queryClient)
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
      queryClient.removeQueries({ queryKey: queryKeys.entities.detail(entityId) })
      void invalidateEntityRecords(queryClient)
    },
  })
}

export function useDeleteEntitiesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: EntityDeleteManyRequest) =>
      responseData(deleteEntitiesRouteApiV1EntitiesDelete({ body, throwOnError: true })),
    onSuccess: () => invalidateEvidence(queryClient),
  })
}
