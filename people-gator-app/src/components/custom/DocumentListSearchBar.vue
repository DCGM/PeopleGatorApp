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
import DocumentFilterTags from './DocumentFilterTags.vue'
import type { DocumentSortField } from '@/client'
import SortControl from './SortControl.vue'
import type { SortOption, SortState } from '@/lib/sorting'

// Only search and sort sit above the Documents table; filters live in the sidebar or drawer.
const desktop = useMediaQuery('(min-width: 1024px)')

defineProps<{ resultCount: number; sortOptions?: SortOption<DocumentSortField>[] }>()
const sort = defineModel<SortState<DocumentSortField>>('sort')
const searchTerm = defineModel<string>('searchTerm', { required: true })
const filtersOpen = defineModel<boolean>('filtersOpen', { default: false })
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
  <!-- With the drawer closed, applied filters stay visible and removable under search. -->
  <DocumentFilterTags v-if="!desktop" />
</template>
