<script setup lang="ts">
import EvidenceFilterControls from './EvidenceFilterControls.vue'
import EvidenceFilterTags from './EvidenceFilterTags.vue'
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'
import type { EntityLinkState, PageSortField } from '@/client'
import SortControl from './SortControl.vue'
import type { SortOption, SortState } from '@/lib/sorting'
const linkStates = defineModel<EntityLinkState[]>('linkStates', { default: () => [] })
import { computed } from 'vue'
import SearchFilterPanel from './SearchFilterPanel.vue'
import { linkStateVisuals } from '@/lib/entity-links'

import FilterSingleSelect from './FilterSingleSelect.vue'
import type { PageContentFilter } from '@/viewmodels/assignment'

const props = defineProps<{
  library?: string
  documentId?: string
  resultCount: number
  hasMoreResults?: boolean
  sortOptions?: SortOption<PageSortField>[]
}>()
const sort = defineModel<SortState<PageSortField>>('sort')

const emit = defineEmits<{ removeScope: [key: 'library' | 'document'] }>()
const searchTerm = defineModel<string>('searchTerm', { required: true })
const assignment = defineModel<PageContentFilter>('assignment', { required: true })
const active = computed(() => [
  ...(props.library
    ? [{ key: 'library', value: props.library, label: `Library: ${props.library}` }]
    : []),
  ...(props.documentId
    ? [{ key: 'document', value: props.documentId, label: `Document: ${props.documentId}` }]
    : []),
  ...(assignment.value === 'all'
    ? []
    : [{ key: 'assignment', value: assignment.value, label: `Page content: ${assignment.value}` }]),
  ...linkStates.value.map((value) => ({
    key: 'state',
    value,
    label: `Link state: ${linkStateVisuals[value].label}`,
  })),
])
function remove(chip: { key: string; value: string }) {
  if (chip.key === 'library' || chip.key === 'document') {
    emit('removeScope', chip.key)
    return
  }
  if (chip.key === 'assignment') assignment.value = 'all'
  else linkStates.value = linkStates.value.filter((state) => state !== chip.value)
}
</script>

<template>
  <SearchFilterPanel
    v-model="searchTerm"
    label="Search scans"
    placeholder="Search a person, page or document…"
    :result-count="resultCount"
    :has-more-results="hasMoreResults"
  >
    <EntityLinkStateFilter v-model="linkStates" />
    <EvidenceFilterControls hide-state />
    <FilterSingleSelect
      v-model="assignment"
      label="Page content"
      :options="[
        { value: 'all', label: 'All pages' },
        { value: 'entities', label: 'Contains assigned entities' },
        { value: 'faces', label: 'Contains faces' },
        { value: 'mentions', label: 'Contains mentions' },
      ]"
    />
    <SortControl v-if="sort && sortOptions" v-model="sort" :options="sortOptions" />
  </SearchFilterPanel>
  <EvidenceFilterTags hide-state :additional-filters="active" @remove-additional="remove" />
</template>
