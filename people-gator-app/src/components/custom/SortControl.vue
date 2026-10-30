<script setup lang="ts" generic="Field extends string">
import { computed } from 'vue'
import SortSelect from './SortSelect.vue'
import { sortStrategies, type SortOption, type SortState } from '@/lib/sorting'

const props = withDefaults(
  defineProps<{
    options: readonly SortOption<Field>[]
    label?: string
    prefix?: string
    size?: 'sm' | 'default'
  }>(),
  { label: 'Sort by', size: 'default' },
)
const sort = defineModel<SortState<Field>>({ required: true })
// One choice per complete strategy: field and direction together.
const strategies = computed(() => sortStrategies(props.options))
const value = computed({
  get: () =>
    strategies.value.find(
      (item) => item.field === sort.value.field && item.direction === sort.value.direction,
    )?.value ?? '',
  set: (next) => {
    const strategy = strategies.value.find((item) => item.value === next)
    if (strategy) sort.value = { field: strategy.field, direction: strategy.direction }
  },
})
</script>

<template>
  <SortSelect
    v-model="value"
    :strategies="strategies"
    :label="label"
    :prefix="prefix"
    :size="size"
  />
</template>
