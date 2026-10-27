<script setup lang="ts">
import { computed } from 'vue'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'

export type SortSelectStrategy = { value: string; label: string }

const props = withDefaults(
  defineProps<{
    strategies: readonly SortSelectStrategy[]
    prefix?: string
    label?: string
    size?: 'sm' | 'default'
  }>(),
  { label: 'Sort by', prefix: 'Sort', size: 'default' },
)
const value = defineModel<string>({ required: true })
const selected = computed(
  () => props.strategies.find((item) => item.value === value.value) ?? props.strategies[0],
)

function select(next: unknown) {
  const strategy = props.strategies.find((item) => item.value === next)
  if (strategy) value.value = strategy.value
}
</script>

<template>
  <Select :model-value="selected?.value" @update:model-value="select">
    <SelectTrigger :aria-label="label" :size="size" class="min-w-0 max-w-full flex-none">
      <span class="min-w-0 truncate">{{ prefix }}: {{ selected?.label }}</span>
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="strategy in strategies" :key="strategy.value" :value="strategy.value">
        {{ strategy.label }}
      </SelectItem>
    </SelectContent>
  </Select>
</template>
