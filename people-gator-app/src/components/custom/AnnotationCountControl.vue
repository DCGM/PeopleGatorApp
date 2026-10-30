<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import FilterSingleSelect from './FilterSingleSelect.vue'
import { DOCUMENT_ANNOTATION_GROUPS, DOCUMENT_ANNOTATION_STATES } from '@/viewmodels/document-table'
import {
  parseMinimum,
  useAnnotationCounts,
  type AnnotationCountField,
} from '@/viewmodels/annotation-counts'

const counts = useAnnotationCounts()
const category = ref('annotations'),
  state = ref('total'),
  minimum = ref('1'),
  attempted = ref(false)
const open = ref(false)
const parsed = computed(() => parseMinimum(minimum.value))
const field = computed(() => `${category.value}_${state.value}_count` as AnnotationCountField)
watch([open, field, counts.params], () => {
  if (!open.value) return
  minimum.value = String(counts.params.value[`filter.min_${field.value}`] ?? 1)
  attempted.value = false
})
function apply() {
  attempted.value = true
  if (parsed.value === undefined) return
  counts.set(field.value, parsed.value)
  open.value = false
  attempted.value = false
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child><Button variant="outline">Minimum annotations</Button></PopoverTrigger>
    <PopoverContent align="start" class="max-w-[calc(100vw-2rem)]">
      <form
        class="flex flex-wrap gap-2"
        aria-label="Minimum annotation count"
        @submit.prevent="apply"
      >
        <FilterSingleSelect
          v-model="category"
          label="Annotation category"
          :options="
            DOCUMENT_ANNOTATION_GROUPS.map((group) => ({
              value: group.scope === 'all' ? 'annotations' : group.scope,
              label: group.label,
            }))
          "
        />
        <FilterSingleSelect
          v-model="state"
          label="Annotation state"
          :options="
            DOCUMENT_ANNOTATION_STATES.map((state) => ({ value: state.id, label: state.label }))
          "
        />
        <Input
          v-model="minimum"
          aria-label="Minimum count"
          inputmode="numeric"
          placeholder="Minimum count"
          :aria-invalid="attempted && parsed === undefined"
        />
        <p v-if="attempted && parsed === undefined" role="alert">
          Enter a non-negative whole number.
        </p>
        <Button type="submit">Apply minimum</Button>
      </form>
    </PopoverContent>
  </Popover>
</template>
