import type { EvidenceQuery } from './evidence-filters'
import { useQueries } from '@tanstack/vue-query'
import { watch, computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { linkMetadata } from '@/lib/entity-links'
import { listSortParams, sortParams, type SortState } from '@/lib/sorting'
import { FACE_DEFAULT } from '@/viewmodels/sort-options'
import {
  type EntityLinkState,
  type EntitySortField,
  type FaceSortField,
  type BoundingBox,
  type EntityType,
  type PageLayoutModel,
  type TextMentionSpanModel,
} from '@/client'
import type {
  Face,
  TranscriptionEntitySpan,
  TranscriptionLine,
} from '@/viewmodels/document-workspace.types'
import { lineMentionsEntity, transcriptionEntityKey } from '@/viewmodels/document-workspace.types'
import type { SimilarPersonCandidate } from '@/viewmodels/similar-people.types'
import { useCreateEntityMutation, useEntityListQuery } from '@/query/entities'
import { fetchFaceAlignedCrop, useAssignFaceMutation, useFaceListQuery } from '@/query/faces'
import { usePageImageQuery, usePageLookupQuery } from '@/query/media'
import { usePageLayoutQuery, usePageMentionSpansQuery } from '@/query/pages'
import { useObjectUrl, useObjectUrlMap } from '@/composables/object-url'
import { queryKeys } from '@/query/keys'
import { useEntitySearchQuery, type EntitySearchRecord } from '@/query/search'
import { useTextMentionListQuery } from '@/query/text-mentions'
import { candidateSearchParams, type CandidateBrowseMode } from '@/viewmodels/similar-people'

function percentage(value: number) {
  return Math.round((value <= 1 ? value * 100 : value) * 10) / 10
}

function bounds(points: number[][]) {
  const xs = points.map((point) => point[0] ?? 0)
  const ys = points.map((point) => point[1] ?? 0)
  const left = Math.min(...xs)
  const top = Math.min(...ys)
  return {
    left,
    top,
    width: Math.max(...xs) - left,
    height: Math.max(...ys) - top,
  }
}

function toPercentBox(box: BoundingBox, dimensions: { width: number; height: number } | null) {
  if (!dimensions) return { left: 0, top: 0, width: 0, height: 0 }
  const pageHeight = dimensions.height
  const pageWidth = dimensions.width
  return {
    left: (box.x / pageWidth) * 100,
    top: (box.y / pageHeight) * 100,
    width: (box.width / pageWidth) * 100,
    height: (box.height / pageHeight) * 100,
  }
}

function spanFragments(
  span: TextMentionSpanModel,
  lines: Array<{ id: string; text: string }>,
): TranscriptionEntitySpan[] {
  if (!span.entity_type) return []
  const startLineIndex = lines.findIndex((line) => line.id === span.start_line_id)
  const endLineIndex = lines.findIndex((line) => line.id === span.end_line_id)
  if (startLineIndex < 0 || endLineIndex < startLineIndex) return []

  return lines.slice(startLineIndex, endLineIndex + 1).flatMap((line, offset) => {
    const index = startLineIndex + offset
    const start = index === startLineIndex ? span.start_character : 0
    const end = index === endLineIndex ? span.end_character : line.text.length
    const text = line.text.slice(start, end)
    if (!text) return []
    return [
      {
        ...linkMetadata(span),
        mention_id: span.mention_id,
        firstFragment: offset === 0,
        entity_id: span.entity_id,
        label: span.entity_type as EntityType,
        text,
        line_id: line.id,
        start_index: start,
        end_index: end,
      },
    ]
  })
}

function makeTranscription(layout?: PageLayoutModel, spans: TextMentionSpanModel[] = []) {
  if (!layout) return []
  const pageHeight = layout.page_size[0] || 1
  const pageWidth = layout.page_size[1] || 1
  const orderedRegions = [...layout.regions].sort(
    (left, right) =>
      (layout.reading_order[left.id] ?? Number.MAX_SAFE_INTEGER) -
      (layout.reading_order[right.id] ?? Number.MAX_SAFE_INTEGER),
  )
  const rawLines = orderedRegions.flatMap((region) =>
    [...region.lines]
      .sort((left, right) => (left.index ?? 0) - (right.index ?? 0))
      .filter((line) => line.transcription?.trim())
      .map((line) => ({ id: line.id, text: line.transcription ?? '', polygon: line.polygon })),
  )
  const fragments = spans.flatMap((span) => spanFragments(span, rawLines))

  return rawLines.map<TranscriptionLine>((line) => {
    const box = bounds(line.polygon)
    return {
      id: line.id,
      text: line.text,
      position: {
        left: (box.left / pageWidth) * 100,
        top: (box.top / pageHeight) * 100,
        width: (box.width / pageWidth) * 100,
        height: (box.height / pageHeight) * 100,
      },
      entities: fragments.filter((fragment) => fragment.line_id === line.id),
    }
  })
}

export function useDocumentWorkspace(
  library: MaybeRefOrGetter<string>,
  documentId: MaybeRefOrGetter<string>,
  pageId: MaybeRefOrGetter<string>,
  selectedFaceId: MaybeRefOrGetter<string | null>,
  candidateTerm: MaybeRefOrGetter<string>,
  candidateBrowseMode: MaybeRefOrGetter<CandidateBrowseMode> = 'page',
  linkStates: MaybeRefOrGetter<EntityLinkState[]> = [],
  evidence: MaybeRefOrGetter<EvidenceQuery> = {},
  evidenceValid: MaybeRefOrGetter<boolean> = true,
  faceSort: MaybeRefOrGetter<SortState<FaceSortField>> = FACE_DEFAULT,
  candidateSort?: MaybeRefOrGetter<SortState<EntitySortField> | undefined>,
) {
  const pageQuery = usePageLookupQuery(library, documentId, pageId)
  const sourceId = computed(() => pageQuery.data.value?.source_id ?? '')
  const hasPage = computed(() => Boolean(sourceId.value) && toValue(evidenceValid))
  const layoutQuery = usePageLayoutQuery(sourceId)
  const spanQuery = usePageMentionSpansQuery(sourceId, linkStates, evidence)
  const faceQuery = useFaceListQuery(
    computed(() => ({
      ...toValue(evidence),
      'filter.source_id': [sourceId.value],
      'filter.entity_link_state': toValue(linkStates).length ? toValue(linkStates) : undefined,
      ...listSortParams(toValue(faceSort)),
      limit: 100,
    })),
    hasPage,
  )
  const faceRecords = computed(() =>
    (faceQuery.data.value?.pages ?? []).flatMap((page) => page.items),
  )
  const candidateOrder = computed(() => toValue(candidateSort))
  const onPageEntityQuery = useEntityListQuery(
    computed(() => ({
      ...toValue(evidence),
      'filter.source_id': [sourceId.value],
      'filter.entity_link_state': toValue(linkStates).length ? toValue(linkStates) : undefined,
      ...(candidateOrder.value && listSortParams(candidateOrder.value)),
      limit: 100,
    })),
    hasPage,
  )
  const onPageEntityRecords = computed(() =>
    (onPageEntityQuery.data.value?.pages ?? []).flatMap((page) => page.items),
  )
  const mentionQuery = useTextMentionListQuery(
    computed(() => ({
      ...toValue(evidence),
      'filter.source_id': [sourceId.value],
      'filter.entity_link_state': toValue(linkStates).length ? toValue(linkStates) : undefined,
      limit: 100,
    })),
    hasPage,
  )
  const mentions = computed(() =>
    (mentionQuery.data.value?.pages ?? []).flatMap((page) => page.items),
  )
  for (const query of [faceQuery, mentionQuery, onPageEntityQuery]) {
    watch(
      () => [query.data.value, query.hasNextPage.value, query.isFetchingNextPage.value],
      () => {
        if (query.hasNextPage.value && !query.isFetchingNextPage.value && !query.isError.value)
          void query.fetchNextPage()
      },
    )
  }
  const layoutDimensions = computed(() => {
    const size = layoutQuery.data.value?.page_size
    return size && size[0] > 0 && size[1] > 0 ? { height: size[0], width: size[1] } : null
  })
  // Face boxes use original pixels. A resized derivative cannot supply those
  // dimensions when OCR is absent, so request the original in that case.
  const pageImageQuery = usePageImageQuery(
    sourceId,
    computed(() => (layoutDimensions.value ? 1024 : undefined)),
    computed(() => !layoutQuery.isPending.value),
  )
  const pageImageUrl = useObjectUrl(computed(() => pageImageQuery.data.value))
  const imageDimensions = ref<{ width: number; height: number } | null>(null)
  watch(
    [sourceId, () => pageImageQuery.data.value],
    () => {
      imageDimensions.value = null
    },
    { flush: 'sync' },
  )
  function pageImageLoaded(event: Event) {
    const image = event.target as HTMLImageElement
    if (image.src !== pageImageUrl.value || image.naturalWidth <= 0 || image.naturalHeight <= 0)
      return
    imageDimensions.value = { width: image.naturalWidth, height: image.naturalHeight }
  }
  const annotationDimensions = computed(() => layoutDimensions.value ?? imageDimensions.value)

  // Aligned face crops (ArcFace-aligned, 1:1) are fetched per detection and
  // used as the face portraits instead of the full page image.
  const faceIds = computed(() => faceRecords.value.map((face) => face.detection_id))
  const alignedCropQueries = useQueries({
    queries: computed(() =>
      faceIds.value.map((detectionId) => ({
        queryKey: queryKeys.faceCrops.aligned(detectionId, 256),
        queryFn: ({ signal }: { signal: AbortSignal }) =>
          fetchFaceAlignedCrop(detectionId, 256, signal),
        staleTime: Number.POSITIVE_INFINITY,
        retry: false,
      })),
    ),
  })
  const alignedCropBlobs = computed(() => {
    const result = new Map<string, Blob>()
    faceIds.value.forEach((detectionId, index) => {
      const blob = alignedCropQueries.value[index]?.data
      if (blob instanceof Blob) result.set(detectionId, blob)
    })
    return result
  })
  const alignedCropUrls = useObjectUrlMap(alignedCropBlobs)

  // Source-filtered entities are authoritative for the "On this page" state;
  // ranked entity search results do not expose source membership.

  const faces = computed<Face[]>(() =>
    faceRecords.value.map((face, index) => {
      const person = face.entity_id
        ? onPageEntityRecords.value.find((entity) => entity.entity_id === face.entity_id)
        : undefined
      return {
        ...linkMetadata(face),
        id: face.detection_id,
        sourceId: face.source_id,
        embeddingModel: face.embeddings?.[0],
        personId: face.entity_id ?? null,
        name: person?.name || 'Unknown person',
        shortDescription: person?.short_description || undefined,
        wikidataId: person?.wikidata_id ?? undefined,
        nlcrAuthorityId: person?.nlcr_authority_id ?? undefined,
        confidence: percentage(face.confidence),
        status: face.entity_id ? 'assigned' : 'unassigned',
        portraitLoading: alignedCropQueries.value[index]?.isPending ?? false,
        position: toPercentBox(face.bounding_box, annotationDimensions.value),
        portrait: alignedCropUrls.value.get(face.detection_id) ?? pageImageUrl.value,
      }
    }),
  )
  const transcription = computed(() =>
    makeTranscription(layoutQuery.data.value ?? undefined, spanQuery.data.value),
  )

  const textTerm = computed(() => toValue(candidateTerm).trim())
  const selectedFaceEmbedding = computed(() => {
    const id = toValue(selectedFaceId)
    return faceRecords.value.find((face) => face.detection_id === id)?.embeddings?.[0]
  })
  const searchParams = computed(() =>
    candidateSearchParams(
      toValue(selectedFaceId),
      textTerm.value,
      selectedFaceEmbedding.value,
      toValue(candidateBrowseMode),
    ),
  )
  const resultMode = computed<'page' | 'face' | 'text'>(() =>
    textTerm.value ? 'text' : toValue(candidateBrowseMode),
  )
  const searchEnabled = computed(() => Boolean(searchParams.value))
  const candidateSearchQuery = useEntitySearchQuery(
    computed(() => ({
      ...(searchParams.value ?? { limit: 0 }),
      ...toValue(evidence),
      ...(candidateOrder.value && sortParams(candidateOrder.value)),
    })),
    computed(() => searchEnabled.value && toValue(evidenceValid)),
  )
  const candidateMatches = computed(() =>
    (candidateSearchQuery.data.value?.pages ?? []).flatMap((page) => page.items),
  )
  const onPageEntities = computed(
    () => new Map(onPageEntityRecords.value.map((entity) => [entity.entity_id, entity])),
  )
  const candidateRecords = computed<EntitySearchRecord[]>(() =>
    resultMode.value === 'page' ? onPageEntityRecords.value : candidateMatches.value,
  )

  const similarPeople = computed<SimilarPersonCandidate[]>(() => {
    const pageIds = new Set(onPageEntities.value.keys())
    const matches = candidateMatches.value
    const matchingScores = new Map(
      matches.map((entity) => [
        entity.entity_id,
        textTerm.value ? (entity.text_score ?? entity.score) : (entity.face_score ?? entity.score),
      ]),
    )
    const lines = transcription.value
    return candidateRecords.value.map((entity) => {
      const entityLineIndex = lines.findIndex((line) => lineMentionsEntity(line, entity.entity_id))
      const entitySpan =
        entityLineIndex >= 0
          ? lines[entityLineIndex]?.entities?.find((span) => span.entity_id === entity.entity_id)
          : undefined
      const nerMentions = mentions.value.filter(
        (mention) => mention.entity_id === entity.entity_id,
      ).length
      const detections = faces.value.filter((face) => face.personId === entity.entity_id).length
      const matchingScore = matchingScores.get(entity.entity_id)
      const normalizedFaceSimilarity =
        matchingScore === undefined
          ? undefined
          : matchingScore > 1
            ? matchingScore / 100
            : matchingScore
      const faceId =
        ('matched_detection_ids' in entity ? entity.matched_detection_ids?.[0] : undefined) ??
        faces.value.find((face) => face.personId === entity.entity_id)?.id
      return {
        id: entity.entity_id,
        sourceId: resultMode.value === 'page' ? sourceId.value : undefined,
        referenceFaceId: toValue(selectedFaceId) ?? undefined,
        candidateMode: resultMode.value,
        candidateText: textTerm.value || undefined,
        name: entity.name || 'Unnamed person',
        // Stores without persisted portraits (Weaviate) show the related face.
        thumbnailFaceId: entity.thumbnail_face_id ?? faceId,
        shortDescription: entity.short_description || undefined,
        score: matchingScore === undefined ? undefined : percentage(matchingScore),
        nerMentions,
        detections,
        source: pageIds.has(entity.entity_id) ? 'page' : 'database',
        matchSources: [
          ...(textTerm.value && matchingScore !== undefined
            ? ([{ type: 'text-search', score: percentage(matchingScore) }] as const)
            : []),
          ...(!textTerm.value && normalizedFaceSimilarity !== undefined
            ? ([
                {
                  type: 'face-match',
                  distance: Math.max(0, 1 - normalizedFaceSimilarity),
                },
              ] as const)
            : []),
          ...(nerMentions > 0 ? ([{ type: 'scan-text' }] as const) : []),
          ...(detections > 0 ? ([{ type: 'scan-face' }] as const) : []),
        ],
        wikidataId: entity.wikidata_id || undefined,
        nlcrAuthorityId: entity.nlcr_authority_id || undefined,
        faceId,
        entityKey: entitySpan ? transcriptionEntityKey(entitySpan) : undefined,
        entityLineIndex: entityLineIndex >= 0 ? entityLineIndex : undefined,
      }
    })
  })

  const hasNextPage = computed(() =>
    resultMode.value === 'page'
      ? onPageEntityQuery.hasNextPage.value
      : candidateSearchQuery.hasNextPage.value,
  )
  const isFetchingNextPage = computed(() =>
    resultMode.value === 'page'
      ? onPageEntityQuery.isFetchingNextPage.value
      : candidateSearchQuery.isFetchingNextPage.value,
  )

  function loadMore() {
    return resultMode.value === 'page'
      ? onPageEntityQuery.fetchNextPage()
      : candidateSearchQuery.fetchNextPage()
  }

  const createEntity = useCreateEntityMutation()
  const assignFaceMutation = useAssignFaceMutation()

  function assignFace(detectionId: string, entityId: string | null) {
    assignFaceMutation.mutate({ detectionId, entityId })
  }

  async function createAndAssign(detectionId: string, name: string, shortDescription?: string) {
    const entity = await createEntity.mutateAsync({
      entity_type: 'person',
      name,
      short_description: shortDescription || null,
    })
    await assignFaceMutation.mutateAsync({ detectionId, entityId: entity.entity_id })
    return entity
  }

  return {
    assignFace,
    unassignFace: (detectionId: string) => assignFace(detectionId, null),
    assignmentStatus: assignFaceMutation.status,
    createAndAssign,
    error: computed(
      () =>
        pageQuery.error.value ||
        layoutQuery.error.value ||
        spanQuery.error.value ||
        faceQuery.error.value ||
        mentionQuery.error.value ||
        (resultMode.value === 'page'
          ? onPageEntityQuery.error.value
          : candidateSearchQuery.error.value),
    ),
    faces,
    hasNextPage,
    isFetchingNextPage,
    isLoading: computed(
      () =>
        pageQuery.isPending.value ||
        layoutQuery.isPending.value ||
        spanQuery.isPending.value ||
        faceQuery.isPending.value ||
        mentionQuery.isPending.value,
    ),
    loadMore,
    page: pageQuery.data,
    annotationsLoading: computed(
      () => faceQuery.isPending.value || spanQuery.isPending.value || faceQuery.hasNextPage.value,
    ),
    pageDimensions: computed(() => annotationDimensions.value ?? { height: 297, width: 210 }),
    pageImageLoaded,
    pageImageReady: computed(() => imageDimensions.value !== null),
    pageImageLoading: pageImageQuery.isPending,
    pageImageError: computed(() => Boolean(pageImageQuery.error.value)),
    pageImageUrl,
    similarPeopleLoading: computed(
      () =>
        (resultMode.value === 'page' && onPageEntityQuery.isPending.value) ||
        (resultMode.value !== 'page' &&
          searchEnabled.value &&
          candidateSearchQuery.isPending.value),
    ),
    similarPeople,
    transcription,
  }
}
