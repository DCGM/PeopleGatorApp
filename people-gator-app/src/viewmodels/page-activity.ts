import { computed, toValue, watchEffect, type MaybeRefOrGetter } from 'vue'
import { useFaceListQuery } from '@/query/faces'
import { useTextMentionListQuery } from '@/query/text-mentions'
import { utcToLocalTime } from './people-filters'

export type PageActivityItem = {
  id: string
  kind: 'face' | 'mention'
  label: string
  touchedAt: string | null
  userId: string | null
}
export function activityGroups(items: PageActivityItem[], mode: 'time' | 'user') {
  const groups = new Map<string, PageActivityItem[]>()
  for (const item of items) {
    const key =
      mode === 'user' ? (item.userId ?? '') : (utcToLocalTime(item.touchedAt).split('T')[0] ?? '')
    groups.set(key, [...(groups.get(key) ?? []), item])
  }
  return [...groups]
    .sort(([a], [b]) => (a ? (b ? b.localeCompare(a) : -1) : 1))
    .map(([key, records]) => ({
      key,
      records: records.sort(
        (a, b) => (b.touchedAt ?? '').localeCompare(a.touchedAt ?? '') || a.id.localeCompare(b.id),
      ),
      faces: records.filter((item) => item.kind === 'face').length,
      mentions: records.filter((item) => item.kind === 'mention').length,
    }))
}
export function localDayBounds(day: string) {
  const [year, month, date] = day.split('-').map(Number)
  const from = new Date(year!, month! - 1, date!)
  const to = new Date(year!, month! - 1, date! + 1)
  to.setMilliseconds(to.getMilliseconds() - 1)
  return {
    touchedFrom: utcToLocalTime(from.toISOString()),
    touchedTo: utcToLocalTime(to.toISOString()),
  }
}
export function usePageActivity(sourceId: MaybeRefOrGetter<string>) {
  const enabled = computed(() => !!toValue(sourceId))
  // These source-only collections remain stable while a group filters the workspace.
  const params = computed(() => ({
    'filter.source_id': [toValue(sourceId)],
    limit: 100,
    return_total_count: true,
  }))
  const faces = useFaceListQuery(params, enabled),
    mentions = useTextMentionListQuery(params, enabled)
  for (const query of [faces, mentions])
    watchEffect(() => {
      if (query.hasNextPage.value && !query.isFetchingNextPage.value && !query.isError.value)
        void query.fetchNextPage()
    })
  const items = computed<PageActivityItem[]>(() => [
    ...(faces.data.value?.pages ?? [])
      .flatMap((page) => page.items)
      .map((face) => ({
        id: face.detection_id,
        kind: 'face' as const,
        label: face.identifier || face.detection_id,
        touchedAt: face.last_touched_at ?? null,
        userId: face.last_touched_by_user_id ?? null,
      })),
    ...(mentions.data.value?.pages ?? [])
      .flatMap((page) => page.items)
      .map((mention) => ({
        id: mention.mention_id,
        kind: 'mention' as const,
        label: mention.name,
        touchedAt: mention.last_touched_at ?? null,
        userId: mention.last_touched_by_user_id ?? null,
      })),
  ])
  return {
    items,
    loading: computed(
      () =>
        faces.isPending.value ||
        mentions.isPending.value ||
        faces.hasNextPage.value ||
        mentions.hasNextPage.value,
    ),
    error: computed(() => faces.error.value || mentions.error.value),
    retry: () => {
      void faces.refetch()
      void mentions.refetch()
    },
  }
}
