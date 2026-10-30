<script setup lang="ts">
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import { linkTooltip } from '@/lib/entity-links'
import { computed, nextTick, onBeforeUnmount, ref, watch, type CSSProperties } from 'vue'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'

import { lineMentionsEntity } from '@/viewmodels/document-workspace.types'
import type {
  Face,
  PageViewportBounds,
  TranscriptionLine,
} from '@/viewmodels/document-workspace.types'

const props = withDefaults(
  defineProps<{
    pageBounds: PageViewportBounds | null
    transcription: TranscriptionLine[]
    faces: Face[]
    selectedLineIndex: number
    selectedFaceId: string | null
    selectedPersonId: string | null
    selectedCandidateFaceId: string | null
    showBadgeNames?: boolean
    viewer?: HTMLElement | null
    actionsEnabled?: boolean
  }>(),
  { showBadgeNames: true, actionsEnabled: true },
)

const emit = defineEmits<{
  selectLine: [index: number]
  selectFace: [faceId: string]
  clearFace: []
}>()

const overlay = ref<HTMLElement | null>(null)
const drawableFaces = computed(() =>
  props.faces.filter((face) => face.position.width > 0 && face.position.height > 0),
)
// Hidden by an outside click; the face stays selected until another selection.
const dismissedFaceId = ref<string | null>(null)
watch(
  () => props.selectedFaceId,
  () => (dismissedFaceId.value = null),
)

function detectionButton(faceId: string) {
  return overlay.value?.querySelector<HTMLButtonElement>(`[data-detection-id="${faceId}"]`)
}

function activateFace(faceId: string) {
  dismissedFaceId.value = null
  emit('selectFace', faceId)
}

// Move focus into the actions only when the box itself was activated, so
// selections from the keyboard shortcuts, toolbar or gallery keep their focus.
// The panel itself takes focus, not its first button, so no tooltip pops up.
async function openFocus(event: Event, faceId: string) {
  event.preventDefault()
  if (document.activeElement !== detectionButton(faceId)) return
  await nextTick()
  document
    .querySelector<HTMLElement>(`[data-detection-actions="${faceId}"]`)
    ?.focus({ preventScroll: true })
}

const dragThreshold = 6
let outsidePress: { x: number; y: number; faceId: string; cancelled: boolean } | null = null
function finishOutsidePress(event: PointerEvent) {
  const press = outsidePress
  outsidePress = null
  window.removeEventListener('pointerup', finishOutsidePress, true)
  window.removeEventListener('pointercancel', finishOutsidePress, true)
  if (!press || press.cancelled || event.type === 'pointercancel') return
  if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > dragThreshold) return
  if (props.selectedFaceId === press.faceId) dismissedFaceId.value = press.faceId
}
// Close on an outside click, but not when the press starts a scan drag or pinch.
function pressOutside(event: CustomEvent<{ originalEvent: PointerEvent }>, faceId: string) {
  event.preventDefault()
  const { clientX, clientY, pointerType } = event.detail.originalEvent
  // Reka reports touch only after a tap's click; touch drags never get here.
  if (pointerType === 'touch') {
    if (props.selectedFaceId === faceId) dismissedFaceId.value = faceId
    return
  }
  if (outsidePress) {
    outsidePress.cancelled = true
    return
  }
  outsidePress = { x: clientX, y: clientY, faceId, cancelled: false }
  window.addEventListener('pointerup', finishOutsidePress, true)
  window.addEventListener('pointercancel', finishOutsidePress, true)
}
onBeforeUnmount(() => {
  window.removeEventListener('pointerup', finishOutsidePress, true)
  window.removeEventListener('pointercancel', finishOutsidePress, true)
})

function returnFocus(event: Event, faceId: string) {
  event.preventDefault()
  const active = document.activeElement
  if (active !== document.body && !(event.target as HTMLElement).contains(active)) return
  const selected = props.selectedFaceId ? detectionButton(props.selectedFaceId) : null
  ;(selected ?? detectionButton(faceId))?.focus({ preventScroll: true })
}

const faceSelectionClasses = {
  selected: 'z-10 border-secondary bg-secondary/25 ring-2 ring-secondary/70',
  matched: 'border-accent bg-accent/15 ring-2 ring-accent/80',
  default: 'border-gray-500/20 bg-transparent hover:bg-accent/20',
} as const

