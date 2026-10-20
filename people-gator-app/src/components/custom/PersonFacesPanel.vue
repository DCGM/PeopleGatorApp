<script setup lang="ts">
import { BadgeCheck, Unlink } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from '@/components/ui/button'
import PersonFaceCard from './PersonFaceCard.vue'
import SelectedFaceActions from './SelectedFaceActions.vue'
import { useCanAnnotate } from '@/composables/can-annotate'
import { useReviewFacesMutation } from '@/query/faces'
import type { PersonFace } from '@/viewmodels/person-detail.types'
const props = defineProps<{ faces: PersonFace[]; personName: string }>()
const allowed = useCanAnnotate()
const mutation = useReviewFacesMutation()
const route = useRoute()
const selectedIds = ref(new Set<string>())
const anchor = ref<string | null>(null)
const selected = computed(() => props.faces.filter((face) => selectedIds.value.has(face.id)))
const unverified = computed(() => selected.value.filter((face) => face.linkState !== 'verified'))
const busy = mutation.isPending
const feedback = ref('')
function clear() {
  selectedIds.value = new Set()
  anchor.value = null
}
function select(id: string, event: MouseEvent, addOnly = false) {
  if (busy.value) return
  feedback.value = ''
  const next = new Set(selectedIds.value)
  const index = props.faces.findIndex((face) => face.id === id)
  const start = props.faces.findIndex((face) => face.id === anchor.value)
  if (event.shiftKey && start >= 0 && index >= 0) {
    event.preventDefault()
    for (const face of props.faces.slice(Math.min(start, index), Math.max(start, index) + 1))
      next.add(face.id)
  } else {
    if (!addOnly && next.has(id)) next.delete(id)
    else next.add(id)
    anchor.value = id
  }
  selectedIds.value = next
}
async function review(action: 'verify' | 'unassign') {
  if (busy.value || !allowed.value) return
  const targets = action === 'verify' ? unverified.value : selected.value
  if (!targets.length) return
  feedback.value = ''
  try {
    await mutation.mutateAsync({ detectionIds: targets.map((face) => face.id), action })
    clear()
    feedback.value = `${targets.length} ${targets.length === 1 ? 'face' : 'faces'} ${action === 'verify' ? 'verified' : 'unassigned'}.`
  } catch {
    feedback.value =
      'Could not update all selected faces. Results have been refreshed; review the selection and try again.'
  }
}
watch(
  () => route.fullPath,
  () => {
    clear()
    feedback.value = ''
  },
)
watch(
  () => props.faces.map((face) => face.id),
  (ids) => {
    const available = new Set(ids)
    selectedIds.value = new Set([...selectedIds.value].filter((id) => available.has(id)))
    if (anchor.value && !available.has(anchor.value)) anchor.value = null
  },
)
</script>
<template>
  <div
    class="col-span-full grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6"
    :class="selected.length > 0 && 'pb-40 sm:pb-24'"
  >
    <p v-if="allowed && faces.length" class="col-span-full text-sm text-muted-foreground">
      Select faces to verify or unassign them. Shift-select a range; open a face to inspect its
      source.
    </p>
    <p
      v-if="feedback"
      class="col-span-full text-sm"
      :role="mutation.isError.value ? 'alert' : 'status'"
    >
      {{ feedback }}
    </p>
    <PersonFaceCard
      v-for="face in faces"
      :key="face.id"
      :face="face"
      :person-name="personName"
      :selectable="allowed"
      :selected="selectedIds.has(face.id)"
      :selection-enabled="selected.length > 0"
      :busy="busy"
      @toggle="select(face.id, $event)"
      @add="select(face.id, $event, true)"
    />
    <SelectedFaceActions
      v-if="selected.length"
      :count="selected.length"
      :busy="busy"
      @clear="clear"
    >
      <template #description
        >Click faces to add them; use the checkboxes to remove them or Shift-select a range.
        Unassigning keeps the face and source image.</template
      >
      <Button type="button" size="sm" variant="outline" :disabled="busy" @click="review('unassign')"
        ><Unlink aria-hidden="true" />{{
          busy && mutation.variables.value?.action === 'unassign'
            ? 'Unassigning…'
            : 'Unassign selected'
        }}</Button
      >
      <Button
        type="button"
        size="sm"
        :disabled="busy || !unverified.length"
        @click="review('verify')"
        ><BadgeCheck aria-hidden="true" />{{
          busy && mutation.variables.value?.action === 'verify'
            ? 'Verifying…'
            : `Verify selected (${unverified.length})`
        }}</Button
      >
    </SelectedFaceActions>
  </div>
</template>
