<script setup lang="ts">
import {
  usePeopleCounts,
  PEOPLE_COUNT_STATES,
  type PeopleCountCategory,
  type PeopleCountState,
} from '@/viewmodels/people-counts'
import CountRangeControl from './CountRangeControl.vue'
const props = defineProps<{ category: PeopleCountCategory; label: string }>()
const counts = usePeopleCounts()
</script>
<template>
  <CountRangeControl
    :label="label"
    :states="PEOPLE_COUNT_STATES"
    :field-for="(state) => `${props.category}_${state}_count`"
    :params="counts.params.value"
    @apply="
      (_field, lower, upper, state) =>
        counts.set(props.category, lower, upper, state as PeopleCountState)
    "
  />
</template>
