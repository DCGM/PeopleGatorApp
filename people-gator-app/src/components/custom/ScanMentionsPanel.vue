<script setup lang="ts">
import { ScrollArea } from '@/components/ui/scroll-area'
import { computed } from 'vue'
import ActiveFilters, { type ActiveFilter } from './ActiveFilters.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
import PersonMentionGroups from './PersonMentionGroups.vue'
import PersonMentionOccurrences from './PersonMentionOccurrences.vue'
import SearchFilterPanel from './SearchFilterPanel.vue'
import SortControl from './SortControl.vue'
import type { EntityLinkState, TextMentionGroupSortField, TextMentionSortField } from '@/client'
import type { SortState } from '@/lib/sorting'
import type { TextMentionListParams } from '@/query/text-mentions'
import { MENTION_GROUP_SORTS } from '@/viewmodels/sort-options'
import {
  EVIDENCE_SCOPES,
  MENTION_VIEWS,
  SCAN_MENTION_SORTS,
  type EvidenceScope,
  type MentionView,
} from '@/viewmodels/scan-sidebar'

const props = defineProps<{
  sources: { page: string; document: string } | null
  linkStates: EntityLinkState[]
}>()
const scope = defineModel<EvidenceScope>('scope', { required: true })
const view = defineModel<MentionView>('view', { required: true })
const sort = defineModel<SortState<TextMentionSortField>>('sort', { required: true })
const groupSort = defineModel<SortState<TextMentionGroupSortField>>('groupSort', {
  required: true,
})
const emit = defineEmits<{ resetFilters: [] }>()

// Linked and unlinked occurrences alike, unless link states narrow the evidence.
const filters = computed<TextMentionListParams>(() => ({
  ...(props.sources &&
    (scope.value === 'page'
      ? { 'filter.page_source_id': [props.sources.page] }
      : { 'filter.document_source_id': [props.sources.document] })),
  ...(props.linkStates.length && { 'filter.entity_link_state': props.linkStates }),
}))
const tags = computed<ActiveFilter[]>(() =>
  scope.value === 'page'
    ? []
    : [{ key: 'scope', value: scope.value, label: 'Scope: This document' }],
)
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col" aria-label="Mentions">
    <div class="shrink-0 px-3 pt-3">
      <SearchFilterPanel label="Mentions" filters-only>
        <FilterSingleSelect v-model="scope" label="Scope" :options="EVIDENCE_SCOPES" />
        <FilterSingleSelect v-model="view" label="View" :options="MENTION_VIEWS" />
        <SortControl
          v-if="view === 'group'"
          v-model="groupSort"
          :options="MENTION_GROUP_SORTS"
          label="Sort mention groups"
        />
        <SortControl v-else v-model="sort" :options="SCAN_MENTION_SORTS" label="Sort mentions" />
      </SearchFilterPanel>
      <ActiveFilters
        :filters="tags"
        clear-label="Clear filters"
        @remove="scope = 'page'"
        @clear="scope = 'page'"
      />
    </div>
    <ScrollArea class="min-h-0 flex-1">
      <div class="px-3 pb-3">
        <template v-if="sources">
          <PersonMentionGroups
            v-if="view === 'group'"
            mode="mention"
            :filters="filters"
            :group-sort="groupSort"
            :occurrence-sort="sort"
            :link-states="linkStates"
            compact-occurrences
            automatic
            :selectable="false"
            @broaden="emit('resetFilters')"
          />
          <PersonMentionOccurrences
            v-else
            class="pt-2"
            :filters="filters"
            :sort="sort"
            :link-states="linkStates"
            compact
            :selectable="false"
          />
        </template>
      </div>
    </ScrollArea>
  </section>
</template>
