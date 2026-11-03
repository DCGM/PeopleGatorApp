<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useCanAnnotate } from '@/composables/can-annotate'
import type { PageResponse } from '@/client'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { usePageNumberMutation } from '@/query/media'
const props = defineProps<{ page: PageResponse }>()
const allowed = useCanAnnotate()
const value = ref('')
const draftVersion = ref(props.page.version)
const editing = ref(false)
let sourceGeneration = 0
watch(
  () => [props.page.source_id, props.page.page_number, props.page.version] as const,
  ([sourceId], previous) => {
    if (previous && previous[0] !== sourceId) {
      editing.value = false
      sourceGeneration += 1
    }
    if (!editing.value) {
      value.value = String(props.page.page_number ?? '')
      draftVersion.value = props.page.version
    }
  },
  { immediate: true },
)
const mutation = usePageNumberMutation()
const valid = computed(
  () => value.value === '' || (/^[1-9]\d*$/.test(value.value) && Number(value.value) <= 2147483647),
)
function save() {
  if (!valid.value || mutation.isPending.value) return
  const generation = sourceGeneration
  const submittedValue = value.value
  mutation.mutate(
    {
      sourceId: props.page.source_id,
      payload: {
        version: draftVersion.value,
        page_number: value.value === '' ? null : Number(value.value),
      },
    },
    {
      onSuccess: (saved) => {
        if (generation !== sourceGeneration || saved.source_id !== props.page.source_id) return
        draftVersion.value = saved.version
        if (value.value === submittedValue) {
          editing.value = false
          value.value = String(saved.page_number ?? '')
        }
      },
    },
  )
}
</script>
<template>
  <form v-if="allowed" class="mb-4 flex flex-wrap items-center gap-2" @submit.prevent="save">
    <Input
      v-model="value"
      @focus="
        () => {
          if (!editing) {
            draftVersion = page.version
            editing = true
          }
        }
      "
      class="w-28"
      inputmode="numeric"
      aria-label="Page number"
      placeholder="Page number"
      :aria-invalid="!valid"
    />
    <Button type="submit" variant="outline" size="sm" :disabled="!valid || mutation.isPending.value"
      >Save</Button
    >
    <small v-if="mutation.isError.value" role="alert">Could not save page number.</small>
  </form>
</template>
