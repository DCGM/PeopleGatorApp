<script setup lang="ts">
import { computed } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Search, SlidersHorizontal, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'
import { DOCUMENT_COUNT_KEYS, useDocumentCounts } from '@/viewmodels/document-counts'
import SharedFilterTags from './SharedFilterTags.vue'
import type { ActiveFilter } from './ActiveFilters.vue'
import type { UnassignedFilter } from '@/viewmodels/document-filters'
import type { DocumentSortField } from '@/client'
import SortControl from './SortControl.vue'
import type { SortOption, SortState } from '@/lib/sorting'

// Only search and sort sit above the Documents table; filters live in the sidebar or drawer.
const counts = useDocumentCounts()
const desktop = useMediaQuery('(min-width: 1024px)')

defineProps<{ resultCount: number; sortOptions?: SortOption<DocumentSortField>[] }>()
const sort = defineModel<SortState<DocumentSortField>>('sort')
const searchTerm = defineModel<string>('searchTerm', { required: true })
const filtersOpen = defineModel<boolean>('filtersOpen', { default: false })
// Unassigned faces has no control here, but links can still carry it.
const unassigned = defineModel<UnassignedFilter>('unassigned', { required: true })
const labels = { yes: 'Has unassigned faces', no: 'No unassigned faces' }
const specific = computed<ActiveFilter[]>(() =>
  unassigned.value === 'all'
    ? []
    : [
        {
          key: 'unassigned',
          value: unassigned.value,
          label: `Unassigned faces: ${labels[unassigned.value]}`,
        },
      ],
)
</script>

<template>
  <div
    class="flex w-full min-w-0 flex-row flex-wrap items-center gap-2"
    aria-label="Search documents panel"
    role="search"
  >
    <div class="flex min-w-0 flex-1 basis-full items-center gap-2 sm:basis-0">
      <InputGroup class="min-w-0 flex-1">
        <InputGroupInput
          v-model="searchTerm"
          aria-label="Search documents"
          placeholder="Search a document, person or archive UUID…"
        />
        <InputGroupAddon><Search aria-hidden="true" /></InputGroupAddon>
        <InputGroupAddon align="inline-end">
          <InputGroupButton
            v-if="searchTerm"
            size="icon-sm"
            aria-label="Clear search documents"
            @click="searchTerm = ''"
            ><X aria-hidden="true"
          /></InputGroupButton>
          <small class="whitespace-nowrap" role="status">{{ resultCount }} results</small>
        </InputGroupAddon>
      </InputGroup>
      <Button
        v-if="!desktop"
        type="button"
        variant="outline"
        size="icon"
        aria-haspopup="dialog"
        :aria-expanded="filtersOpen"
        :aria-label="filtersOpen ? 'Hide filters' : 'Show filters'"
        @click="filtersOpen = !filtersOpen"
        ><SlidersHorizontal aria-hidden="true"
      /></Button>
    </div>
    <SortControl v-if="sort && sortOptions" v-model="sort" :options="sortOptions" />
  </div>
  <p v-if="counts.error.value" role="alert">{{ counts.error.value }}</p>
  <SharedFilterTags
    :specific-filters="[...specific, ...counts.tags.value]"
    :specific-keys="['unassigned', ...DOCUMENT_COUNT_KEYS]"
    @remove-specific="$event.key === 'unassigned' ? (unassigned = 'all') : counts.remove($event)"
  />
</template>
