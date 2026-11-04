import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useFaceListQuery } from '@/query/faces'
import { useTextMentionListQuery } from '@/query/text-mentions'
import { utcToLocalTime } from './shared-filters'
import type { SortDirection } from '@/lib/sorting'

export type PageActivityItem = {
  id: string
  kind: 'face' | 'mention'
  label: string
  touchedAt: string | null
  userId: string | null
}

export const ACTIVITY_BATCH_SIZE = 25

/**
 * The API order of each stream: last change with unknown times last in both
 * directions, then identity ascending. Faces precede mentions on equal times.
 */
export function compareActivity(direction: SortDirection) {
  const sign = direction === 'asc' ? 1 : -1
  return (left: PageActivityItem, right: PageActivityItem) => {
    if (left.touchedAt !== right.touchedAt) {
      if (!left.touchedAt) return 1
      if (!right.touchedAt) return -1
      const compared =
        Date.parse(left.touchedAt) - Date.parse(right.touchedAt) ||
        microseconds(left.touchedAt) - microseconds(right.touchedAt)
      if (compared) return sign * compared
    }
    return left.kind.localeCompare(right.kind) || left.id.localeCompare(right.id)
  }
}

/** The API orders by microseconds, below the millisecond precision of Date. */
function microseconds(time: string) {
  const fraction = /\.(\d+)/.exec(time)?.[1] ?? ''
  return Number(fraction.padEnd(6, '0').slice(3, 6))
}

type Stream = { items: PageActivityItem[]; done: boolean }

/**
 * Merge independently paged streams in the same order. An item is shown only
 * once every unfinished stream has loaded past it, so later batches append and
 * never insert above records already shown. `limitedBy` names the stream to load next.
 */
export function mergeActivity(streams: Stream[], direction: SortDirection) {
  const merged = streams.flatMap((stream) => stream.items).sort(compareActivity(direction))
  let visible = merged.length
  let limitedBy = -1
  for (const [index, stream] of streams.entries()) {
    if (stream.done) continue
    const last = stream.items[stream.items.length - 1]
    const end = last ? merged.indexOf(last) + 1 : 0
    if (end < visible || limitedBy < 0) {
      visible = Math.min(visible, end)
      limitedBy = index
    }
  }
  return { items: merged.slice(0, visible), limitedBy }
}

/** Contiguous local days of an ordered activity list; unknown times form one group. */
export function activityDays(items: PageActivityItem[]) {
  const days = new Map<string, PageActivityItem[]>()
  for (const item of items) {
    const key = item.touchedAt ? (utcToLocalTime(item.touchedAt).split('T')[0] ?? '') : ''
    days.set(key, [...(days.get(key) ?? []), item])
  }
  return [...days].map(([key, records]) => ({ key, records }))
}

/** Recorded latest changes of the page's faces and mentions, paged by last change. */
export function usePageActivity(
  sourceId: MaybeRefOrGetter<string>,
  direction: MaybeRefOrGetter<SortDirection> = 'desc',
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const active = computed(() => Boolean(toValue(sourceId)) && toValue(enabled))
  const params = computed(() => ({
    'filter.page_source_id': [toValue(sourceId)],
    sort: 'last_touched_at' as const,
    sort_direction: toValue(direction),
    limit: ACTIVITY_BATCH_SIZE,
    return_total_count: true,
  }))
  const faces = useFaceListQuery(params, active)
  const mentions = useTextMentionListQuery(params, active)
  const streams = computed<Stream[]>(() => [
    {
      done: Boolean(faces.data.value) && !faces.hasNextPage.value,
      items: (faces.data.value?.pages ?? [])
        .flatMap((page) => page.items)
        .map((face) => ({
          id: face.detection_id,
          kind: 'face' as const,
          label: face.identifier || 'Face',
          touchedAt: face.last_touched_at ?? null,
          userId: face.last_touched_by_user_id ?? null,
        })),
    },
    {
      done: Boolean(mentions.data.value) && !mentions.hasNextPage.value,
      items: (mentions.data.value?.pages ?? [])
        .flatMap((page) => page.items)
        .map((mention) => ({
          id: mention.mention_id,
          kind: 'mention' as const,
          label: mention.name,
          touchedAt: mention.last_touched_at ?? null,
          userId: mention.last_touched_by_user_id ?? null,
        })),
    },
  ])
  const merged = computed(() => mergeActivity(streams.value, toValue(direction)))
  const queries = [faces, mentions]
  return {
    items: computed(() => merged.value.items),
    days: computed(() => activityDays(merged.value.items)),
    totalCount: computed(
      () =>
        (faces.data.value?.pages[0]?.total_count ?? 0) +
        (mentions.data.value?.pages[0]?.total_count ?? 0),
    ),
    loading: computed(() => faces.isPending.value || mentions.isPending.value),
    hasNextPage: computed(() => streams.value.some((stream) => !stream.done)),
    isFetching: computed(() => faces.isFetching.value || mentions.isFetching.value),
    error: computed(() => faces.error.value || mentions.error.value),
    loadMore: async () => {
      const query = queries[merged.value.limitedBy]
      if (query?.hasNextPage.value) await query.fetchNextPage()
    },
    retry: () => {
      for (const query of queries) if (query.error.value) void query.refetch()
    },
  }
}
