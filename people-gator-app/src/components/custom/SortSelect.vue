<script setup lang="ts">
import { computed } from 'vue'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectGroup,
  SelectLabel,
} from '@/components/ui/select'

export type SortSelectStrategy = { value: string; label: string; group?: string }

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

const groups = computed(() =>
  [...new Set(props.strategies.map((item) => item.group))].map((label) => ({
    label,
    items: props.strategies.filter((item) => item.group === label),
  })),
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
      <SelectGroup v-for="group in groups" :key="group.label ?? 'general'">
        <SelectLabel v-if="group.label">{{ group.label }}</SelectLabel>
        <SelectItem v-for="strategy in group.items" :key="strategy.value" :value="strategy.value">
          {{ strategy.label }}
        </SelectItem>
      </SelectGroup>
    </SelectContent>
  </Select>
</template>
