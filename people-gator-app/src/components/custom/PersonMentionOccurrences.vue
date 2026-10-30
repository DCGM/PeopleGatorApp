<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { EntityLinkState, TextMentionSortField } from '@/client'
import { Button } from '@/components/ui/button'
import { useAutomaticPagination } from '@/composables/automatic-pagination'
import PersonMentionReviewList from './PersonMentionReviewList.vue'
import PersonMentionListSkeleton from './PersonMentionListSkeleton.vue'
import { sortParams, type SortState } from '@/lib/sorting'
import { useTextMentionListQuery, type TextMentionListParams } from '@/query/text-mentions'
import { useMentionViews } from '@/viewmodels/person-mentions'

const props = defineProps<{
  name?: string
  compact?: boolean
  selection?: { all: boolean; ids: string[] }
  disabled?: boolean
  filters: TextMentionListParams
  sort: SortState<TextMentionSortField>
  personId: string
  linkStates: EntityLinkState[]
}>()
const emit = defineEmits<{
  selectMention: [id: string, value: boolean, shift: boolean]
  loaded: [ids: string[], verifiedIds: string[]]
}>()
const query = useTextMentionListQuery(
  computed(() => ({
    ...props.filters,
    ...(props.name !== undefined && { 'filter.name': [props.name] }),
    ...sortParams(props.sort),
    limit: 20,
    return_total_count: true,
  })),
)
const records = computed(() => (query.data.value?.pages ?? []).flatMap((page) => page.items))
// Fetch the next occurrence page as soon as the last loaded occurrence is shown.
const listEnd = ref<HTMLElement | null>(null)
useAutomaticPagination({
  target: listEnd,
  hasNextPage: query.hasNextPage,
  isFetching: query.isFetching,
  error: query.error,
  enabled: true,
  loadMore: () => query.fetchNextPage(),
})
const mentions = useMentionViews(records)
watch(
  () => records.value.map((record) => [record.mention_id, record.entity_link_state] as const),
  (items) =>
    emit(
      'loaded',
      items.map(([id]) => id),
      items.filter(([, state]) => state === 'verified').map(([id]) => id),
    ),
  { immediate: true },
)
</script>

<template>
  <div>
    <PersonMentionReviewList
      :mentions="mentions"
      :person-id="personId"
      :link-states="linkStates"
      :compact="compact"
      :selection="selection"
      :disabled="disabled"
      @select-mention="(id, value, shift) => emit('selectMention', id, value, shift)"
    />
    <div v-if="query.hasNextPage.value" ref="listEnd" class="h-px" aria-hidden="true" />
    <PersonMentionListSkeleton
      v-if="query.isPending.value || query.isFetchingNextPage.value"
      :compact="compact"
      :class="records.length > 0 && 'border-t'"
      :count="query.isPending.value ? 3 : 2"
    />
    <p v-if="query.error.value" role="alert" class="py-3 text-sm">
      Could not load occurrences.
      <Button variant="link" @click="query.refetch()">Retry</Button>
    </p>
  </div>
</template>
