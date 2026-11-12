import { useQueries } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import type {
  EntityLinkState,
  EntityResponse,
  FaceResponse,
  FaceSortField,
  PageResponse,
} from '@/client'
import { listSortParams, type SortState } from '@/lib/sorting'
import { fetchEntity } from '@/query/entities'
import { useFaceListQuery, type FaceListParams } from '@/query/faces'
import { queryKeys } from '@/query/keys'
import { fetchPage } from '@/query/media'
import type { EvidenceScope, FaceView } from '@/viewmodels/scan-sidebar'

export const SCAN_FACE_BATCH_SIZE = 30
/** Person order keeps each person's faces contiguous across cursor batches. */
export const PERSON_FACE_SORT: SortState<FaceSortField> = { field: 'person', direction: 'asc' }

export type ScanFaceItem = {
  face: FaceResponse
  personName?: string
  page?: PageResponse
  onPage: boolean
}
export type ScanFaceGroup = { key: string; personId: string | null; items: ScanFaceItem[] }

export function scanFaceParams(
  scope: EvidenceScope,
  view: FaceView,
  sort: SortState<FaceSortField>,
  sources: { page: string; document: string },
  linkStates: EntityLinkState[],
): FaceListParams {
  return {
    ...(scope === 'page'
      ? { 'filter.page_source_id': [sources.page] }
      : { 'filter.document_source_id': [sources.document] }),
    ...(linkStates.length && { 'filter.entity_link_state': linkStates }),
    ...listSortParams(view === 'person' ? PERSON_FACE_SORT : sort),
    limit: SCAN_FACE_BATCH_SIZE,
    return_total_count: true,
  }
}

/**
 * Group faces by assigned person in arrival order; unassigned faces form one
 * group. A key that arrives again in a later batch joins its existing group, so
 * no group section is ever repeated.
 */
export function groupFacesByPerson(items: ScanFaceItem[]): ScanFaceGroup[] {
  const groups = new Map<string, ScanFaceGroup>()
  for (const item of items) {
    const personId = item.face.entity_id ?? null
    const key = personId ?? 'unassigned'
    const group = groups.get(key) ?? { key, personId, items: [] }
    group.items.push(item)
    groups.set(key, group)
  }
  // Unassigned is unknown to the person order and stays last.
  return [...groups.values()].sort(
    (left, right) => Number(left.personId === null) - Number(right.personId === null),
  )
}

export function useScanFaces(options: {
  sources: MaybeRefOrGetter<{ page: string; document: string } | null>
  scope: MaybeRefOrGetter<EvidenceScope>
  view: MaybeRefOrGetter<FaceView>
  sort: MaybeRefOrGetter<SortState<FaceSortField>>
  linkStates: MaybeRefOrGetter<EntityLinkState[]>
  enabled?: MaybeRefOrGetter<boolean>
}) {
  const params = computed(() => {
    const sources = toValue(options.sources)
    return sources
      ? scanFaceParams(
          toValue(options.scope),
          toValue(options.view),
          toValue(options.sort),
          sources,
          toValue(options.linkStates),
        )
      : undefined
  })
  const query = useFaceListQuery(
    params,
    computed(() => Boolean(params.value) && toValue(options.enabled ?? true)),
  )
  const records = computed(() => {
    const seen = new Set<string>()
    return (query.data.value?.pages ?? [])
      .flatMap((page) => page.items)
      .filter((face) => !seen.has(face.detection_id) && Boolean(seen.add(face.detection_id)))
  })
  const personIds = computed(() => [
    ...new Set(records.value.flatMap((face) => (face.entity_id ? [face.entity_id] : []))),
  ])
  const people = useQueries({
    queries: computed(() =>
      personIds.value.map((entityId) => ({
        queryKey: queryKeys.entities.detail(entityId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchEntity(entityId, signal),
        staleTime: 60_000,
      })),
    ),
  })
  const names = computed(() => {
    const result = new Map<string, EntityResponse>()
    personIds.value.forEach((entityId, index) => {
      const person = people.value[index]?.data
      if (person) result.set(entityId, person)
    })
    return result
  })
  // Off-page faces name their page, so they can open there.
  const sourceIds = computed(() => [...new Set(records.value.map((face) => face.source_id))])
  const pages = useQueries({
    queries: computed(() =>
      sourceIds.value.map((sourceId) => ({
        queryKey: queryKeys.pages.detail(sourceId),
        queryFn: ({ signal }: { signal: AbortSignal }) => fetchPage(sourceId, signal),
        staleTime: Number.POSITIVE_INFINITY,
        retry: false,
      })),
    ),
  })
  const pageBySource = computed(() => {
    const result = new Map<string, PageResponse>()
    sourceIds.value.forEach((sourceId, index) => {
      const page = pages.value[index]?.data
      if (page) result.set(sourceId, page)
    })
    return result
  })
  const items = computed<ScanFaceItem[]>(() => {
    const pageSource = toValue(options.sources)?.page
    return records.value.map((face) => ({
      face,
      personName: face.entity_id ? names.value.get(face.entity_id)?.name || undefined : undefined,
      page: pageBySource.value.get(face.source_id),
      onPage: face.source_id === pageSource,
    }))
  })
  return {
    items,
    groups: computed(() => groupFacesByPerson(items.value)),
    totalCount: computed(() => query.data.value?.pages[0]?.total_count ?? undefined),
    loading: computed(() => query.isPending.value),
    hasNextPage: computed(() => query.hasNextPage.value),
    isFetching: computed(() => query.isFetching.value),
    isFetchingNextPage: computed(() => query.isFetchingNextPage.value),
    error: computed(() => query.error.value),
    loadMore: () => query.fetchNextPage(),
    retry: () => query.refetch(),
  }
}
