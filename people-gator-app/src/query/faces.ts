import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  deleteFaceRouteApiV1FacesDetectionIdDelete,
  createFaceRouteApiV1FacesPost,
  createFaceBatchRouteApiV1FacesBatchPost,
  getFaceAlignedCropRouteApiV1FacesDetectionIdAlignedCropGet,
  getFaceRouteApiV1FacesDetectionIdGet,
  listFacesRouteApiV1FacesGet,
  patchFaceBatchRouteApiV1FacesBatchPatch,
  patchFaceRouteApiV1FacesDetectionIdPatch,
  type FaceCreateRequest,
  type ListFacesRouteApiV1FacesGetData,
} from '@/client'
import { responseData } from '@/query/api'
import { initialCursor, nextCursor, withCursor, useFirstPageOnFilterChange } from '@/query/cursor'
import { invalidateEvidence } from '@/query/invalidation'
import { queryKeys } from '@/query/keys'

export type FaceListParams = NonNullable<ListFacesRouteApiV1FacesGetData['query']>

export function fetchFaces(params?: FaceListParams, signal?: AbortSignal) {
  return responseData(listFacesRouteApiV1FacesGet({ query: params, signal, throwOnError: true }))
}

export function fetchFace(detectionId: string, signal?: AbortSignal) {
  return responseData(
    getFaceRouteApiV1FacesDetectionIdGet({
      path: { detection_id: detectionId },
      signal,
      throwOnError: true,
    }),
  )
}

export function fetchFaceAlignedCrop(detectionId: string, maxWidth?: number, signal?: AbortSignal) {
  return responseData(
    getFaceAlignedCropRouteApiV1FacesDetectionIdAlignedCropGet({
      path: { detection_id: detectionId },
      query: maxWidth ? { max_width: maxWidth } : undefined,
      responseType: 'blob',
      signal,
      throwOnError: true,
    }),
  ) as Promise<Blob>
}

export function useFaceAlignedCropQuery(
  detectionId: MaybeRefOrGetter<string>,
  maxWidth?: MaybeRefOrGetter<number | undefined>,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.faceCrops.aligned(toValue(detectionId), toValue(maxWidth))),
    queryFn: ({ signal }) => fetchFaceAlignedCrop(toValue(detectionId), toValue(maxWidth), signal),
    enabled: computed(() => Boolean(toValue(detectionId))),
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 60 * 60_000,
    retry: false,
  })
}

export function useFaceListQuery(
  params?: MaybeRefOrGetter<FaceListParams | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const key = computed(() => queryKeys.faces.infinite(toValue(params)))
  useFirstPageOnFilterChange(key)
  return useInfiniteQuery({
    queryKey: key,
    queryFn: ({ pageParam, signal }) => fetchFaces(withCursor(toValue(params), pageParam), signal),
    initialPageParam: computed(() => initialCursor(params)),
    getNextPageParam: (lastPage, _pages, lastPageParam) => nextCursor(lastPage, lastPageParam),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useFaceQuery(detectionId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.faces.detail(toValue(detectionId))),
    queryFn: ({ signal }) => fetchFace(toValue(detectionId), signal),
    enabled: computed(() => Boolean(toValue(detectionId))),
  })
}

export function useCreateFaceMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: FaceCreateRequest) =>
      responseData(
        createFaceRouteApiV1FacesPost({
          body: {
            ...body,
            ...(body.entity_id && { entity_link_state: 'manual' }),
          },
          throwOnError: true,
        }),
      ),
    onSuccess: (face) => {
      queryClient.setQueryData(queryKeys.faces.detail(face.detection_id), face)
      void invalidateEvidence(queryClient)
    },
  })
}

export function useCreateFacesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: FaceCreateRequest[]) =>
      responseData(
        createFaceBatchRouteApiV1FacesBatchPost({
          body: body.map((item) => ({
            ...item,
            ...(item.entity_id && { entity_link_state: 'manual' as const }),
          })),
          throwOnError: true,
        }),
      ),
    onSuccess: (faces) => {
      for (const face of faces) {
        queryClient.setQueryData(queryKeys.faces.detail(face.detection_id), face)
      }
      void invalidateEvidence(queryClient)
    },
  })
}

export function useAssignFaceMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ detectionId, entityId }: { detectionId: string; entityId: string | null }) =>
      responseData(
        patchFaceRouteApiV1FacesDetectionIdPatch({
          path: { detection_id: detectionId },
          body: { entity_id: entityId, entity_link_state: entityId ? 'manual' : null },
          throwOnError: true,
        }),
      ),
    onSuccess: (face) => {
      queryClient.setQueryData(queryKeys.faces.detail(face.detection_id), face)
      void invalidateEvidence(queryClient)
    },
  })
}

export function useAssignFacesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ detectionIds, entityId }: { detectionIds: string[]; entityId: string }) =>
      responseData(
        patchFaceBatchRouteApiV1FacesBatchPatch({
          body: detectionIds.map((detectionId) => ({
            detection_id: detectionId,
            entity_id: entityId,
            entity_link_state: 'manual',
          })),
          throwOnError: true,
        }),
      ),
    onSuccess: (faces) => {
      for (const face of faces) {
        if (!face) continue
        queryClient.setQueryData(queryKeys.faces.detail(face.detection_id), face)
      }
    },
    onSettled: () => invalidateEvidence(queryClient),
  })
}

export function useReviewFacesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      detectionIds,
      action,
    }: {
      detectionIds: string[]
      action: 'verify' | 'unassign'
    }) => {
      const faces = await responseData(
        patchFaceBatchRouteApiV1FacesBatchPatch({
          body: [...new Set(detectionIds)].map((detection_id) => ({
            detection_id,
            ...(action === 'verify'
              ? { entity_link_state: 'verified' as const }
              : { entity_id: null, entity_link_state: null }),
          })),
          throwOnError: true,
        }),
      )
      for (const face of faces) {
        if (face) queryClient.setQueryData(queryKeys.faces.detail(face.detection_id), face)
      }
      if (faces.some((face) => face === null))
        throw new Error('Some selected faces are no longer available.')
      return faces
    },
    onSettled: () => invalidateEvidence(queryClient),
  })
}

export function useDeleteFaceMutation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (detectionId: string) =>
      responseData(
        deleteFaceRouteApiV1FacesDetectionIdDelete({
          path: { detection_id: detectionId },
          throwOnError: true,
        }),
      ),
    onSuccess: async (_data, detectionId) => {
      // A deleted detail must not remain available as a selected reference face.
      client.removeQueries({ queryKey: queryKeys.faces.detail(detectionId), exact: true })
      client.removeQueries({ queryKey: queryKeys.faceCrops.detection(detectionId) })
      await invalidateEvidence(client)
    },
  })
}
