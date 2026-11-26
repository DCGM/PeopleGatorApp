<script setup lang="ts">
import FilterGroup from './FilterGroup.vue'
import SharedFilterControls from './SharedFilterControls.vue'
import PeopleCountControl from './PeopleCountControl.vue'
import PeopleFilterTags from './PeopleFilterTags.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
import FilterDateTimePicker from './FilterDateTimePicker.vue'
import { PEOPLE_COUNT_CATEGORIES } from '@/viewmodels/people-counts'
import { LIFE_DATE_FILTERS, usePeopleLifeDates } from '@/viewmodels/people-life-dates'
import { ASSIGNMENT_LABELS, usePeopleFilters } from '@/viewmodels/people-filters'

// The People filter set, shown in the desktop sidebar or the mobile drawer like Documents.
// Applied filters are listed below the selectors; mobile also shows them under search.
const lifeDates = usePeopleLifeDates()
const { assignment } = usePeopleFilters()
const assignmentOptions = [
  { value: 'all' as const, label: 'All people' },
  { value: 'faces' as const, label: ASSIGNMENT_LABELS.faces },
  { value: 'mentions' as const, label: ASSIGNMENT_LABELS.mentions },
]
</script>

<template>
  <div class="flex w-full min-w-0 flex-col gap-4" role="group" aria-label="Filters">
    <FilterGroup title="Source">
      <SharedFilterControls :controls="['libraries', 'documents', 'pages']" />
    </FilterGroup>
    <FilterGroup title="Evidence">
      <SharedFilterControls :controls="['linkStates']" />
      <FilterSingleSelect
        v-model="assignment"
        class="max-w-full flex-none"
        label="Assignment"
        :options="assignmentOptions"
      />
    </FilterGroup>
    <FilterGroup title="Counts">
      <PeopleCountControl
        v-for="category in PEOPLE_COUNT_CATEGORIES"
        :key="category.value"
        :category="category.value"
        :label="category.label"
        trigger-class="max-w-full"
      />
    </FilterGroup>
    <FilterGroup title="Life dates">
      <FilterDateTimePicker
        v-for="filter in LIFE_DATE_FILTERS"
        :key="filter.key"
        date-only
        :label="filter.label"
        :invalid="!!lifeDates.error.value"
        :model-value="lifeDates.values.value[filter.key]"
        @update:model-value="lifeDates.set(filter.key, $event)"
      />
    </FilterGroup>
    <FilterGroup title="Created">
      <SharedFilterControls :controls="['creators', 'creationDates']" />
    </FilterGroup>
    <FilterGroup title="Modified">
      <SharedFilterControls :controls="['actors', 'dates']" />
    </FilterGroup>
  </div>
  <!-- Applied filters always follow the selectors, in the sidebar and in the drawer. -->
  <div class="flex min-w-0 flex-col gap-2 pt-2">
    <PeopleFilterTags />
  </div>
</template>
