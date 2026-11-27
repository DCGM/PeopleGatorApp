<script setup lang="ts">
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import { linkTooltip } from '@/lib/entity-links'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type CSSProperties } from 'vue'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { SCAN_DRAG_THRESHOLD } from '@/composables/scan-viewport'
import { cardInUse, movedIntoNestedLayer, useHoverCard } from '@/composables/hover-card'

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
    /** Lines holding the name mentions selected for editing (#176). */
    selectedMentionLines?: readonly number[]
  }>(),
  { showBadgeNames: true, actionsEnabled: true, selectedMentionLines: () => [] },
)
const mentionLines = computed(() => new Set(props.selectedMentionLines))
function lineSelected(index: number) {
  return index === props.selectedLineIndex || mentionLines.value.has(index)
}

const emit = defineEmits<{
  selectLine: [index: number]
  selectFace: [faceId: string]
  clearFace: []
}>()

const overlay = ref<HTMLElement | null>(null)
const drawableFaces = computed(() =>
  props.faces.filter((face) => face.position.width > 0 && face.position.height > 0),
)
// The selected face expands its name tag into its details card. A click off it
// on the scan unselects it; the card also collapses at once, in case the parent
// keeps the face selected. A hovered face shows its card instead, until the
// pointer leaves; using that card selects the face (#203).
const dismissedFaceId = ref<string | null>(null)
watch(
  () => props.selectedFaceId,
  (selected) => {
    dismissedFaceId.value = null
    // Another selection takes over from a hovered card.
    if (hoverCard.target.value !== selected) hoverCard.close(true)
  },
)

const slots = defineSlots<{ card?: (props: { face: Face }) => unknown }>()
const hoverCard = useHoverCard<string>()
// Cards that opened on hover only; closing one leaves focus where it is.
const hoverOnly = new Set<string>()
watch(hoverCard.target, (faceId) => {
  if (faceId && faceId !== props.selectedFaceId) hoverOnly.add(faceId)
})
watch(
  () => props.actionsEnabled,
  (enabled) => enabled || hoverCard.close(true),
)
const cardFaceId = computed(() => {
  const hovered = hoverCard.target.value
  if (hovered && drawableFaces.value.some((face) => face.id === hovered)) return hovered
  return dismissedFaceId.value === props.selectedFaceId ? null : props.selectedFaceId
})
function cardOpen(faceId: string) {
  return props.actionsEnabled && Boolean(slots.card) && cardFaceId.value === faceId
}

function detectionCard(faceId: string) {
  return document.querySelector<HTMLElement>(`[data-detection-card="${faceId}"]`)
}
function hoverFace(event: MouseEvent, faceId: string) {
  // Not while dragging the scan, or while the open card is in use.
  if (event.buttons || cardInUse(document.querySelector('[data-detection-card]'))) return
  if (faceId === cardFaceId.value) hoverCard.hold()
  else hoverCard.open(faceId)
}
/** Using the hovered card selects its face, so the card's actions apply to it. */
function selectHovered(faceId: string) {
  hoverOnly.delete(faceId)
  if (props.selectedFaceId !== faceId) emit('selectFace', faceId)
}
function leaveCard(event: MouseEvent, faceId: string) {
  if (movedIntoNestedLayer(event, event.currentTarget as Element)) selectHovered(faceId)
  else hoverCard.close()
}

function detectionButton(faceId: string) {
  return overlay.value?.querySelector<HTMLButtonElement>(`[data-detection-id="${faceId}"]`)
}

async function activateFace(faceId: string) {
  // A card already open from hovering gets focus as a newly opened one does.
  const shown = cardOpen(faceId)
  hoverOnly.delete(faceId)
  dismissedFaceId.value = null
  emit('selectFace', faceId)
  if (!shown || document.activeElement !== detectionButton(faceId)) return
  await nextTick()
  detectionCard(faceId)?.focus({ preventScroll: true })
}

// Move focus into the card only when the box itself was activated, so
// selections from the keyboard shortcuts, toolbar or gallery keep their focus.
// The card itself takes focus, not its first button, so no tooltip pops up.
async function openFocus(event: Event, faceId: string) {
  event.preventDefault()
  // Hovering shows the card without moving focus.
  if (props.selectedFaceId !== faceId) return
  if (document.activeElement !== detectionButton(faceId)) return
  await nextTick()
  detectionCard(faceId)?.focus({ preventScroll: true })
}

function clickOff(faceId: string) {
  if (props.selectedFaceId !== faceId) return
  hoverCard.close(true)
  dismissedFaceId.value = faceId
  emit('clearFace')
}

