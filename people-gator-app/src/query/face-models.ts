import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { listFaceModelsRouteApiV1FaceModelsGet } from '@/client'
import { responseData } from './api'

export function useFaceModels(enabled: MaybeRefOrGetter<boolean> = true) {
  return useQuery({
    queryKey: ['face-models'],
    queryFn: ({ signal }) =>
      responseData(listFaceModelsRouteApiV1FaceModelsGet({ signal, throwOnError: true })),
    enabled: computed(() => toValue(enabled)),
  })
}
