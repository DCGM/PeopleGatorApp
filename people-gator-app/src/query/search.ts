import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  searchDocumentsGetApiV1SearchDocumentsGet,
  searchEntitiesGetApiV1SearchEntitiesGet,
  searchFacesGetApiV1SearchFacesGet,
  searchPagesGetApiV1SearchPagesGet,
  type SearchDocumentsGetApiV1SearchDocumentsGetData,
  type SearchEntitiesGetApiV1SearchEntitiesGetData,
  type SearchFacesGetApiV1SearchFacesGetData,
  type SearchPagesGetApiV1SearchPagesGetData,
} from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'

export type EntitySearchParams = NonNullable<SearchEntitiesGetApiV1SearchEntitiesGetData['query']>
export type FaceSearchParams = NonNullable<SearchFacesGetApiV1SearchFacesGetData['query']>
export type PageSearchParams = SearchPagesGetApiV1SearchPagesGetData['query']
export type DocumentSearchParams = SearchDocumentsGetApiV1SearchDocumentsGetData['query']

export function fetchEntitySearch(params: EntitySearchParams, signal?: AbortSignal) {
  return responseData(
    searchEntitiesGetApiV1SearchEntitiesGet({ query: params, signal, throwOnError: true }),
  )
}

export function fetchFaceSearch(params: FaceSearchParams, signal?: AbortSignal) {
  return responseData(
    searchFacesGetApiV1SearchFacesGet({ query: params, signal, throwOnError: true }),
  )
}

export function fetchPageSearch(params: PageSearchParams, signal?: AbortSignal) {
  return responseData(
    searchPagesGetApiV1SearchPagesGet({ query: params, signal, throwOnError: true }),
  )
}

export function useEntitySearchQuery(
  params: MaybeRefOrGetter<EntitySearchParams>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.search.entities(toValue(params))),
    queryFn: ({ signal }) => fetchEntitySearch(toValue(params), signal),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useFaceSearchQuery(
  params: MaybeRefOrGetter<FaceSearchParams>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.search.faces(toValue(params))),
    queryFn: ({ signal }) => fetchFaceSearch(toValue(params), signal),
    enabled: computed(() => toValue(enabled)),
  })
}

export function usePageSearchQuery(
  params: MaybeRefOrGetter<PageSearchParams>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.search.pages(toValue(params))),
    queryFn: ({ signal }) => fetchPageSearch(toValue(params), signal),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useDocumentSearchQuery(
  params: MaybeRefOrGetter<DocumentSearchParams>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.search.documents(toValue(params))),
    queryFn: ({ signal }) =>
      responseData(
        searchDocumentsGetApiV1SearchDocumentsGet({
          query: toValue(params),
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => toValue(enabled)),
  })
}
