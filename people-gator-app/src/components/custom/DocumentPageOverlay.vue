<script setup lang="ts">
import { Link, UserRoundX } from '@lucide/vue'
import type { Component, CSSProperties } from 'vue'

import type {
  Face,
  FaceStatus,
  PageViewportBounds,
  TranscriptionLine,
} from '@/components/custom/document-page.types'
import { Badge } from '@/components/ui/badge'

const props = defineProps<{
  pageBounds: PageViewportBounds | null
  transcription: TranscriptionLine[]
  faces: Face[]
  selectedLineIndex: number
  selectedFaceId: string | null
  selectedPersonId: string | null
  selectedCandidateFaceId: string | null
}>()

const emit = defineEmits<{
  selectLine: [index: number]
  selectFace: [faceId: string]
}>()

const faceStatusIcons = {
  assigned: Link,
  unassigned: UserRoundX,
} satisfies Record<FaceStatus, Component>

const faceStatusBadgeClasses = {
  assigned: 'bg-emerald-700 text-white',
  unassigned: 'bg-muted-foreground text-background',
} satisfies Record<FaceStatus, string>

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
  default: 'border-transparent hover:border-accent/70 hover:bg-accent/10',
} as const

function lineSelectionState(index: number): keyof typeof lineSelectionClasses {
  return index === props.selectedLineIndex ? 'selected' : 'default'
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
      :aria-label="`Select line ${index + 1}: ${line.text}`"
      :aria-pressed="index === selectedLineIndex"
      @click.stop="emit('selectLine', index)"
    />

    <button
      v-for="face in faces"
      :key="face.id"
      type="button"
      data-region-type="face"
      class="pointer-events-auto absolute border-2 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      :class="faceSelectionClasses[faceSelectionState(face)]"
      :style="regionStyle(face.position)"
      :aria-label="`Select ${face.name}`"
      :aria-pressed="face.id === selectedFaceId"
      @click.stop="emit('selectFace', face.id)"
    >
      <Badge
        data-face-status-badge
        class="absolute -left-1 -top-7 h-6 max-w-40 gap-1.5 rounded-full border-0 px-2 py-0 text-xs font-light shadow-xs"
        :class="faceStatusBadgeClasses[face.status]"
        :title="face.status === 'assigned' ? 'Assigned' : 'Unassigned'"
        aria-hidden="true"
      >
        <component :is="faceStatusIcons[face.status]" class="size-3.5 shrink-0" />
        <span class="min-w-0 truncate">{{ face.name }}</span>
      </Badge>
    </button>
  </div>
</template>
