import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  createFaceRouteApiV1FacesPost,
  createFaceBatchRouteApiV1FacesBatchPost,
  getFaceAlignedCropRouteApiV1FacesDetectionIdAlignedCropGet,
  getFaceRouteApiV1FacesDetectionIdGet,
  listFacesRouteApiV1FacesGet,
  patchFaceEntityRouteApiV1FacesDetectionIdPatch,
  type FaceCreateRequest,
  type ListFacesRouteApiV1FacesGetData,
} from '@/client'
import { responseData } from '@/query/api'
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
    queryKey: computed(() => queryKeys.faces.alignedCrop(toValue(detectionId), toValue(maxWidth))),
    queryFn: ({ signal }) => fetchFaceAlignedCrop(toValue(detectionId), toValue(maxWidth), signal),
    enabled: computed(() => Boolean(toValue(detectionId))),
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useFacesQuery(params?: MaybeRefOrGetter<FaceListParams | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.faces.list(toValue(params))),
    queryFn: ({ signal }) => fetchFaces(toValue(params), signal),
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
      responseData(createFaceRouteApiV1FacesPost({ body, throwOnError: true })),
    onSuccess: (face) => {
      queryClient.setQueryData(queryKeys.faces.detail(face.detection_id), face)
      void queryClient.invalidateQueries({ queryKey: queryKeys.faces.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
    },
  })
}

export function useCreateFacesMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: FaceCreateRequest[]) =>
      responseData(createFaceBatchRouteApiV1FacesBatchPost({ body, throwOnError: true })),
    onSuccess: (faces) => {
      for (const face of faces) {
        queryClient.setQueryData(queryKeys.faces.detail(face.detection_id), face)
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.faces.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
    },
  })
}

export function useAssignFaceMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ detectionId, entityId }: { detectionId: string; entityId: string }) =>
      responseData(
        patchFaceEntityRouteApiV1FacesDetectionIdPatch({
          path: { detection_id: detectionId },
          body: { entity_id: entityId },
          throwOnError: true,
        }),
      ),
    onSuccess: (face) => {
      queryClient.setQueryData(queryKeys.faces.detail(face.detection_id), face)
      void queryClient.invalidateQueries({ queryKey: queryKeys.faces.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
    },
  })
}
