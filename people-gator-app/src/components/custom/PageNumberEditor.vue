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
watch(
  () => [props.page.source_id, props.page.page_number],
  () => {
    value.value = String(props.page.page_number ?? '')
  },
  { immediate: true },
)
const mutation = usePageNumberMutation()
const valid = computed(
  () => value.value === '' || (/^[1-9]\d*$/.test(value.value) && Number(value.value) <= 2147483647),
)
function save() {
  if (!valid.value) return
  mutation.mutate({
    sourceId: props.page.source_id,
    payload: { page_number: value.value === '' ? null : Number(value.value) },
  })
}
</script>
<template>
  <form v-if="allowed" class="mb-4 flex flex-wrap items-center gap-2" @submit.prevent="save">
    <Input
      v-model="value"
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
