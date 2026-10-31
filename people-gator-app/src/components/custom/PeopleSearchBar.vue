<script setup lang="ts">
import PeopleCountControl from './PeopleCountControl.vue'
import {
  PEOPLE_COUNT_CATEGORIES,
  PEOPLE_COUNT_KEYS,
  usePeopleCounts,
} from '@/viewmodels/people-counts'
import { computed } from 'vue'
import SharedFilterControls from './SharedFilterControls.vue'
import SharedFilterTags from './SharedFilterTags.vue'
import SearchFilterPanel from './SearchFilterPanel.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
import SortControl from './SortControl.vue'
import type { ActiveFilter } from './ActiveFilters.vue'
import type { EntitySortField } from '@/client'
import type { SortOption, SortState } from '@/lib/sorting'
import type { AssignmentFilter } from '@/viewmodels/assignment'

defineProps<{
  resultCount: number
  hasMoreResults?: boolean
  sortOptions?: SortOption<EntitySortField>[]
}>()
const sort = defineModel<SortState<EntitySortField>>('sort')
const searchTerm = defineModel<string>('searchTerm', { required: true })
const assignment = defineModel<AssignmentFilter>('assignment', { required: true })
const counts = usePeopleCounts()
const assignmentTags = computed<ActiveFilter[]>(() =>
  assignment.value === 'all'
    ? []
    : [
        {
          key: 'assignment',
          value: assignment.value,
          label: assignment.value === 'faces' ? 'Assigned faces' : 'Assigned mentions',
        },
      ],
)
const specific = computed(() => [...assignmentTags.value, ...counts.tags.value])
</script>

<template>
  <SearchFilterPanel
    v-model="searchTerm"
    label="Search people"
    placeholder="Search a person or alias…"
    :result-count="resultCount"
    :has-more-results="hasMoreResults"
  >
    <SharedFilterControls />
    <FilterSingleSelect
      v-model="assignment"
      label="Assignment"
      :options="[
        { value: 'all', label: 'All people' },
        { value: 'faces', label: 'Assigned faces' },
        { value: 'mentions', label: 'Assigned mentions' },
      ]"
    />
    <PeopleCountControl
      v-for="category in PEOPLE_COUNT_CATEGORIES"
      :key="category.value"
      :category="category.value"
      :label="category.label"
    />
    <SortControl v-if="sort && sortOptions" v-model="sort" :options="sortOptions" />
  </SearchFilterPanel>
  <p v-if="counts.error.value" role="alert">{{ counts.error.value }}</p>
  <SharedFilterTags
    :specific-filters="specific"
    :specific-keys="['assignment', 'filters', ...PEOPLE_COUNT_KEYS]"
    @remove-specific="
      (tag) => (tag.key === 'assignment' ? (assignment = 'all') : counts.remove(tag))
    "
  />
</template>
