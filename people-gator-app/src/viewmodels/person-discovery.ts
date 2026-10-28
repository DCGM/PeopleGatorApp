import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { EntityAnnotation, EntitySortField, FaceSortField, PageResponse } from '@/client'
import { sortParams, type SortState } from '@/lib/sorting'
import { RELEVANCE } from '@/viewmodels/sort-options'
import type {
  PersonDiscoveryCandidate,
  PersonDiscoveryFace,
} from '@/viewmodels/person-detail.types'
import { fetchEntity, useMergeEntitiesMutation } from '@/query/entities'
import { fetchFaceAlignedCrop, useAssignFacesMutation } from '@/query/faces'
import { queryKeys } from '@/query/keys'
import { fetchPage } from '@/query/media'
import { useObjectUrlMap } from '@/composables/object-url'
import { useEntitySearchQuery, useFaceSearchQuery } from '@/query/search'

const DISCOVERY_LIMIT = 40
const FACE_DISCOVERY_BATCH = 14
const DISCOVERY_GC_TIME = 60 * 60_000

function percentage(value: number) {
  return Math.round(value <= 1 ? value * 100 : value)
}

export const DISCOVERY_ANNOTATIONS: EntityAnnotation[] = ['faces', 'aliases', 'name']

export function personDiscoverySignals(
  entityId: string,
  faceEmbeddingModel: string | null,
  extraText: string,
  annotations: EntityAnnotation[] = DISCOVERY_ANNOTATIONS,
) {
  const text = extraText.trim()
  return {
    ...(annotations.length && {
      'query.entity_id': entityId,
      'query.entity_annotations': DISCOVERY_ANNOTATIONS.filter((item) =>
        annotations.includes(item),
      ),
    }),
    ...(text && { 'query.text': [text] }),
    ...(faceEmbeddingModel && { 'query.face_embedding_model': faceEmbeddingModel }),
    limit: DISCOVERY_LIMIT,
  }
}

type DiscoveryReference = { model: string | null; text: string; annotations: EntityAnnotation[] }

