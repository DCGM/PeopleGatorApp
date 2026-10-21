<script setup lang="ts">
import { computed } from 'vue'
import type { EntityLinkState, TextMentionSortField } from '@/client'
import { Button } from '@/components/ui/button'
import PersonMentionEntry from './PersonMentionEntry.vue'
import PersonMentionItemSkeleton from './PersonMentionItemSkeleton.vue'
import { sortParams, type SortState } from '@/lib/sorting'
import { useTextMentionListQuery, type TextMentionListParams } from '@/query/text-mentions'
import { useMentionViews } from '@/viewmodels/person-mentions'

const props = defineProps<{
  name: string
  filters: TextMentionListParams
  sort: SortState<TextMentionSortField>
  personId: string
  linkStates: EntityLinkState[]
}>()
const query = useTextMentionListQuery(
  computed(() => ({
    ...props.filters,
    'filter.name': [props.name],
    ...sortParams(props.sort),
    limit: 20,
    return_total_count: true,
  })),
)
const records = computed(() => (query.data.value?.pages ?? []).flatMap((page) => page.items))
const mentions = useMentionViews(records)
</script>

<template>
  <div class="divide-y">
    <PersonMentionEntry
      v-for="mention in mentions"
      :key="mention.id"
      :mention="mention"
      :person-id="personId"
      :link-states="linkStates"
    />
    <PersonMentionItemSkeleton v-if="query.isPending.value" />
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
