import { restartPeoplePages } from './people-count-invalidation'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { isAxiosError } from 'axios'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  patchPageRouteApiV1PagesPageSourceIdPatch,
  type PagePatchRequest,
  createDocumentRouteApiV1DocumentsPost,
  createDocumentBatchRouteApiV1DocumentsBatchPost,
  createImageRouteApiV1ImagesPost,
  createImageBatchRouteApiV1ImagesBatchPost,
  createPageRouteApiV1PagesPost,
  createPageBatchRouteApiV1PagesBatchPost,
  deleteDocumentRouteApiV1DocumentsDocumentSourceIdDelete,
  deleteImageRouteApiV1ImagesImageIdDelete,
  deletePageRouteApiV1PagesPageSourceIdDelete,
  deleteSourceRouteApiV1SourcesSourceIdDelete,
  getDocumentRouteApiV1DocumentsDocumentSourceIdGet,
  getImageContentByIdRouteApiV1ImagesImageIdContentGet,
  getImageRouteApiV1ImagesImageIdGet,
  getPageImageByIdRouteApiV1PagesPageSourceIdImageGet,
  getPageRouteApiV1PagesPageSourceIdGet,
  getSourceRouteApiV1SourcesSourceIdGet,
  listDocumentsRouteApiV1DocumentsGet,
  listImagesRouteApiV1ImagesGet,
  listPagesRouteApiV1PagesGet,
  listSourcesRouteApiV1SourcesGet,
  lookupDocumentRouteApiV1DocumentsLookupGet,
  lookupImageRouteApiV1ImagesLookupGet,
  lookupPageRouteApiV1PagesLookupGet,
  lookupSourceRouteApiV1SourcesLookupGet,
  type DocumentCreateRequest,
  type ImageCreateRequest,
  type ListDocumentsRouteApiV1DocumentsGetData,
  type ListImagesRouteApiV1ImagesGetData,
  type ListPagesRouteApiV1PagesGetData,
  type ListSourcesRouteApiV1SourcesGetData,
  type PageCreateRequest,
} from '@/client'
import { responseData } from '@/query/api'
import { initialCursor, nextCursor, withCursor } from '@/query/cursor'
import { queryKeys } from '@/query/keys'

export type DocumentListParams = NonNullable<ListDocumentsRouteApiV1DocumentsGetData['query']>
export type PageListParams = NonNullable<ListPagesRouteApiV1PagesGetData['query']>
export type ImageListParams = NonNullable<ListImagesRouteApiV1ImagesGetData['query']>
export type SourceListParams = NonNullable<ListSourcesRouteApiV1SourcesGetData['query']>

export function fetchDocuments(params?: DocumentListParams, signal?: AbortSignal) {
  return responseData(
    listDocumentsRouteApiV1DocumentsGet({ query: params, signal, throwOnError: true }),
  )
}

export function fetchPages(params?: PageListParams, signal?: AbortSignal) {
  return responseData(listPagesRouteApiV1PagesGet({ query: params, signal, throwOnError: true }))
}

export function fetchSources(params?: SourceListParams, signal?: AbortSignal) {
  return responseData(
    listSourcesRouteApiV1SourcesGet({ query: params, signal, throwOnError: true }),
  )
}

export function fetchPage(sourceId: string, signal?: AbortSignal) {
  return responseData(
    getPageRouteApiV1PagesPageSourceIdGet({
      path: { page_source_id: sourceId },
      signal,
      throwOnError: true,
    }),
  )
}

export function fetchPageImage(sourceId: string, width?: number, signal?: AbortSignal) {
  return responseData(
    getPageImageByIdRouteApiV1PagesPageSourceIdImageGet({
      path: { page_source_id: sourceId },
      query: width ? { width } : undefined,
      responseType: 'blob',
      signal,
      throwOnError: true,
    }),
  ) as Promise<Blob>
}

export function useDocumentListQuery(
  params?: MaybeRefOrGetter<DocumentListParams | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.documents.infinite(toValue(params))),
    queryFn: ({ pageParam, signal }) =>
      fetchDocuments(withCursor(toValue(params), pageParam), signal),
    initialPageParam: computed(() => initialCursor(params)),
    getNextPageParam: (lastPage, _pages, lastPageParam) => nextCursor(lastPage, lastPageParam),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useDocumentQuery(sourceId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.documents.detail(toValue(sourceId))),
    queryFn: ({ signal }) =>
      responseData(
        getDocumentRouteApiV1DocumentsDocumentSourceIdGet({
          path: { document_source_id: toValue(sourceId) },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(toValue(sourceId))),
  })
}

export function useDocumentLookupQuery(
  library: MaybeRefOrGetter<string>,
  documentId: MaybeRefOrGetter<string>,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.documents.lookup(toValue(library), toValue(documentId))),
    queryFn: ({ signal }) =>
      responseData(
        lookupDocumentRouteApiV1DocumentsLookupGet({
          query: { library: toValue(library), document_id: toValue(documentId) },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(toValue(library) && toValue(documentId))),
  })
}

