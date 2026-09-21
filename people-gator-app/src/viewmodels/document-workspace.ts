import { useQueries, useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  getPageLayoutByIdRouteApiV1PagesPageSourceIdPageLayoutGet,
  getTextMentionSpansByIdRouteApiV1PagesPageSourceIdTextMentionsSpansGet,
  type BoundingBox,
  type EntityResponse,
  type EntityType,
  type PageLayoutModel,
  type TextMentionSpanModel,
} from '@/client'
import type {
  Face,
  TranscriptionEntitySpan,
  TranscriptionLine,
} from '@/viewmodels/document-workspace.types'
import { transcriptionEntityKey } from '@/viewmodels/document-workspace.types'
import type { SimilarPersonCandidate } from '@/viewmodels/similar-people.types'
import { responseData } from '@/query/api'
import { fetchEntity, useCreateEntityMutation } from '@/query/entities'
import { fetchFaces, fetchFaceAlignedCrop, useAssignFaceMutation } from '@/query/faces'
import { usePageImageQuery, usePageLookupQuery } from '@/query/media'
import { useObjectUrl, useObjectUrlMap } from '@/composables/object-url'
import { queryKeys } from '@/query/keys'
import { fetchEntitySearch } from '@/query/search'
import {
  candidateEntities,
  candidateSearchParams,
  currentPagePersonIds,
} from '@/viewmodels/similar-people'

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

