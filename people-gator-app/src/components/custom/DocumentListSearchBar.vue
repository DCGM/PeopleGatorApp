<script setup lang="ts">
import AnnotationCountControl from './AnnotationCountControl.vue'
import { COUNT_KEYS, useAnnotationCounts } from '@/viewmodels/annotation-counts'
import { computed } from 'vue'
import SharedFilterControls from './SharedFilterControls.vue'
import SharedFilterTags from './SharedFilterTags.vue'
import SearchFilterPanel from './SearchFilterPanel.vue'
import type { ActiveFilter } from './ActiveFilters.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
import type { UnassignedFilter } from '@/viewmodels/document-filters'
import type { DocumentSortField } from '@/client'
import SortControl from './SortControl.vue'
import type { SortOption, SortState } from '@/lib/sorting'

const counts = useAnnotationCounts()

defineProps<{ resultCount: number; sortOptions?: SortOption<DocumentSortField>[] }>()
const sort = defineModel<SortState<DocumentSortField>>('sort')
const searchTerm = defineModel<string>('searchTerm', { required: true })
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
  <SearchFilterPanel
    v-model="searchTerm"
    label="Search documents"
    placeholder="Search a document, person or archive UUID…"
    :result-count="resultCount"
  >
    <SharedFilterControls />
    <AnnotationCountControl />
    <FilterSingleSelect
      v-model="unassigned"
      label="Unassigned faces"
      :options="[
        { value: 'all', label: 'All documents' },
        { value: 'yes', label: labels.yes },
        { value: 'no', label: labels.no },
      ]"
    />
    <SortControl v-if="sort && sortOptions" v-model="sort" :options="sortOptions" />
  </SearchFilterPanel>
  <p v-if="counts.error.value" role="alert">{{ counts.error.value }}</p>
  <SharedFilterTags
    :specific-filters="[...specific, ...counts.tags.value]"
    :specific-keys="['unassigned', ...COUNT_KEYS]"
    @remove-specific="$event.key.startsWith('min_') ? counts.remove($event) : (unassigned = 'all')"
  />
</template>
