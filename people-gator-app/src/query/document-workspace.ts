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
} from '@/components/custom/document-page.types'
import { transcriptionEntityKey } from '@/components/custom/document-page.types'
import type { SimilarPersonCandidate } from '@/components/custom/similar-people.types'
import { responseData } from '@/query/api'
import { fetchEntity, useCreateEntityMutation } from '@/query/entities'
import { fetchFaces, useAssignFaceMutation } from '@/query/faces'
import { usePageImageQuery, usePageLookupQuery } from '@/query/media'
import { useObjectUrl } from '@/query/object-url'
import { queryKeys } from '@/query/keys'
import { fetchEntitySearch } from '@/query/search'
import {
  candidateEntities,
  candidateSearchParams,
  currentPagePersonIds,
} from '@/query/similar-people'

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
    (faceQuery.data.value?.items ?? []).map((face) => ({
      id: face.detection_id,
      personId: face.entity_id ?? null,
      name: (face.entity_id && onPageEntities.value.get(face.entity_id)?.name) || 'Unknown person',
      confidence: percentage(face.confidence),
      status: face.entity_id ? 'assigned' : 'unassigned',
      position: toPercentBox(face.bounding_box, layoutQuery.data.value),
      portrait: pageImageUrl.value,
    })),
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

  const similarPeople = computed<SimilarPersonCandidate[]>(() => {
    const pageIds = new Set(onPageEntityIds.value)
    const candidates = candidateEntities(
      [...onPageEntities.value.values()],
      candidateSearchQuery.data.value?.items ?? [],
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
      return {
        id: entity.entity_id,
        name: entity.name || 'Unnamed person',
        shortDescription: entity.short_description || undefined,
        score: 'matching_score' in entity ? percentage(entity.matching_score) : undefined,
        nerMentions: lines.reduce(
          (count, line) =>
            count +
            (line.entities?.filter((span) => span.entity_id === entity.entity_id).length ?? 0),
          0,
        ),
        detections: faces.value.filter((face) => face.personId === entity.entity_id).length,
        source: pageIds.has(entity.entity_id) ? 'page' : 'database',
        faceId: faces.value.find((face) => face.personId === entity.entity_id)?.id,
        entityKey: entitySpan ? transcriptionEntityKey(entitySpan) : undefined,
        entityLineIndex: entityLineIndex >= 0 ? entityLineIndex : undefined,
      }
    })
  })

  const createEntity = useCreateEntityMutation()
  const assignFaceMutation = useAssignFaceMutation()

  function assignFace(detectionId: string, entityId: string) {
    assignFaceMutation.mutate({ detectionId, entityId })
  }

  async function createAndAssign(detectionId: string, name: string) {
    const entity = await createEntity.mutateAsync({ entity_type: 'person', name })
    await assignFaceMutation.mutateAsync({ detectionId, entityId: entity.entity_id })
    return entity
  }

  return {
    assignFace,
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
