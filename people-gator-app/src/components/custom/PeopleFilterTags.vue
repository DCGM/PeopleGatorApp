<script setup lang="ts">
import { computed } from 'vue'
import { PEOPLE_COUNT_KEYS, usePeopleCounts } from '@/viewmodels/people-counts'
import { LIFE_DATE_KEYS, usePeopleLifeDates } from '@/viewmodels/people-life-dates'
import { ASSIGNMENT_LABELS, usePeopleFilters } from '@/viewmodels/people-filters'
import SharedFilterTags from './SharedFilterTags.vue'
import type { ActiveFilter } from './ActiveFilters.vue'

// Applied People filters: below the sidebar selectors on desktop, below search on mobile.
const counts = usePeopleCounts()
const lifeDates = usePeopleLifeDates()
const { assignment } = usePeopleFilters()
const specific = computed<ActiveFilter[]>(() => [
  ...(assignment.value === 'all'
    ? []
    : [{ key: 'assignment', value: assignment.value, label: ASSIGNMENT_LABELS[assignment.value] }]),
  ...counts.tags.value,
  ...lifeDates.tags.value,
])
const lifeDateKeys = new Set<string>(LIFE_DATE_KEYS)
function remove(filter: ActiveFilter) {
  if (filter.key === 'assignment') assignment.value = 'all'
  else if (lifeDateKeys.has(filter.key)) lifeDates.remove(filter)
  else counts.remove(filter)
}
</script>

<template>
  <p v-if="counts.error.value" role="alert">{{ counts.error.value }}</p>
  <p v-if="lifeDates.error.value" role="alert">{{ lifeDates.error.value }}</p>
  <SharedFilterTags
    :specific-filters="specific"
    :specific-keys="['assignment', 'filters', ...PEOPLE_COUNT_KEYS, ...LIFE_DATE_KEYS]"
    @remove-specific="remove"
  />
</template>
