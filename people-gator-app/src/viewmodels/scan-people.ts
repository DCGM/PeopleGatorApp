import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type { EntitySortField, FoundEntity, EntityResponse } from '@/client'
import { defaultDirection, listSortParams, sortParams, type SortState } from '@/lib/sorting'
import { apiErrorCode } from '@/query/api'
import { fetchEntities, useEntityListQuery, type EntityListParams } from '@/query/entities'
import { queryKeys } from '@/query/keys'
import { useEntitySearchQuery, type EntitySearchParams } from '@/query/search'
import { RELEVANCE } from '@/viewmodels/sort-options'
import type { PeopleOrder, PeopleScope } from '@/viewmodels/scan-sidebar'
import type { Face, TranscriptionLine } from '@/viewmodels/document-workspace.types'
import { lineMentionsEntity, transcriptionEntityKey } from '@/viewmodels/document-workspace.types'
import type { SimilarPersonCandidate } from '@/viewmodels/similar-people.types'

export type PeopleTier = 'page' | 'document' | 'all'
const NESTED_TIERS: PeopleTier[] = ['page', 'document', 'all']
export const SCAN_PEOPLE_BATCH_SIZE = 20
const MEMBERSHIP_BATCH_SIZE = 50

/**
 * Context order lists this page's people, then the rest of this document, then
 * everyone else. Each tier is one server query over its complete matching set,
 * so scope, name/face search and the order within a tier apply before
 * pagination. The tiers are nested, so a later tier skips people shown earlier.
 * Every other order is a single query over the selected scope.
 */
export function peopleTiers(scope: PeopleScope, order: PeopleOrder): PeopleTier[] {
  if (order !== 'context') return [scope]
  return NESTED_TIERS.slice(0, NESTED_TIERS.indexOf(scope) + 1)
}

/** Within a context tier, the best matches lead when a name or face is searched. */
export function tierSort(order: PeopleOrder, scored: boolean): SortState<EntitySortField> {
  if (order === 'relevance' || (order === 'context' && scored)) return RELEVANCE
  if (order === 'context') return { field: 'name', direction: 'asc' }
  return { field: order, direction: defaultDirection(order) }
}

export type PeopleSearchInput = {
  text: string
  /** The attached reference face, once its embedding model is known. */
  face?: { id: string; embeddingModel: string } | null
}

export function tierParams(
  tier: PeopleTier,
  sources: { page: string; document: string },
): EntityListParams {
  return {
    'filter.entity_type': ['person'],
    ...(tier === 'page' && { 'filter.page_source_id': [sources.page] }),
    ...(tier === 'document' && { 'filter.document_source_id': [sources.document] }),
    limit: SCAN_PEOPLE_BATCH_SIZE,
    return_total_count: true,
  }
}

export function searchParams(
  base: EntityListParams,
  input: PeopleSearchInput,
  sort: SortState<EntitySortField>,
): EntitySearchParams {
  const text = input.text.trim()
  return {
    ...(base as EntitySearchParams),
    ...(text && { 'query.text': [text] }),
    ...(input.face && {
      'query.face_id': [input.face.id],
      'query.face_embedding_model': input.face.embeddingModel,
    }),
    ...sortParams(sort),
  }
}

/** List pages report `total_count`; search pages are reshaped to `totalCount`. */
type TierPage = {
  items: Array<EntityResponse | FoundEntity>
  total_count?: number | null
  totalCount?: number
}
type TierState = {
  pages: TierPage[] | undefined
  hasNextPage: boolean
  isFetching: boolean
  error: unknown
}

/**
 * Combine tier results in order: a tier contributes only after every earlier
 * tier is exhausted, and an identity appears once, at its first tier.
 */
export function combineTiers(tiers: TierState[]) {
  const seen = new Set<string>()
  const items: Array<{ record: EntityResponse | FoundEntity; tier: number }> = []
  let active = tiers.length
  for (const [index, tier] of tiers.entries()) {
    if (!tier.pages) {
      active = index
      break
    }
    for (const page of tier.pages)
      for (const record of page.items) {
        if (seen.has(record.entity_id)) continue
        seen.add(record.entity_id)
        items.push({ record, tier: index })
      }
    if (tier.hasNextPage || tier.error) {
      active = index
      break
    }
  }
  return { items, active }
}