let outsidePress: { x: number; y: number; faceId: string; cancelled: boolean } | null = null
function finishOutsidePress(event: PointerEvent) {
  const press = outsidePress
  outsidePress = null
  window.removeEventListener('pointerup', finishOutsidePress, true)
  window.removeEventListener('pointercancel', finishOutsidePress, true)
  if (!press || press.cancelled || event.type === 'pointercancel') return
  if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > SCAN_DRAG_THRESHOLD) return
  clickOff(press.faceId)
}
// Reka reports a touch press only on the next click. A touch drag has none, so a later
// click elsewhere, such as on the toolbar, would report that stale press.
let latestPress: PointerEvent | null = null
function notePress(event: PointerEvent) {
  latestPress = event
}
onMounted(() => window.addEventListener('pointerdown', notePress, true))
// Unselect on an outside click on the scan, but not when the press starts a scan
// drag or pinch. Work elsewhere, such as searching People for this face, keeps it.
function pressOutside(event: CustomEvent<{ originalEvent: PointerEvent }>, faceId: string) {
  event.preventDefault()
  const press = event.detail.originalEvent
  const { clientX, clientY, pointerType, target } = press
  if (props.viewer && !(target instanceof Node && props.viewer.contains(target))) return
  // A press on a face box selects that face; clearing first would flash the selection off.
  if (target instanceof Element && target.closest('[data-region-type="face"]')) return
  if (pointerType === 'touch') {
    if (press === latestPress) clickOff(faceId)
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
  window.removeEventListener('pointerdown', notePress, true)
  window.removeEventListener('pointerup', finishOutsidePress, true)
  window.removeEventListener('pointercancel', finishOutsidePress, true)
})

function returnFocus(event: Event, faceId: string) {
  event.preventDefault()
  const active = document.activeElement
  // A card that was only hovered never took focus, and one hidden by a hovered card keeps it.
  if (hoverOnly.delete(faceId) || hoverCard.target.value) return
  if (active !== document.body && !(event.target as HTMLElement).contains(active)) return
  const selected = props.selectedFaceId ? detectionButton(props.selectedFaceId) : null
  ;(selected ?? detectionButton(faceId))?.focus({ preventScroll: true })
}

// Faces share the lines' colors: accent for the selection, orange for the selected person.
const faceSelectionClasses = {
  selected: 'z-10 border-accent bg-accent/20 ring-1 ring-background/75',
  selectedMatched: 'z-10 border-accent bg-accent/20 ring-2 ring-orange-500',
  matched: 'border-orange-500 bg-orange-500/15 hover:bg-orange-500/30',
  default: 'border-gray-500/20 bg-transparent hover:bg-accent/20',
} as const

function faceSelectionState(face: Face): keyof typeof faceSelectionClasses {
  const ofSelectedPerson = face.personId !== null && face.personId === props.selectedPersonId
  if (face.id === props.selectedFaceId) return ofSelectedPerson ? 'selectedMatched' : 'selected'
  if (ofSelectedPerson || face.id === props.selectedCandidateFaceId) return 'matched'
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
  if (lineSelected(index)) return mentioned ? 'selectedMentioned' : 'selected'
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
      :aria-pressed="lineSelected(index)"
      @click.stop="emit('selectLine', index)"
    />

    <Popover v-for="face in drawableFaces" :key="face.id" :open="cardOpen(face.id)">
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
          :aria-expanded="actionsEnabled && $slots.card ? cardOpen(face.id) : undefined"
          :aria-haspopup="actionsEnabled && $slots.card ? 'dialog' : undefined"
          @mouseenter="hoverFace($event, face.id)"
          @mouseleave="hoverCard.close()"
          @click.stop="activateFace(face.id)"
          @keydown.esc="face.id === selectedFaceId && emit('clearFace')"
        >
          <EntityLinkStateBadge
            v-show="!cardOpen(face.id)"
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
        v-if="$slots.card"
        :data-detection-card="face.id"
        side="top"
        align="start"
        :side-offset="4"
        class="max-h-(--reka-popover-content-available-height) w-64 max-w-[calc(100vw-2rem)] overflow-y-auto p-0"
        :collision-boundary="viewer ?? undefined"
        :collision-padding="8"
        sticky="always"
        hide-when-detached
        update-position-strategy="always"
        prioritize-position
        :aria-label="`Details for ${face.personId ? face.name : 'unassigned face'}`"
        @mouseenter="hoverCard.hold"
        @mouseleave="leaveCard($event, face.id)"
        @pointerdown.capture="selectHovered(face.id)"
        @focusin="selectHovered(face.id)"
        @open-auto-focus="openFocus($event, face.id)"
        @focus-outside.prevent
        @pointer-down-outside="pressOutside($event, face.id)"
        @keydown.esc="emit('clearFace')"
        @close-auto-focus="returnFocus($event, face.id)"
      >
        <slot name="card" :face="face" />
      </PopoverContent>
    </Popover>
  </div>
</template>
