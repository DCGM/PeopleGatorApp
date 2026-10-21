<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronRight } from '@lucide/vue'
import type { EntityLinkState, TextMentionGroupSortField, TextMentionSortField } from '@/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import PersonMentionOccurrences from './PersonMentionOccurrences.vue'
import PersonMentionItemSkeleton from './PersonMentionItemSkeleton.vue'
import { sortParams, type SortState } from '@/lib/sorting'
import { useTextMentionGroupsQuery, type TextMentionListParams } from '@/query/text-mentions'

const props = withDefaults(
  defineProps<{
    filters: TextMentionListParams
    groupSort: SortState<TextMentionGroupSortField>
    occurrenceSort: SortState<TextMentionSortField>
    personId: string
    linkStates: EntityLinkState[]
    enabled?: boolean
  }>(),
  { enabled: true },
)
const emit = defineEmits<{ broaden: [] }>()
const query = useTextMentionGroupsQuery(
  computed(() => ({
    ...props.filters,
    ...sortParams(props.groupSort),
    limit: 25,
    return_total_count: true,
  })),
  computed(() => props.enabled),
)
const groups = computed(() => (query.data.value?.pages ?? []).flatMap((page) => page.items))
const total = computed(() => query.data.value?.pages[0]?.total_count ?? 0)
const open = ref(new Set<string>())
function toggle(name: string, value: boolean) {
  const next = new Set(open.value)
  if (value) next.add(name)
  else next.delete(name)
  open.value = next
}
// Filters can remove a group; never keep stale expanded state for it.
watch(groups, (items) => {
  const names = new Set(items.map((group) => group.name))
  open.value = new Set([...open.value].filter((name) => names.has(name)))
})
</script>

<template>
  <div>
    <ul class="divide-y" aria-label="Exact appearance groups">
      <li v-for="group in groups" :key="group.name">
        <Collapsible :open="open.has(group.name)" @update:open="toggle(group.name, $event)">
          <CollapsibleTrigger as-child>
            <Button
              type="button"
              variant="ghost"
              class="h-auto w-full justify-start gap-3 py-3 text-left whitespace-normal"
            >
              <ChevronRight
                class="size-4 shrink-0 transition-transform"
                :class="open.has(group.name) && 'rotate-90'"
                aria-hidden="true"
              />
              <span class="min-w-0 flex-1 font-serif text-lg">“{{ group.name }}”</span>
              <Badge variant="outline" class="font-mono">
                {{ group.occurrence_count }}
                {{ group.occurrence_count === 1 ? 'occurrence' : 'occurrences' }}
              </Badge>
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent class="pl-7">
            <PersonMentionOccurrences
              v-if="open.has(group.name)"
              :name="group.name"
              :filters="filters"
              :sort="occurrenceSort"
              :person-id="personId"
              :link-states="linkStates"
            />
          </CollapsibleContent>
        </Collapsible>
      </li>
    </ul>
    <PersonMentionItemSkeleton v-if="query.isPending.value && enabled" />
    <div class="py-3 text-sm">
      <p v-if="query.error.value" role="alert">
        Could not load mention groups.
        <Button variant="link" @click="query.refetch()">Retry</Button>
      </p>
      <p v-else-if="!query.isPending.value">Showing {{ groups.length }} of {{ total }} groups</p>
      <p v-if="!query.error.value && !query.isPending.value && !groups.length">
        No mentions match the evidence filters.
        <Button variant="link" @click="emit('broaden')">Broaden evidence</Button>
      </p>
      <Button
        v-if="query.hasNextPage.value"
        variant="outline"
        :disabled="query.isFetchingNextPage.value"
        @click="query.fetchNextPage()"
        >Load more groups</Button
      >
    </div>
  </div>
</template>
