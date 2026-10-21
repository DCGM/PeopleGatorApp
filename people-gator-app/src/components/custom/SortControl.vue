<script setup lang="ts" generic="Field extends string">
import { computed } from 'vue'
import { ArrowDownWideNarrow, ArrowUpNarrowWide } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { defaultDirection, directionLabel, type SortOption, type SortState } from '@/lib/sorting'

const props = withDefaults(
  defineProps<{ options: readonly SortOption<Field>[]; label?: string; size?: 'sm' | 'default' }>(),
  { label: 'Sort by', size: 'default' },
)
const sort = defineModel<SortState<Field>>({ required: true })
const selected = computed(
  () => props.options.find((option) => option.value === sort.value.field) ?? props.options[0],
)
const current = computed(() => directionLabel(selected.value?.kind ?? 'id', sort.value.direction))
const next = computed(() =>
  directionLabel(selected.value?.kind ?? 'id', sort.value.direction === 'asc' ? 'desc' : 'asc'),
)

function selectField(value: unknown) {
  const option = props.options.find((item) => item.value === value)
  if (option && option.value !== sort.value.field)
    sort.value = { field: option.value, direction: defaultDirection(option.value) }
}
function toggleDirection() {
  sort.value = { ...sort.value, direction: sort.value.direction === 'asc' ? 'desc' : 'asc' }
}
</script>

<template>
  <ButtonGroup class="min-w-0 max-w-full flex-none" :aria-label="label">
    <Select :model-value="sort.field" @update:model-value="selectField">
      <SelectTrigger :aria-label="label" :size="size" class="min-w-0 max-w-full">
        <span class="min-w-0 truncate">Sort: {{ selected?.label }}</span>
      </SelectTrigger>
      <SelectContent>
        <SelectItem v-for="option in options" :key="option.value" :value="option.value">
          {{ option.label }}
        </SelectItem>
      </SelectContent>
    </Select>
    <Button
      type="button"
      variant="outline"
      :size="size === 'sm' ? 'icon-sm' : 'icon'"
      :aria-label="`Order: ${current}. Change to ${next}`"
      :title="current"
      @click="toggleDirection"
    >
      <ArrowUpNarrowWide v-if="sort.direction === 'asc'" aria-hidden="true" />
      <ArrowDownWideNarrow v-else aria-hidden="true" />
    </Button>
  </ButtonGroup>
</template>
