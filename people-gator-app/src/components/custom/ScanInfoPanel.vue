<script setup lang="ts">
import { ScrollArea } from '@/components/ui/scroll-area'
import { computed } from 'vue'
import AnnotationLastChange from './AnnotationLastChange.vue'
import ListPagination from './ListPagination.vue'
import PageNumberEditor from './PageNumberEditor.vue'
import SortSelect from './SortSelect.vue'
import { SIDEBAR_TITLE } from './sidebar-title'
import type { PageResponse } from '@/client'
import { linkStateVisuals } from '@/lib/entity-links'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import { usePageActivity } from '@/viewmodels/page-activity'
import type { ActivityDirection } from '@/viewmodels/scan-sidebar'

const props = defineProps<{ page?: PageResponse | null }>()
const direction = defineModel<ActivityDirection>('direction', { required: true })
const states = ['automatic', 'manual', 'verified', 'unassigned'] as const
const activity = usePageActivity(
  () => props.page?.source_id ?? '',
  () => direction.value,
)
const userIds = computed(() => [
  ...new Set(activity.items.value.flatMap((item) => (item.userId ? [item.userId] : []))),
])
const users = usePeopleFilterOptions(
  'user',
  '',
  computed(() => userIds.value.length > 0),
)
const directionValue = computed({
  get: () => direction.value,
  set: (value: string) => (direction.value = value as ActivityDirection),
})
const orders = [
  { value: 'desc', label: 'Newest first' },
  { value: 'asc', label: 'Oldest first' },
]
function dayLabel(key: string) {
  return key ? new Date(`${key}T12:00:00`).toLocaleDateString() : 'Time not recorded'
}
</script>

<template>
  <ScrollArea class="min-h-0 flex-1">
    <section class="p-3" aria-label="Page info">
      <div class="space-y-5">
        <section aria-labelledby="page-info-title" class="min-w-0 space-y-3">
          <h3 id="page-info-title" :class="SIDEBAR_TITLE">This page</h3>
          <PageNumberEditor v-if="page" :page="page" />
          <AnnotationLastChange
            v-if="page"
            :touched-at="page.last_touched_at"
            :user-id="page.last_touched_by_user_id"
          />
          <div v-if="page?.entity_link_stats" class="space-y-4">
            <section
              v-for="kind in ['faces', 'mentions'] as const"
              :key="kind"
              :aria-label="`Page ${kind}`"
            >
              <div class="mb-2 flex items-baseline justify-between gap-2">
                <h4 class="text-sm font-semibold capitalize">{{ kind }}</h4>
                <span class="text-sm tabular-nums"
                  >{{ page.entity_link_stats[kind]?.total ?? 0 }} total</span
                >
              </div>
              <dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                <div
                  v-for="state in states"
                  :key="state"
                  class="flex items-center justify-between gap-2"
                >
                  <dt class="flex items-center gap-1.5">
                    <component
                      :is="linkStateVisuals[state].icon"
                      class="size-3 shrink-0"
                      aria-hidden="true"
                    />
                    {{ linkStateVisuals[state].label }}
                  </dt>
                  <dd class="tabular-nums">{{ page.entity_link_stats[kind]?.[state] ?? 0 }}</dd>
                </div>
              </dl>
            </section>
          </div>
          <p v-else-if="page" class="text-sm text-muted-foreground">Statistics unavailable.</p>
        </section>

        <section aria-labelledby="page-activity-title" class="min-w-0 space-y-3">
          <div class="flex flex-row flex-wrap items-center justify-between gap-2">
            <h3 id="page-activity-title" :class="SIDEBAR_TITLE">Latest changes</h3>
            <SortSelect
              v-model="directionValue"
              :strategies="orders"
              label="Sort changes"
              size="sm"
            />
          </div>
          <p class="text-xs text-muted-foreground">Only each record's latest change is kept.</p>
          <p v-if="activity.loading.value && !activity.error.value" role="status" class="text-sm">
            Loading…
          </p>
          <p
            v-else-if="
              !activity.items.value.length && !activity.hasNextPage.value && !activity.error.value
            "
            class="text-sm text-muted-foreground"
          >
            No faces or mentions on this page.
          </p>
          <section
            v-for="day in activity.days.value"
            :key="day.key"
            class="min-w-0 space-y-1"
            :aria-label="dayLabel(day.key)"
          >
            <h4 class="text-sm font-semibold">{{ dayLabel(day.key) }}</h4>
            <ul class="space-y-1">
              <li v-for="item in day.records" :key="`${item.kind}:${item.id}`" class="min-w-0">
                <small class="block break-words"
                  >{{ item.kind === 'face' ? 'Face' : 'Mention' }} · {{ item.label }}</small
                >
                <small class="block text-muted-foreground"
                  ><time v-if="item.touchedAt" :datetime="item.touchedAt">{{
                    new Date(item.touchedAt).toLocaleTimeString()
                  }}</time
                  ><span v-else>Time not recorded</span> ·
                  {{
                    item.userId
                      ? (users.labels.value[item.userId] ?? item.userId)
                      : 'User not recorded'
                  }}</small
                >
              </li>
            </ul>
          </section>
          <ListPagination
            :has-next-page="activity.hasNextPage.value"
            :is-fetching="activity.isFetching.value"
            :error="activity.error.value"
            error-text="Could not load changes."
            :reset-key="direction"
            :load-more="activity.loadMore"
            :retry="activity.retry"
          />
        </section>
      </div>
    </section>
  </ScrollArea>
</template>