export function usePageListQuery(
  params?: MaybeRefOrGetter<PageListParams | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.pages.infinite(toValue(params))),
    queryFn: ({ pageParam, signal }) => fetchPages(withCursor(toValue(params), pageParam), signal),
    initialPageParam: computed(() => initialCursor(params)),
    getNextPageParam: (lastPage, _pages, lastPageParam) => nextCursor(lastPage, lastPageParam),
    enabled: computed(() => toValue(enabled)),
  })
}

export function usePageQuery(sourceId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.pages.detail(toValue(sourceId))),
    queryFn: ({ signal }) => fetchPage(toValue(sourceId), signal),
    enabled: computed(() => Boolean(toValue(sourceId))),
  })
}

export function usePageLookupQuery(
  library: MaybeRefOrGetter<string>,
  documentId: MaybeRefOrGetter<string>,
  pageId: MaybeRefOrGetter<string>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.pages.lookup(toValue(library), toValue(documentId), toValue(pageId)),
    ),
    queryFn: ({ signal }) =>
      responseData(
        lookupPageRouteApiV1PagesLookupGet({
          query: {
            library: toValue(library),
            document_id: toValue(documentId),
            page_id: toValue(pageId),
          },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(toValue(library) && toValue(documentId) && toValue(pageId))),
  })
}

export function usePageImageQuery(
  sourceId: MaybeRefOrGetter<string>,
  width?: MaybeRefOrGetter<number | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.pages.image(toValue(sourceId), toValue(width))),
    queryFn: ({ signal }) => fetchPageImage(toValue(sourceId), toValue(width), signal),
    enabled: computed(() => Boolean(toValue(sourceId)) && toValue(enabled)),
    staleTime: Number.POSITIVE_INFINITY,
    // A registered page without stored media is a definite state, not a transient failure.
    retry: (failures, error) =>
      !(isAxiosError(error) && error.response?.status === 404) && failures < 3,
  })
}

export function useImageListQuery(
  params?: MaybeRefOrGetter<ImageListParams | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.images.infinite(toValue(params))),
    queryFn: ({ pageParam, signal }) =>
      responseData(
        listImagesRouteApiV1ImagesGet({
          query: withCursor(toValue(params), pageParam),
          signal,
          throwOnError: true,
        }),
      ),
    initialPageParam: computed(() => initialCursor(params)),
    getNextPageParam: (lastPage, _pages, lastPageParam) => nextCursor(lastPage, lastPageParam),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useImageQuery(imageId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.images.detail(toValue(imageId))),
    queryFn: ({ signal }) =>
      responseData(
        getImageRouteApiV1ImagesImageIdGet({
          path: { image_id: toValue(imageId) },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(toValue(imageId))),
  })
}

export function useImageContentQuery(imageId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.images.content(toValue(imageId))),
    queryFn: ({ signal }) =>
      responseData(
        getImageContentByIdRouteApiV1ImagesImageIdContentGet({
          path: { image_id: toValue(imageId) },
          responseType: 'blob',
          signal,
          throwOnError: true,
        }),
      ) as Promise<Blob>,
    enabled: computed(() => Boolean(toValue(imageId))),
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useImageLookupQuery(url: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.images.lookup(toValue(url))),
    queryFn: ({ signal }) =>
      responseData(
        lookupImageRouteApiV1ImagesLookupGet({
          query: { url: toValue(url) },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(toValue(url))),
  })
}

export function useSourceListQuery(
  params?: MaybeRefOrGetter<SourceListParams | undefined>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.sources.infinite(toValue(params))),
    queryFn: ({ pageParam, signal }) =>
      fetchSources(withCursor(toValue(params), pageParam), signal),
    initialPageParam: computed(() => initialCursor(params)),
    getNextPageParam: (lastPage, _pages, lastPageParam) => nextCursor(lastPage, lastPageParam),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useSourceQuery(sourceId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.sources.detail(toValue(sourceId))),
    queryFn: ({ signal }) =>
      responseData(
        getSourceRouteApiV1SourcesSourceIdGet({
          path: { source_id: toValue(sourceId) },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(toValue(sourceId))),
  })
}

export function useSourceLookupQuery(url: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.sources.lookup(toValue(url))),
    queryFn: ({ signal }) =>
      responseData(
        lookupSourceRouteApiV1SourcesLookupGet({
          query: { url: toValue(url) },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(toValue(url))),
  })
}

