<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { parseMinimum } from '@/viewmodels/annotation-counts'
import { usePeopleCounts, type PeopleCountCategory } from '@/viewmodels/people-counts'
const props = defineProps<{ category: PeopleCountCategory; label: string }>()
const counts = usePeopleCounts()
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
watch([open, counts.params], () => {
  if (!open.value) return
  lower.value = String(counts.params.value[`filter.min_${props.category}_total_count`] ?? '')
  upper.value = String(counts.params.value[`filter.max_${props.category}_total_count`] ?? '')
  attempted.value = false
})
function apply() {
  attempted.value = true
  if (error.value) return
  counts.set(props.category, lower.value, upper.value)
  open.value = false
}
</script>
<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child
      ><Button variant="outline">{{ label }}</Button></PopoverTrigger
    >
    <PopoverContent align="start" class="max-w-[calc(100vw-2rem)]">
      <form
        class="flex flex-wrap gap-2"
        :aria-label="`${label} count range`"
        @submit.prevent="apply"
      >
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