export function usePersonDiscovery(
  personId: MaybeRefOrGetter<string>,
  referenceFaceModel: MaybeRefOrGetter<string | null>,
  extraText: MaybeRefOrGetter<string>,
  enabled: MaybeRefOrGetter<boolean>,
  faceSort: MaybeRefOrGetter<SortState<FaceSortField>> = RELEVANCE,
  peopleSort: MaybeRefOrGetter<SortState<EntitySortField>> = RELEVANCE,
  annotations: MaybeRefOrGetter<EntityAnnotation[]> = DISCOVERY_ANNOTATIONS,
  peopleReference?: MaybeRefOrGetter<DiscoveryReference>,
  faceAssignment: MaybeRefOrGetter<'all' | 'assigned' | 'unassigned'> = 'all',
) {
  const signals = computed(() =>
    personDiscoverySignals(
      toValue(personId),
      toValue(referenceFaceModel),
      toValue(extraText),
      toValue(annotations),
    ),
  )
  const canSearch = computed(
    () =>
      toValue(enabled) && (toValue(annotations).length > 0 || Boolean(toValue(extraText).trim())),
  )
  const peopleSignals = computed(() => {
    const reference = peopleReference && toValue(peopleReference)
    return reference
      ? personDiscoverySignals(
          toValue(personId),
          reference.model,
          reference.text,
          reference.annotations,
        )
      : signals.value
  })
  const canSearchPeople = computed(() => {
    const reference = peopleReference && toValue(peopleReference)
    return reference
      ? toValue(enabled) && (reference.annotations.length > 0 || Boolean(reference.text.trim()))
      : canSearch.value
  })
  // Discovery searches all accessible data; shared browsing filters stay in the URL.
  const faceSearchQuery = useFaceSearchQuery(
    computed(() => ({
      ...signals.value,
      ...sortParams(toValue(faceSort)),
      limit: FACE_DISCOVERY_BATCH,
      return_total_count: true,
      ...(toValue(faceAssignment) !== 'all' && {
        'filter.is_assigned': toValue(faceAssignment) === 'assigned',
      }),
    })),
    canSearch,
  )

  const faceMatches = computed(() =>
    (faceSearchQuery.data.value?.pages ?? [])
      .flatMap((page) => page.items)
      .filter((face) => face.entity_id !== toValue(personId)),
  )
  const matchedFaceIds = computed(() => faceMatches.value.map((face) => face.detection_id))
  const matchedSourceIds = computed(() => [
    ...new Set(faceMatches.value.flatMap((face) => (face.source_id ? [face.source_id] : []))),
  ])
  const assignedEntityIds = computed(() => [
    ...new Set(faceMatches.value.flatMap((face) => (face.entity_id ? [face.entity_id] : []))),
  ])

  const assignedEntityQueries = useQueries({
    queries: computed(() =>
      assignedEntityIds.value.map((entityId) => ({
        queryKey: queryKeys.entities.detail(entityId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchEntity(entityId, signal),
        retry: false,
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: DISCOVERY_GC_TIME,
      })),
    ),
  })
  const assignedEntityNames = computed(() => {
    const names = new Map<string, string>()
    assignedEntityIds.value.forEach((entityId, index) => {
      const entity = assignedEntityQueries.value[index]?.data
      names.set(entityId, entity?.name || entityId)
    })
    return names
  })

  const matchedCropQueries = useQueries({
    queries: computed(() =>
      matchedFaceIds.value.map((faceId) => ({
        queryKey: queryKeys.faceCrops.aligned(faceId, 320),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchFaceAlignedCrop(faceId, 320, signal),
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: DISCOVERY_GC_TIME,
        retry: false,
      })),
    ),
  })
  const matchedCropBlobs = computed(() => {
    const blobs = new Map<string, Blob>()
    matchedFaceIds.value.forEach((faceId, index) => {
      const blob = matchedCropQueries.value[index]?.data
      if (blob instanceof Blob) blobs.set(faceId, blob)
    })
    return blobs
  })
  const matchedCropUrls = useObjectUrlMap(matchedCropBlobs)

  const matchedPageQueries = useQueries({
    queries: computed(() =>
      matchedSourceIds.value.map((sourceId) => ({
        queryKey: queryKeys.pages.detail(sourceId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchPage(sourceId, signal),
        retry: false,
        staleTime: Number.POSITIVE_INFINITY,
        gcTime: DISCOVERY_GC_TIME,
      })),
    ),
  })
  const matchedPages = computed(() => {
    const pages = new Map<string, PageResponse>()
    matchedSourceIds.value.forEach((sourceId, index) => {
      const page = matchedPageQueries.value[index]?.data
      if (page) pages.set(sourceId, page)
    })
    return pages
  })

  const similarFaces = computed<PersonDiscoveryFace[]>(() =>
    faceMatches.value.map((face, index) => {
      const page = face.source_id ? matchedPages.value.get(face.source_id) : undefined
      return {
        id: face.detection_id,
        portrait: matchedCropUrls.value.get(face.detection_id) ?? '',
        portraitLoading:
          !matchedCropUrls.value.has(face.detection_id) &&
          (matchedCropQueries.value[index]?.isPending ?? false),
        score: face.face_score == null ? null : percentage(face.face_score),
        assignedEntityId: face.entity_id ?? null,
        assignedEntityName: face.entity_id
          ? (assignedEntityNames.value.get(face.entity_id) ?? face.entity_id)
          : undefined,
        library: page?.library,
        documentId: page?.document_id,
        pageUrl: page?.url,
        pageId: page?.page_id,
        pageLabel: page?.page_id,
      }
    }),
  )

  const entitySearchParams = computed(() => ({
    ...peopleSignals.value,
    'filter.entity_type': ['person'] as Array<'person'>,
    ...sortParams(toValue(peopleSort)),
  }))
  const entitySearchQuery = useEntitySearchQuery(entitySearchParams, canSearchPeople)
  const entityMatches = computed(() =>
    (entitySearchQuery.data.value?.pages ?? [])
      .flatMap((page) => page.items)
      .filter(
        (entity) => entity.entity_id !== toValue(personId) && entity.entity_type === 'person',
      ),
  )

  const similarPeople = computed<PersonDiscoveryCandidate[]>(() =>
    entityMatches.value.map((entity) => {
      return {
        id: entity.entity_id,
        matchedFaceIds: entity.matched_detection_ids ?? [],
        textMatch: entity.text_score != null,
        name: entity.name || 'Unnamed person',
        shortDescription: entity.short_description || '',
        aliases: entity.aliases ?? [],
        // Stores without persisted portraits (Weaviate) show the matched face.
        thumbnailFaceId: entity.thumbnail_face_id ?? entity.matched_detection_ids?.[0],
      }
    }),
  )

  const assignFacesMutation = useAssignFacesMutation()
  const mergeEntitiesMutation = useMergeEntitiesMutation()

  return {
    assignFaces: (faceIdsToAssign: string[]) => {
      if (!faceIdsToAssign.length) return
      assignFacesMutation.mutate({
        detectionIds: [...new Set(faceIdsToAssign)],
        entityId: toValue(personId),
      })
    },
    assignmentStatus: assignFacesMutation.status,
    mergePeople: (sourceEntityIds: string[]) => {
      const uniqueSourceIds = [...new Set(sourceEntityIds)].filter((id) => id !== toValue(personId))
      if (!uniqueSourceIds.length) return
      mergeEntitiesMutation.mutate({
        targetEntityId: toValue(personId),
        sourceEntityIds: uniqueSourceIds,
      })
    },
    mergeStatus: mergeEntitiesMutation.status,
    searchError: computed(
      () =>
        (faceSearchQuery.isFetchNextPageError?.value ? null : faceSearchQuery.error.value) ??
        entitySearchQuery.error.value,
    ),
    isLoadingFaces: computed(
      () =>
        canSearch.value && (faceSearchQuery.isPending.value || faceSearchQuery.isFetching.value),
    ),
    isLoadingPeople: computed(
      () =>
        canSearchPeople.value &&
        (entitySearchQuery.isPending.value || entitySearchQuery.isFetching.value),
    ),
    retry: () => {
      void faceSearchQuery.refetch()
      void entitySearchQuery.refetch()
    },
    similarFaces,
    hasMoreFaces: faceSearchQuery.hasNextPage,
    loadingMoreFaces: faceSearchQuery.isFetchingNextPage,
    moreFacesFailed: faceSearchQuery.isFetchNextPageError,
    foundFaceCount: computed(
      () => faceSearchQuery.data.value?.pages[0]?.totalCount ?? similarFaces.value.length,
    ),
    loadMoreFaces: () => faceSearchQuery.fetchNextPage(),
    similarPeople,
  }
}
