<script setup lang="ts" generic="T extends string">
import { computed, ref } from 'vue'
import { Check, ChevronsUpDown } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxTrigger,
  ComboboxList,
  ComboboxViewport,
  ComboboxGroup,
  ComboboxItem,
  ComboboxItemIndicator,
} from '@/components/ui/combobox'

const props = defineProps<{ label: string; options: { value: T; label: string }[] }>()
const selected = defineModel<T>({ required: true })
const open = ref(false)
const selectedLabel = computed(
  () => props.options.find((option) => option.value === selected.value)?.label,
)

function updateSelection(value: unknown) {
  const option = props.options.find((option) => option.value === value)
  if (option) {
    selected.value = option.value
    open.value = false
  }
}
</script>

<template>
  <Combobox
    v-model:open="open"
    :model-value="selected"
    ignore-filter
    class="min-w-0 max-w-full flex-none"
    @update:model-value="updateSelection"
  >
    <ComboboxAnchor class="w-full" as-child>
      <ComboboxTrigger as-child :aria-label="label">
        <Button type="button" variant="outline" class="w-full justify-between">
          <span class="min-w-0 truncate">{{ label }}: {{ selectedLabel }}</span>
          <ChevronsUpDown class="size-4 shrink-0" aria-hidden="true" />
        </Button>
      </ComboboxTrigger>
    </ComboboxAnchor>
    <ComboboxList align="start" :collision-padding="12" :aria-label="label">
      <ComboboxViewport>
        <ComboboxGroup>
          <ComboboxItem
            v-for="option in options"
            :key="option.value"
            :value="option.value"
            :text-value="option.label"
          >
            {{ option.label }}
            <ComboboxItemIndicator
              ><Check class="size-4" aria-hidden="true"
            /></ComboboxItemIndicator>
          </ComboboxItem>
        </ComboboxGroup>
      </ComboboxViewport>
    </ComboboxList>
  </Combobox>
</template>
