<script setup lang="ts">
import SharedFilterControls from './SharedFilterControls.vue'
import PeopleCountControl from './PeopleCountControl.vue'
import PeopleFilterTags from './PeopleFilterTags.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
import FilterDateTimePicker from './FilterDateTimePicker.vue'
import { PEOPLE_COUNT_CATEGORIES } from '@/viewmodels/people-counts'
import { LIFE_DATE_FILTERS, usePeopleLifeDates } from '@/viewmodels/people-life-dates'
import { ASSIGNMENT_LABELS, usePeopleFilters } from '@/viewmodels/people-filters'

// The People filter set, shown in the desktop sidebar or the mobile drawer like Documents.
// The sidebar lists applied filters below the selectors; mobile shows them under search.
defineProps<{ tags?: boolean }>()
const lifeDates = usePeopleLifeDates()
const { assignment } = usePeopleFilters()
const assignmentOptions = [
  { value: 'all' as const, label: 'All people' },
  { value: 'faces' as const, label: ASSIGNMENT_LABELS.faces },
  { value: 'mentions' as const, label: ASSIGNMENT_LABELS.mentions },
]
</script>

<template>
  <div
    class="flex w-full min-w-0 flex-row flex-wrap items-start gap-2"
    role="group"
    aria-label="Filters"
  >
    <SharedFilterControls />
    <FilterSingleSelect
      v-model="assignment"
      class="max-w-full flex-none"
      label="Assignment"
      :options="assignmentOptions"
    />
    <PeopleCountControl
      v-for="category in PEOPLE_COUNT_CATEGORIES"
      :key="category.value"
      :category="category.value"
      :label="category.label"
      trigger-class="max-w-full"
    />
    <FilterDateTimePicker
      v-for="filter in LIFE_DATE_FILTERS"
      :key="filter.key"
      date-only
      :label="filter.label"
      :invalid="!!lifeDates.error.value"
      :model-value="lifeDates.values.value[filter.key]"
      @update:model-value="lifeDates.set(filter.key, $event)"
    />
  </div>
  <div v-if="tags" class="flex min-w-0 flex-col gap-2 pt-2">
    <PeopleFilterTags />
  </div>
</template>
