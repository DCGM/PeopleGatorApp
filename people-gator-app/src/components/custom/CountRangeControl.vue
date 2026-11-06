<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { parseMinimum } from '@/viewmodels/annotation-counts'
import FilterSingleSelect from './FilterSingleSelect.vue'

// One count's inclusive range, optionally per annotation state (#111 and People lists).
const props = defineProps<{
  label: string
  states?: readonly { value: string; label: string }[]
  fieldFor: (state: string) => string
  params: Partial<Record<string, number>>
  triggerClass?: string
}>()
const emit = defineEmits<{ apply: [field: string, lower: string, upper: string, state: string] }>()
const state = ref(props.states?.[0]?.value ?? 'total')
const open = ref(false),
  lower = ref(''),
  upper = ref(''),
  attempted = ref(false)
const error = computed(() => {
  const min = parseMinimum(lower.value),
    max = parseMinimum(upper.value)
  if ((lower.value !== '' && min === undefined) || (upper.value !== '' && max === undefined))
    return 'Enter non-negative whole counts up to 9007199254740991.'
  if (min !== undefined && max !== undefined && min > max) return 'Minimum must not exceed maximum.'
  return undefined
})
watch([open, state, () => props.params], () => {
  if (!open.value) return
  const field = props.fieldFor(state.value)
  lower.value = String(props.params[`filter.min_${field}`] ?? '')
  upper.value = String(props.params[`filter.max_${field}`] ?? '')
  attempted.value = false
})
function apply() {
  attempted.value = true
  if (error.value) return
  emit('apply', props.fieldFor(state.value), lower.value, upper.value, state.value)
  open.value = false
}
</script>
<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child
      ><Button variant="outline" :class="triggerClass">{{ label }}</Button></PopoverTrigger
    >
    <PopoverContent align="start" class="max-w-[calc(100vw-2rem)]">
      <form
        class="flex flex-wrap gap-2"
        :aria-label="`${label} count range`"
        @submit.prevent="apply"
      >
        <FilterSingleSelect v-if="states" v-model="state" label="State" :options="[...states]" />
        <InputGroup>
          <InputGroupAddon>Min</InputGroupAddon>
          <InputGroupInput
            v-model="lower"
            :aria-label="`${label} minimum`"
            inputmode="numeric"
            placeholder="Any"
            :aria-invalid="attempted && !!error"
          />
        </InputGroup>
        <InputGroup>
          <InputGroupAddon>Max</InputGroupAddon>
          <InputGroupInput
            v-model="upper"
            :aria-label="`${label} maximum`"
            inputmode="numeric"
            placeholder="Any"
            :aria-invalid="attempted && !!error"
          />
        </InputGroup>
        <p v-if="attempted && error" role="alert">{{ error }}</p>
        <Button type="submit">Apply</Button>
      </form>
    </PopoverContent>
  </Popover>
</template>