function faceSelectionState(face: Face): keyof typeof faceSelectionClasses {
  if (face.id === props.selectedFaceId) return 'selected'
  if (face.personId === props.selectedPersonId || face.id === props.selectedCandidateFaceId)
    return 'matched'
  return 'default'
}

const lineSelectionClasses = {
  selected: 'z-10 border-accent bg-accent/20 ring-1 ring-background/75',
  // The current line keeps its accent; an orange ring still shows it is a mention.
  selectedMentioned: 'z-10 border-accent bg-accent/20 ring-2 ring-orange-500',
  mentioned: 'border-orange-500 bg-orange-500/15 hover:bg-orange-500/30',
  default: 'border-transparent hover:border-accent/70 hover:bg-accent/10',
} as const

function lineMentionsSelectedPerson(index: number) {
  return (
    props.selectedPersonId !== null &&
    lineMentionsEntity(props.transcription[index], props.selectedPersonId)
  )
}

function lineSelectionState(index: number): keyof typeof lineSelectionClasses {
  const mentioned = lineMentionsSelectedPerson(index)
  if (index === props.selectedLineIndex) return mentioned ? 'selectedMentioned' : 'selected'
  return mentioned ? 'mentioned' : 'default'
}

function lineLabel(line: TranscriptionLine, index: number) {
  const label = `Select line ${index + 1}: ${line.text}`
  return lineMentionsSelectedPerson(index) ? `${label} (mentions the selected person)` : label
}

function regionStyle(position: Face['position']): CSSProperties {
  if (!props.pageBounds) return { display: 'none' }

  return {
    left: `${props.pageBounds.left + (position.left / 100) * props.pageBounds.width}px`,
    top: `${props.pageBounds.top + (position.top / 100) * props.pageBounds.height}px`,
    width: `${(position.width / 100) * props.pageBounds.width}px`,
    height: `${(position.height / 100) * props.pageBounds.height}px`,
  }
}
</script>

<template>
  <div
    ref="overlay"
    data-slot="document-page-overlay"
    class="pointer-events-none absolute inset-0 z-10 overflow-hidden"
  >
    <button
      v-for="(line, index) in transcription"
      :key="line.id"
      type="button"
      data-region-type="line"
      class="pointer-events-auto absolute border-2 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      :class="lineSelectionClasses[lineSelectionState(index)]"
      :style="regionStyle(line.position)"
      :aria-label="lineLabel(line, index)"
      :aria-pressed="index === selectedLineIndex"
      @click.stop="emit('selectLine', index)"
    />

    <Popover
      v-for="face in drawableFaces"
      :key="face.id"
      :open="actionsEnabled && selectedFaceId === face.id && dismissedFaceId !== face.id"
    >
      <PopoverAnchor as-child>
        <button
          type="button"
          data-region-type="face"
          :data-detection-id="face.id"
          class="pointer-events-auto absolute border-2 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          :class="faceSelectionClasses[faceSelectionState(face)]"
          :style="regionStyle(face.position)"
          :aria-label="`Select ${face.name}: ${linkTooltip(face)}`"
          :aria-pressed="face.id === selectedFaceId"
          :aria-expanded="
            actionsEnabled ? face.id === selectedFaceId && dismissedFaceId !== face.id : undefined
          "
          :aria-haspopup="actionsEnabled ? 'dialog' : undefined"
          @pointerdown.stop
          @click.stop="activateFace(face.id)"
          @keydown.esc="face.id === selectedFaceId && emit('clearFace')"
        >
          <EntityLinkStateBadge
            v-bind="face"
            :focusable="false"
            :tooltip="false"
            :compact="!showBadgeNames"
            :label="face.name"
            class="absolute -left-1 -top-7 h-6 rounded-full shadow-xs"
            :class="showBadgeNames ? 'max-w-40' : 'size-6'"
          />
        </button>
      </PopoverAnchor>
      <PopoverContent
        v-if="$slots.actions"
        :data-detection-actions="face.id"
        side="top"
        class="w-auto p-1"
        :collision-boundary="viewer ?? undefined"
        :collision-padding="8"
        sticky="always"
        update-position-strategy="always"
        prioritize-position
        :aria-label="`Actions for ${face.name}`"
        @open-auto-focus="openFocus($event, face.id)"
        @focus-outside.prevent
        @pointer-down-outside="pressOutside($event, face.id)"
        @keydown.esc="emit('clearFace')"
        @close-auto-focus="returnFocus($event, face.id)"
      >
        <slot name="actions" :face="face" />
      </PopoverContent>
    </Popover>
  </div>
</template>