function useMediaInvalidation() {
  const queryClient = useQueryClient()
  return () => {
    restartPeoplePages(queryClient)
    void queryClient.invalidateQueries({ queryKey: queryKeys.entities.all })
    void queryClient.invalidateQueries({ queryKey: ['people-filter-options', 'library'] })
    void queryClient.invalidateQueries({ queryKey: ['people-filter-options', 'document'] })
    void queryClient.invalidateQueries({ queryKey: queryKeys.documents.all })
    void queryClient.invalidateQueries({ queryKey: queryKeys.pages.all })
    void queryClient.invalidateQueries({ queryKey: queryKeys.images.all })
    void queryClient.invalidateQueries({ queryKey: queryKeys.sources.all })
    void queryClient.invalidateQueries({ queryKey: queryKeys.search.all })
  }
}

export function useCreateDocumentMutation() {
  const invalidate = useMediaInvalidation()
  return useMutation({
    mutationFn: (body: DocumentCreateRequest) =>
      responseData(createDocumentRouteApiV1DocumentsPost({ body, throwOnError: true })),
    onSuccess: invalidate,
  })
}

export function useCreateDocumentsMutation() {
  const invalidate = useMediaInvalidation()
  return useMutation({
    mutationFn: (body: DocumentCreateRequest[]) =>
      responseData(createDocumentBatchRouteApiV1DocumentsBatchPost({ body, throwOnError: true })),
    onSuccess: invalidate,
  })
}

export function useCreatePageMutation() {
  const invalidate = useMediaInvalidation()
  return useMutation({
    mutationFn: (body: PageCreateRequest) =>
      responseData(createPageRouteApiV1PagesPost({ body, throwOnError: true })),
    onSuccess: invalidate,
  })
}

export function useCreatePagesMutation() {
  const invalidate = useMediaInvalidation()
  return useMutation({
    mutationFn: (body: PageCreateRequest[]) =>
      responseData(createPageBatchRouteApiV1PagesBatchPost({ body, throwOnError: true })),
    onSuccess: invalidate,
  })
}

export function useCreateImageMutation() {
  const invalidate = useMediaInvalidation()
  return useMutation({
    mutationFn: (body: ImageCreateRequest) =>
      responseData(createImageRouteApiV1ImagesPost({ body, throwOnError: true })),
    onSuccess: invalidate,
  })
}

export function useCreateImagesMutation() {
  const invalidate = useMediaInvalidation()
  return useMutation({
    mutationFn: (body: ImageCreateRequest[]) =>
      responseData(createImageBatchRouteApiV1ImagesBatchPost({ body, throwOnError: true })),
    onSuccess: invalidate,
  })
}

export function useDeleteDocumentMutation() {
  const invalidate = useMediaInvalidation()
  return useMutation({
    mutationFn: (sourceId: string) =>
      responseData(
        deleteDocumentRouteApiV1DocumentsDocumentSourceIdDelete({
          path: { document_source_id: sourceId },
          throwOnError: true,
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useDeletePageMutation() {
  const invalidate = useMediaInvalidation()
  return useMutation({
    mutationFn: (sourceId: string) =>
      responseData(
        deletePageRouteApiV1PagesPageSourceIdDelete({
          path: { page_source_id: sourceId },
          throwOnError: true,
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useDeleteImageMutation() {
  const invalidate = useMediaInvalidation()
  return useMutation({
    mutationFn: (imageId: string) =>
      responseData(
        deleteImageRouteApiV1ImagesImageIdDelete({
          path: { image_id: imageId },
          throwOnError: true,
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useDeleteSourceMutation() {
  const invalidate = useMediaInvalidation()
  return useMutation({
    mutationFn: (sourceId: string) =>
      responseData(
        deleteSourceRouteApiV1SourcesSourceIdDelete({
          path: { source_id: sourceId },
          throwOnError: true,
        }),
      ),
    onSuccess: invalidate,
  })
}

/** Query keys whose cursor chains depend on page order. */
const PAGE_ORDERED_LISTS = [
  queryKeys.pages.lists(),
  ['pages', 'results'],
  ['search', 'pages'],
  queryKeys.documents.lists(),
  ['search', 'documents'],
] as const

/**
 * Discard ordered cursor chains after a numbering edit; keep the edited page,
 * images, layouts and spans cached so the workspace does not reload.
 */
export function usePageNumberMutation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ sourceId, payload }: { sourceId: string; payload: PagePatchRequest }) =>
      responseData(
        patchPageRouteApiV1PagesPageSourceIdPatch({
          path: { page_source_id: sourceId },
          body: payload,
          throwOnError: true,
        }),
      ),
    onSuccess: async (page) => {
      client.setQueryData(queryKeys.pages.detail(page.source_id), page)
      client.setQueryData(
        queryKeys.pages.lookup(page.library, page.document_id, page.page_id),
        page,
      )
      await Promise.all([
        ...PAGE_ORDERED_LISTS.map((queryKey) => client.resetQueries({ queryKey })),
        client.invalidateQueries({ queryKey: ['documents', 'detail'] }),
        client.invalidateQueries({ queryKey: ['documents', 'lookup'] }),
      ])
    },
  })
}
