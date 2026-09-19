import { useQuery } from '@tanstack/vue-query'

import { healthApiV1HealthGet, homeApiV1Get } from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.system.health(),
    queryFn: ({ signal }) => responseData(healthApiV1HealthGet({ signal, throwOnError: true })),
    staleTime: 30_000,
  })
}

export function useRootQuery() {
  return useQuery({
    queryKey: queryKeys.system.root(),
    queryFn: ({ signal }) => responseData(homeApiV1Get({ signal, throwOnError: true })),
    staleTime: Number.POSITIVE_INFINITY,
  })
}
