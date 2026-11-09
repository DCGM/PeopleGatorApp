<script setup lang="ts">
import { computed, ref } from 'vue'
import { refDebounced } from '@vueuse/core'
import { Check, ChevronsUpDown } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxTrigger,
  ComboboxList,
  ComboboxInput,
  ComboboxViewport,
  ComboboxItem,
  ComboboxItemIndicator,
} from '@/components/ui/combobox'
import SearchFilterPanel from './SearchFilterPanel.vue'
import ActiveFilters from './ActiveFilters.vue'
import SortControl from './SortControl.vue'
import { useEntityQuery } from '@/query/entities'
import { useEntityResultsQuery } from '@/query/search/entities'
import type { PageSortField } from '@/client'
import type { SortOption, SortState } from '@/lib/sorting'

defineProps<{ sortOptions: SortOption<PageSortField>[] }>()
const personId = defineModel<string>('personId', { required: true })
const sort = defineModel<SortState<PageSortField>>('sort', { required: true })
const open = ref(false)
const search = ref('')
const debouncedSearch = refDebounced(search, 250)
const selected = useEntityQuery(personId)
const people = useEntityResultsQuery(
  computed(() => ({
    query: debouncedSearch.value,
    processingFilters: { 'filter.entity_type': ['person' as const] },
  })),
  open,
)
const options = computed(() => people.data.value?.pages.flatMap((page) => page.items) ?? [])
const personLabel = computed(
  () =>
    selected.data.value?.name ||
    (selected.isError.value ? `Unavailable person (${personId.value})` : personId.value),
)
const tags = computed(() =>
  personId.value
    ? [{ key: 'person', value: personId.value, label: `Person: ${personLabel.value}` }]
    : [],
)
function select(value: unknown) {
  if (typeof value === 'string') {
    personId.value = value
    open.value = false
  }
}
</script>

<template>
  <SearchFilterPanel label="Document pages" filters-only>
    <Combobox
      v-model:open="open"
      :model-value="personId"
      ignore-filter
      class="min-w-0 max-w-full flex-none"
      @update:model-value="select"
    >
      <ComboboxAnchor as-child>
        <ComboboxTrigger as-child aria-label="Filter pages by person">
          <Button type="button" variant="outline" class="max-w-full justify-between">
            <span class="min-w-0 truncate">Person: {{ personId ? personLabel : 'All' }}</span>
            <ChevronsUpDown class="size-4 shrink-0" aria-hidden="true" />
          </Button>
        </ComboboxTrigger>
      </ComboboxAnchor>
      <ComboboxList align="start" :collision-padding="12" aria-label="People">
        <ComboboxInput v-model="search" aria-label="Search people" placeholder="Search people…" />
        <ComboboxViewport>
          <ComboboxItem value="" text-value="All people">All people</ComboboxItem>
          <p v-if="people.isPending.value" role="status">Loading people…</p>
          <div v-else-if="people.isError.value" role="alert">
            Could not load people.
            <Button variant="ghost" size="sm" @click="people.refetch()">Retry</Button>
          </div>
          <template v-else>
            <p v-if="!options.length" role="status">No matching people.</p>
            <ComboboxItem
              v-for="person in options"
              :key="person.entity_id"
              :value="person.entity_id"
              :text-value="person.name || person.entity_id"
            >
              {{ person.name || person.entity_id }}
              <ComboboxItemIndicator
                ><Check class="size-4" aria-hidden="true"
              /></ComboboxItemIndicator>
            </ComboboxItem>
          </template>
        </ComboboxViewport>
        <Button
          v-if="people.hasNextPage.value"
          variant="ghost"
          size="sm"
          :disabled="people.isFetchingNextPage.value"
          @click="people.fetchNextPage()"
          >Load more people</Button
        >
      </ComboboxList>
    </Combobox>
    <SortControl v-model="sort" :options="sortOptions" label="Sort pages" />
  </SearchFilterPanel>
  <ActiveFilters :filters="tags" @remove="personId = ''" @clear="personId = ''" />
</template>
