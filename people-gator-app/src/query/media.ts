import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
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
  getPageLayoutByIdRouteApiV1PagesPageSourceIdPageLayoutGet,
  getPageRouteApiV1PagesPageSourceIdGet,
  getSourceRouteApiV1SourcesSourceIdGet,
  getTextMentionSpansByIdRouteApiV1PagesPageSourceIdTextMentionsSpansGet,
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

export function useDocumentsQuery(params?: MaybeRefOrGetter<DocumentListParams | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.documents.list(toValue(params))),
    queryFn: ({ signal }) => fetchDocuments(toValue(params), signal),
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

export function usePagesQuery(params?: MaybeRefOrGetter<PageListParams | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.pages.list(toValue(params))),
    queryFn: ({ signal }) => fetchPages(toValue(params), signal),
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
) {
  return useQuery({
    queryKey: computed(() => queryKeys.pages.image(toValue(sourceId), toValue(width))),
    queryFn: ({ signal }) => fetchPageImage(toValue(sourceId), toValue(width), signal),
    enabled: computed(() => Boolean(toValue(sourceId))),
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function usePageLayoutQuery(sourceId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.pages.layout(toValue(sourceId))),
    queryFn: ({ signal }) =>
      responseData(
        getPageLayoutByIdRouteApiV1PagesPageSourceIdPageLayoutGet({
          path: { page_source_id: toValue(sourceId) },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(toValue(sourceId))),
  })
}

export function usePageMentionSpansQuery(sourceId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.pages.mentionSpans(toValue(sourceId))),
    queryFn: ({ signal }) =>
      responseData(
        getTextMentionSpansByIdRouteApiV1PagesPageSourceIdTextMentionsSpansGet({
          path: { page_source_id: toValue(sourceId) },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(toValue(sourceId))),
  })
}

export function useImagesQuery(params?: MaybeRefOrGetter<ImageListParams | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.images.list(toValue(params))),
    queryFn: ({ signal }) =>
      responseData(
        listImagesRouteApiV1ImagesGet({ query: toValue(params), signal, throwOnError: true }),
      ),
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

export function useSourcesQuery(params?: MaybeRefOrGetter<SourceListParams | undefined>) {
  return useQuery({
    queryKey: computed(() => queryKeys.sources.list(toValue(params))),
    queryFn: ({ signal }) => fetchSources(toValue(params), signal),
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
