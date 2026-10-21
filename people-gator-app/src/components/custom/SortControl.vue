<script setup lang="ts" generic="Field extends string">
import { computed } from 'vue'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { sortStrategies, type SortOption, type SortState } from '@/lib/sorting'

const props = withDefaults(
  defineProps<{ options: readonly SortOption<Field>[]; label?: string; size?: 'sm' | 'default' }>(),
  { label: 'Sort by', size: 'default' },
)
const sort = defineModel<SortState<Field>>({ required: true })
// One choice per complete strategy: field and direction together.
const strategies = computed(() => sortStrategies(props.options))
const selected = computed(
  () =>
    strategies.value.find(
      (item) => item.field === sort.value.field && item.direction === sort.value.direction,
    ) ?? strategies.value[0],
)

function select(value: unknown) {
  const strategy = strategies.value.find((item) => item.value === value)
  if (strategy) sort.value = { field: strategy.field, direction: strategy.direction }
}
</script>

<template>
  <Select :model-value="selected?.value" @update:model-value="select">
    <SelectTrigger :aria-label="label" :size="size" class="min-w-0 max-w-full flex-none">
      <span class="min-w-0 truncate">Sort: {{ selected?.label }}</span>
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="strategy in strategies" :key="strategy.value" :value="strategy.value">
        {{ strategy.label }}
      </SelectItem>
    </SelectContent>
  </Select>
</template>
