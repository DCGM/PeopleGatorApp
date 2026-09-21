import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  createEntityRouteApiV1EntitiesPost,
  createEntityBatchRouteApiV1EntitiesBatchPost,
  deleteEntitiesRouteApiV1EntitiesDelete,
  deleteEntityRouteApiV1EntitiesEntityIdDelete,
  getEntityRouteApiV1EntitiesEntityIdGet,
  listEntitiesRouteApiV1EntitiesGet,
  patchEntityRouteApiV1EntitiesEntityIdPatch,
  type EntityCreateRequest,
  type EntityDeleteManyRequest,
  type EntityPatchRequest,
  type ListEntitiesRouteApiV1EntitiesGetData,
} from '@/client'
import { responseData } from '@/query/api'
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

export function useEntityListQuery(params?: MaybeRefOrGetter<EntityListParams | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.entities.list(toValue(params))),
    queryFn: ({ signal }) => fetchEntities(toValue(params), signal),
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
    },
  })
}

export function useDeleteEntitiesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: EntityDeleteManyRequest) =>
      responseData(deleteEntitiesRouteApiV1EntitiesDelete({ body, throwOnError: true })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.faces.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.textMentions.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
    },
  })
}
