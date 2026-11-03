<script setup lang="ts">
import { computed, reactive } from 'vue'
import ListPagination from './ListPagination.vue'
import PersonMentionListSkeleton from './PersonMentionListSkeleton.vue'
import PersonMentionReviewList from './PersonMentionReviewList.vue'
import type { EntityLinkState, TextMentionResponse } from '@/client'
import type { TextMentionListParams } from '@/query/text-mentions'
import { useMentionViews } from '@/viewmodels/person-mentions'
import { useScanMentionsByPerson } from '@/viewmodels/scan-mentions'

const props = defineProps<{ filters: TextMentionListParams; linkStates: EntityLinkState[] }>()
const mentions = reactive(useScanMentionsByPerson(() => props.filters))
// Present every loaded record once, then split the views by group.
const records = computed<TextMentionResponse[]>(() =>
  mentions.groups.flatMap((group) => group.records),
)
const views = useMentionViews(records)
const viewsById = computed(() => new Map(views.value.map((view) => [view.id, view])))
const sections = computed(() =>
  mentions.groups.map((group) => ({
    ...group,
    name: mentions.personName(group.personId),
    views: group.records.flatMap((record) => viewsById.value.get(record.mention_id) ?? []),
  })),
)
</script>

<template>
  <div class="pt-2">
    <section
      v-for="section in sections"
      :key="section.key"
      class="mb-3 min-w-0"
      :aria-label="`Mentions of ${section.name}`"
    >
      <h3 class="truncate py-2 font-serif text-base">{{ section.name }}</h3>
      <PersonMentionReviewList
        class="pl-3"
        :mentions="section.views"
        :link-states="linkStates"
        compact
        :selectable="false"
      />
    </section>
    <PersonMentionListSkeleton v-if="mentions.loading" compact :count="3" />
    <p
      v-else-if="!sections.length && !mentions.hasNextPage && !mentions.error"
      class="py-6 text-center text-sm text-muted-foreground"
    >
      No mentions.
    </p>
    <ListPagination
      :has-next-page="mentions.hasNextPage"
      :is-fetching="mentions.isFetching"
      :error="mentions.error"
      error-text="Could not load mentions."
      :reset-key="JSON.stringify(filters)"
      :load-more="mentions.loadMore"
      :retry="mentions.retry"
    />
  </div>
</template>