export function useScanPeople(options: {
  sources: MaybeRefOrGetter<{ page: string; document: string } | null>
  scope: MaybeRefOrGetter<PeopleScope>
  order: MaybeRefOrGetter<PeopleOrder>
  search: MaybeRefOrGetter<PeopleSearchInput>
  /** Wait while an attached face's record is still loading. */
  searchPending?: MaybeRefOrGetter<boolean>
  enabled?: MaybeRefOrGetter<boolean>
  pageFaces: MaybeRefOrGetter<Face[]>
  transcription: MaybeRefOrGetter<TranscriptionLine[]>
  pageSourceId: MaybeRefOrGetter<string>
}) {
  const input = computed(() => toValue(options.search))
  const scored = computed(() => Boolean(input.value.text.trim() || input.value.face))
  const order = computed(() => toValue(options.order))
  const tiers = computed(() => peopleTiers(toValue(options.scope), order.value))
  const sort = computed(() => tierSort(order.value, scored.value))
  const ready = computed(
    () =>
      Boolean(toValue(options.sources)) &&
      !toValue(options.searchPending) &&
      toValue(options.enabled ?? true),
  )

  // Up to three nested tiers, each either a plain list or a ranked search.
  const slots = [0, 1, 2].map((index) => {
    const tier = computed(() => tiers.value[index])
    const base = computed(() => {
      const sources = toValue(options.sources)
      return tier.value && sources ? tierParams(tier.value, sources) : undefined
    })
    const list = useEntityListQuery(
      computed(() => base.value && { ...base.value, ...listSortParams(sort.value) }),
      computed(() => ready.value && Boolean(base.value) && !scored.value),
    )
    const search = useEntitySearchQuery(
      computed(() =>
        base.value ? searchParams(base.value, input.value, sort.value) : { limit: 0 },
      ),
      computed(() => ready.value && Boolean(base.value) && scored.value),
    )
    const query = computed(() => (scored.value ? search : list))
    return {
      query,
      state: computed<TierState>(() => ({
        pages: query.value.data.value?.pages as TierPage[] | undefined,
        hasNextPage: query.value.hasNextPage.value,
        isFetching: query.value.isFetching.value,
        error: query.value.error.value,
      })),
    }
  })
  const used = computed(() => slots.slice(0, tiers.value.length))
  const combined = computed(() => combineTiers(used.value.map((slot) => slot.state.value)))
  const activeSlot = computed(() => used.value[combined.value.active])

  // Page and document tiers are document members by definition; other loaded
  // people are checked in batches against the document scope.
  const knownMembers = computed(() => {
    const ids = new Set<string>()
    for (const { record, tier } of combined.value.items)
      if (tiers.value[tier] !== 'all') ids.add(record.entity_id)
    return ids
  })
  const membershipBatches = computed(() => {
    const ids = combined.value.items
      .map(({ record }) => record.entity_id)
      .filter((id) => !knownMembers.value.has(id))
      .sort()
    const batches: string[][] = []
    for (let index = 0; index < ids.length; index += MEMBERSHIP_BATCH_SIZE)
      batches.push(ids.slice(index, index + MEMBERSHIP_BATCH_SIZE))
    return batches
  })
  const membership = useQueries({
    queries: computed(() => {
      const document = toValue(options.sources)?.document
      return membershipBatches.value.map((ids) => {
        const params: EntityListParams = {
          'filter.document_source_id': [document ?? ''],
          'filter.entity_id': ids,
          limit: ids.length,
        }
        return {
          queryKey: queryKeys.entities.list(params),
          queryFn: ({ signal }: { signal: AbortSignal }) => fetchEntities(params, signal),
          enabled: ready.value && Boolean(document),
          staleTime: 60_000,
        }
      })
    }),
  })
  const documentMembers = computed(() => {
    const ids = new Set(knownMembers.value)
    for (const query of membership.value)
      for (const entity of query.data?.items ?? []) ids.add(entity.entity_id)
    return ids
  })

  const pageFaceCounts = computed(() => {
    const counts = new Map<string, number>()
    for (const face of toValue(options.pageFaces))
      if (face.personId) counts.set(face.personId, (counts.get(face.personId) ?? 0) + 1)
    return counts
  })

  const people = computed<SimilarPersonCandidate[]>(() => {
    const lines = toValue(options.transcription)
    const faces = toValue(options.pageFaces)
    const text = input.value.text.trim()
    const faceReference = input.value.face?.id
    return combined.value.items.map(({ record, tier }) => {
      const found = 'score' in record ? (record as FoundEntity) : undefined
      const textScore = found?.text_score ?? undefined
      const faceScore = found?.face_score ?? undefined
      const lineIndex = lines.findIndex((line) => lineMentionsEntity(line, record.entity_id))
      const span =
        lineIndex >= 0
          ? lines[lineIndex]?.entities?.find((item) => item.entity_id === record.entity_id)
          : undefined
      // Count occurrences, not the fragments of a name split across lines.
      const mentionCount = lines.reduce(
        (count, line) =>
          count +
          (line.entities ?? []).filter(
            (item) => item.entity_id === record.entity_id && item.firstFragment !== false,
          ).length,
        0,
      )
      const detections = pageFaceCounts.value.get(record.entity_id) ?? 0
      const faceId =
        found?.matched_detection_ids?.[0] ??
        faces.find((face) => face.personId === record.entity_id)?.id
      const tierName = tiers.value[tier]
      return {
        id: record.entity_id,
        sourceId: tierName === 'page' ? toValue(options.pageSourceId) : undefined,
        referenceFaceId: faceReference,
        candidateMode: faceReference ? 'face' : text ? 'text' : 'page',
        candidateText: text || undefined,
        name: record.name || 'Unnamed person',
        thumbnailFaceId: record.thumbnail_face_id ?? faceId,
        shortDescription: record.short_description || undefined,
        score: found ? percentage(found.score) : undefined,
        nerMentions: mentionCount,
        detections,
        linkedFaces: record.entity_link_stats?.faces?.total ?? 0,
        source: tierName === 'page' || mentionCount || detections ? 'page' : 'database',
        matchSources: [
          ...(textScore !== undefined
            ? ([{ type: 'text-search', score: percentage(textScore) }] as const)
            : []),
          ...(faceScore !== undefined
            ? ([{ type: 'face-match', distance: Math.max(0, 1 - normalized(faceScore)) }] as const)
            : []),
          ...(mentionCount > 0 ? ([{ type: 'scan-text' }] as const) : []),
          ...(detections > 0 ? ([{ type: 'scan-face' }] as const) : []),
          ...(documentMembers.value.has(record.entity_id)
            ? ([{ type: 'in-document' }] as const)
            : []),
        ],
        wikidataId: record.wikidata_id || undefined,
        nlcrAuthorityId: record.nlcr_authority_id || undefined,
        faceId,
        entityKey: span ? transcriptionEntityKey(span) : undefined,
        entityLineIndex: lineIndex >= 0 ? lineIndex : undefined,
      }
    })
  })

  const lastTier = computed(() => used.value[used.value.length - 1]?.state.value)
  return {
    people,
    scored,
    /** The widest tier contains every narrower one, so its total is the result count. */
    totalCount: computed(() => {
      const first = lastTier.value?.pages?.[0]
      return first?.total_count ?? first?.totalCount ?? undefined
    }),
    loading: computed(() => {
      const state = activeSlot.value?.state.value
      if (!ready.value) return true
      return combined.value.items.length === 0 && Boolean(state && !state.error && !state.pages)
    }),
    hasNextPage: computed(() => combined.value.active < used.value.length),
    isFetching: computed(() => used.value.some((slot) => slot.state.value.isFetching)),
    error: computed(() => activeSlot.value?.state.value.error ?? null),
    /** The API cannot score with the attached face, e.g. its stored vector is all zeros. */
    faceRejected: computed(
      () =>
        Boolean(input.value.face) &&
        used.value.some((slot) => apiErrorCode(slot.state.value.error) === 'invalid_search'),
    ),
    async loadMore() {
      const slot = activeSlot.value
      if (!slot?.state.value.pages || !slot.state.value.hasNextPage) return
      await slot.query.value.fetchNextPage()
    },
    retry() {
      void activeSlot.value?.query.value.refetch()
    },
  }
}

function normalized(score: number) {
  return score > 1 ? score / 100 : score
}

function percentage(value: number) {
  return Math.round((value <= 1 ? value * 100 : value) * 10) / 10
}
