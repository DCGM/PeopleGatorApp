<script setup lang="ts">
import UiTooltip from './UiTooltip.vue'
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import { linkTooltip } from '@/lib/entity-links'
import type { CSSProperties } from 'vue'

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
  }>(),
  { showBadgeNames: true },
)

const emit = defineEmits<{
  selectLine: [index: number]
  selectFace: [faceId: string]
}>()



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

    <UiTooltip v-for="face in faces" :key="face.id" :text="linkTooltip(face)">
    <button
      v-if="face.position.width > 0 && face.position.height > 0"
      :key="face.id"
      type="button"
      data-region-type="face"
      class="pointer-events-auto absolute border-2 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      :class="faceSelectionClasses[faceSelectionState(face)]"
      :style="regionStyle(face.position)"
      :aria-label="`Select ${face.name}: ${linkTooltip(face)}`"
      :aria-pressed="face.id === selectedFaceId"
      @click.stop="emit('selectFace', face.id)"
    >
      <EntityLinkStateBadge v-bind="face" :focusable="false" :compact="!showBadgeNames" :label="face.name"
        class="absolute -left-1 -top-7 h-6 rounded-full shadow-xs" :class="showBadgeNames ? 'max-w-40' : 'size-6'" />
    </button>
    </UiTooltip>
  </div>
</template>
