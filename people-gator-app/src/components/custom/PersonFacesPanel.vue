<script setup lang="ts">
import { BadgeCheck, Image, Unlink } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from '@/components/ui/button'
import FaceGridAction from './FaceGridAction.vue'
import { FACE_GRID_CLASSES, useFaceGrid } from '@/composables/face-grid'
import PersonFaceCard from './PersonFaceCard.vue'
import SelectedFaceActions from './SelectedFaceActions.vue'
import { useCanAnnotate } from '@/composables/can-annotate'
import { useReviewFacesMutation } from '@/query/faces'
import { usePatchEntityMutation } from '@/query/entities'
import type { PersonFace } from '@/viewmodels/person-detail.types'
const props = defineProps<{
  collapsible?: boolean
  hasMore?: boolean
  matchingCount?: number
  faces: PersonFace[]
  personName: string
  personId: string
  thumbnailFaceId?: string | null
  thumbnailMode?: 'automatic' | 'manual'
}>()
const { grid, columns: rowCapacity, style: faceGridStyle } = useFaceGrid()
const expanded = ref(false)
const canExpand = computed(() => props.hasMore || props.faces.length > rowCapacity.value * 2)
const visibleFaces = computed(() =>
  props.collapsible && !expanded.value
    ? props.faces.slice(0, rowCapacity.value * 2 - (canExpand.value ? 1 : 0))
    : props.faces,
)
watch(
  () => props.personId,
  () => {
    expanded.value = false
  },
)
const allowed = useCanAnnotate()
const mutation = useReviewFacesMutation()
const portraitMutation = usePatchEntityMutation()
const route = useRoute()
const selectedIds = ref(new Set<string>())
const anchor = ref<string | null>(null)
const selected = computed(() => props.faces.filter((face) => selectedIds.value.has(face.id)))
const unverified = computed(() => selected.value.filter((face) => face.linkState !== 'verified'))
const busy = computed(() => mutation.isPending.value || portraitMutation.isPending.value)
const currentPortrait = computed(
  () =>
    selected.value.length === 1 &&
    selected.value[0]?.id === props.thumbnailFaceId &&
    props.thumbnailMode === 'manual',
)
const failed = ref(false)
const feedback = ref('')
function toggleExpansion() {
  expanded.value = !expanded.value
  clear()
}
function clear() {
  selectedIds.value = new Set()
  anchor.value = null
}
function select(id: string, event: MouseEvent, addOnly = false) {
  if (busy.value) return
  feedback.value = ''
  failed.value = false
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
  failed.value = false
  try {
    await mutation.mutateAsync({ detectionIds: targets.map((face) => face.id), action })
    clear()
    feedback.value = `${targets.length} ${targets.length === 1 ? 'face' : 'faces'} ${action === 'verify' ? 'verified' : 'unassigned'}.`
  } catch {
    failed.value = true
    feedback.value =
      'Could not update all selected faces. Results have been refreshed; review the selection and try again.'
  }
}
async function useAsPortrait() {
  const face = selected.value[0]
  if (busy.value || !allowed.value || selected.value.length !== 1 || !face) return
  feedback.value = ''
  failed.value = false
  const automatic = currentPortrait.value
  try {
    await portraitMutation.mutateAsync({
      entityId: props.personId,
      body: { thumbnail_face_id: automatic ? null : face.id },
    })
    feedback.value = automatic ? 'Automatic portrait.' : 'Portrait saved.'
  } catch {
    failed.value = true
    feedback.value = 'Save not confirmed. Try again.'
  }
}
watch(
  () => route.fullPath,
  () => {
    clear()
    feedback.value = ''
    failed.value = false
  },
)
watch(
  () => visibleFaces.value.map((face) => face.id),
  (ids) => {
    const available = new Set(ids)
    selectedIds.value = new Set([...selectedIds.value].filter((id) => available.has(id)))
    if (anchor.value && !available.has(anchor.value)) anchor.value = null
  },
)
</script>
<template>
  <div
    ref="grid"
    class="col-span-full"
    :class="[FACE_GRID_CLASSES, selected.length > 0 && 'pb-40 sm:pb-24']"
    :style="faceGridStyle"
  >
    <p
      v-if="feedback && !selected.length"
      class="col-span-full text-sm"
      :role="failed ? 'alert' : 'status'"
    >
      {{ feedback }}
    </p>
    <PersonFaceCard
      v-for="face in visibleFaces"
      :key="face.id"
      :face="face"
      :person-name="personName"
      :portrait="face.id === thumbnailFaceId"
      :selectable="allowed"
      :selected="selectedIds.has(face.id)"
      :selection-enabled="selected.length > 0"
      :busy="busy"
      @toggle="select(face.id, $event)"
      @add="select(face.id, $event, true)"
    />
    <FaceGridAction
      v-if="collapsible && canExpand"
      data-face-overview-toggle
      :label="expanded ? 'Show less' : 'Show all faces'"
      :description="`${matchingCount ?? faces.length} matching faces`"
      :expanded="expanded"
      :full-width="expanded"
      :disabled="busy"
      @activate="toggleExpansion"
    />
    <div v-if="expanded && hasMore" class="col-span-full flex flex-wrap gap-2">
      <slot name="pagination" />
    </div>
    <SelectedFaceActions
      v-if="selected.length"
      :count="selected.length"
      :busy="busy"
      @clear="clear"
    >
      <template #description>
        <p v-if="feedback" :role="failed ? 'alert' : 'status'">{{ feedback }}</p>
      </template>
      <Button
        v-if="selected.length === 1"
        type="button"
        size="sm"
        variant="outline"
        :disabled="busy"
        @click="useAsPortrait"
        ><Image aria-hidden="true" />{{
          portraitMutation.isPending.value
            ? 'Saving…'
            : currentPortrait
              ? 'Use automatic'
              : 'Use as portrait'
        }}</Button
      >
      <Button
        type="button"
        size="sm"
        variant="outline"
        class="border-destructive text-destructive hover:bg-destructive/10 hover:text-destructive dark:border-destructive dark:hover:bg-destructive/10"
        :disabled="busy"
        @click="review('unassign')"
        ><Unlink aria-hidden="true" />{{
          busy && mutation.variables.value?.action === 'unassign'
            ? 'Unassigning…'
            : 'Unassign selected'
        }}</Button
      >
      <Button
        type="button"
        size="sm"
        variant="outline"
        class="border-emerald-600 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800 dark:border-emerald-500 dark:text-emerald-400 dark:hover:bg-emerald-950 dark:hover:text-emerald-300"
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