function toPercentBox(box: BoundingBox, layout?: PageLayoutModel) {
  const pageHeight = layout?.page_size[0] || 1
  const pageWidth = layout?.page_size[1] || 1
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
) {
  const pageQuery = usePageLookupQuery(library, documentId, pageId)
  const sourceId = computed(() => pageQuery.data.value?.page_source_id ?? '')

  const layoutQuery = useQuery({
    queryKey: computed(() => queryKeys.pages.layout(sourceId.value)),
    queryFn: ({ signal }) =>
      responseData(
        getPageLayoutByIdRouteApiV1PagesPageSourceIdPageLayoutGet({
          path: { page_source_id: sourceId.value },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(sourceId.value)),
  })
  const spanQuery = useQuery({
    queryKey: computed(() => queryKeys.pages.mentionSpans(sourceId.value)),
    queryFn: ({ signal }) =>
      responseData(
        getTextMentionSpansByIdRouteApiV1PagesPageSourceIdTextMentionsSpansGet({
          path: { page_source_id: sourceId.value },
          signal,
          throwOnError: true,
        }),
      ),
    enabled: computed(() => Boolean(sourceId.value)),
  })
  const faceQuery = useQuery({
    queryKey: computed(() => queryKeys.faces.list({ source_id: sourceId.value, limit: 100 })),
    queryFn: ({ signal }) => fetchFaces({ source_id: sourceId.value, limit: 100 }, signal),
    enabled: computed(() => Boolean(sourceId.value)),
  })
  const pageImageQuery = usePageImageQuery(sourceId, 1024)
  const pageImageUrl = useObjectUrl(computed(() => pageImageQuery.data.value))

  // Aligned face crops (ArcFace-aligned, 1:1) are fetched per detection and
  // used as the face portraits instead of the full page image.
  const faceIds = computed(() =>
    (faceQuery.data.value?.items ?? []).map((face) => face.detection_id),
  )
  const alignedCropQueries = useQueries({
    queries: computed(() =>
      faceIds.value.map((detectionId) => ({
        queryKey: queryKeys.faces.alignedCrop(detectionId, 256),
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

  // The page's faces and OCR spans both carry the page source_id. These are
  // authoritative for the "On this page" filter; entity search results do not
  // expose source membership and the search endpoint ignores source_id today.
  const onPageEntityIds = computed(() =>
    currentPagePersonIds(faceQuery.data.value?.items ?? [], spanQuery.data.value ?? []),
  )
  const onPageEntityQueries = useQueries({
    queries: computed(() =>
      onPageEntityIds.value.map((entityId) => ({
        queryKey: queryKeys.entities.detail(entityId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchEntity(entityId, signal),
        retry: false,
      })),
    ),
  })
  const onPageEntities = computed(() => {
    const result = new Map<string, EntityResponse>()
    onPageEntityIds.value.forEach((entityId, index) => {
      const entity = onPageEntityQueries.value[index]?.data
      if (entity) result.set(entityId, entity)
    })
    return result
  })

  const faces = computed<Face[]>(() =>
    (faceQuery.data.value?.items ?? []).map((face, index) => {
      const person = face.entity_id ? onPageEntities.value.get(face.entity_id) : undefined
      return {
        id: face.detection_id,
        personId: face.entity_id ?? null,
        name: person?.name || 'Unknown person',
        shortDescription: person?.short_description || undefined,
        wikidataId: person?.wikidata_id ?? undefined,
        nlcrAuthorityId: person?.nlcr_authority_id ?? undefined,
        confidence: percentage(face.confidence),
        status: face.entity_id ? 'assigned' : 'unassigned',
        portraitLoading: alignedCropQueries.value[index]?.isPending ?? false,
        position: toPercentBox(face.bounding_box, layoutQuery.data.value),
        portrait: alignedCropUrls.value.get(face.detection_id) ?? pageImageUrl.value,
      }
    }),
  )
  const transcription = computed(() =>
    makeTranscription(layoutQuery.data.value, spanQuery.data.value),
  )

  const textTerm = computed(() => toValue(candidateTerm).trim())
  const searchParams = computed(() =>
    candidateSearchParams(toValue(selectedFaceId), textTerm.value),
  )
  const candidateSearchQuery = useQuery({
    queryKey: computed(() => queryKeys.search.entities(searchParams.value)),
    queryFn: ({ signal }) => fetchEntitySearch(searchParams.value!, signal),
    enabled: computed(() => Boolean(searchParams.value)),
    // Reuse the face result when switching between face and text modes.
    // Assignment mutations invalidate search queries when the data changes.
    staleTime: Number.POSITIVE_INFINITY,
  })
  const candidateDetailIds = computed(() =>
    (candidateSearchQuery.data.value?.items ?? []).map((entity) => entity.entity_id),
  )
  const candidateDetailQueries = useQueries({
    queries: computed(() =>
      candidateDetailIds.value.map((entityId) => ({
        queryKey: queryKeys.entities.detail(entityId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchEntity(entityId, signal),
        retry: false,
      })),
    ),
  })
  const candidateDetails = computed(() => {
    const result = new Map<string, EntityResponse>()
    candidateDetailIds.value.forEach((entityId, index) => {
      const entity = candidateDetailQueries.value[index]?.data
      if (entity) result.set(entityId, entity)
    })
    return result
  })

  const similarPeople = computed<SimilarPersonCandidate[]>(() => {
    const pageIds = new Set(onPageEntityIds.value)
    const matches = candidateSearchQuery.data.value?.items ?? []
    const matchingScores = new Map(
      matches.map((entity) => [entity.entity_id, entity.matching_score]),
    )
    const candidates = candidateEntities(
      [...onPageEntities.value.values()],
      matches,
      textTerm.value,
    )
    const lines = transcription.value
    return candidates.map((entity) => {
      const entityLineIndex = lines.findIndex((line) =>
        line.entities?.some((span) => span.entity_id === entity.entity_id),
      )
      const entitySpan =
        entityLineIndex >= 0
          ? lines[entityLineIndex]?.entities?.find((span) => span.entity_id === entity.entity_id)
          : undefined
      const nerMentions = lines.reduce(
        (count, line) =>
          count +
          (line.entities?.filter((span) => span.entity_id === entity.entity_id).length ?? 0),
        0,
      )
      const detections = faces.value.filter((face) => face.personId === entity.entity_id).length
      const matchingScore = matchingScores.get(entity.entity_id)
      const normalizedFaceSimilarity =
        matchingScore === undefined
          ? undefined
          : matchingScore > 1
            ? matchingScore / 100
            : matchingScore
      const details =
        candidateDetails.value.get(entity.entity_id) ?? onPageEntities.value.get(entity.entity_id)
      return {
        id: entity.entity_id,
        name: entity.name || 'Unnamed person',
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
        wikidataId: details?.wikidata_id || undefined,
        nlcrAuthorityId: details?.nlcr_authority_id || undefined,
        faceId: faces.value.find((face) => face.personId === entity.entity_id)?.id,
        entityKey: entitySpan ? transcriptionEntityKey(entitySpan) : undefined,
        entityLineIndex: entityLineIndex >= 0 ? entityLineIndex : undefined,
      }
    })
  })

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
      () => pageQuery.error.value || layoutQuery.error.value || faceQuery.error.value,
    ),
    faces,
    isLoading: computed(
      () => pageQuery.isPending.value || layoutQuery.isPending.value || faceQuery.isPending.value,
    ),
    page: pageQuery.data,
    pageDimensions: computed(() => ({
      height: layoutQuery.data.value?.page_size[0] ?? 297,
      width: layoutQuery.data.value?.page_size[1] ?? 210,
    })),
    pageImageLoading: pageImageQuery.isPending,
    pageImageUrl,
    similarPeopleLoading: computed(
      () =>
        (Boolean(searchParams.value) && candidateSearchQuery.isPending.value) ||
        (!textTerm.value && onPageEntityQueries.value.some((query) => query.isPending)),
    ),
    similarPeople,
    transcription,
  }
}
