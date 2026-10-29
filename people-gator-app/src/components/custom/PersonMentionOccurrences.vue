<script setup lang="ts">
import { computed, watch } from 'vue'
import type { EntityLinkState, TextMentionSortField } from '@/client'
import { Button } from '@/components/ui/button'
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
  loaded: [ids: string[]]
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
const mentions = useMentionViews(records)
watch(
  () => records.value.map((record) => record.mention_id),
  (ids) => emit('loaded', ids),
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
    <Button
      v-if="query.hasNextPage.value"
      variant="outline"
      class="my-3"
      :disabled="query.isFetchingNextPage.value"
      @click="query.fetchNextPage()"
      >Load more occurrences</Button
    >
  </div>
</template>
