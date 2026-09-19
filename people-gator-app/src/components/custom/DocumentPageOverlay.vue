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
      :class="
        index === selectedLineIndex
          ? 'border-accent bg-accent/20 ring-1 ring-background/75'
          : 'border-transparent hover:border-accent/70 hover:bg-accent/10'
      "
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
      :class="
        face.id === selectedFaceId
          ? 'border-secondary bg-secondary/15 ring-2 ring-background/80'
          : face.personId === selectedPersonId || face.id === selectedCandidateFaceId
            ? 'border-accent bg-accent/25 ring-2 ring-accent/70'
            : 'border-accent/60 bg-accent/5 hover:bg-accent/20'
      "
      :style="regionStyle(face.position)"
      :aria-label="`Select ${face.name}`"
      :aria-pressed="face.id === selectedFaceId"
      @click.stop="emit('selectFace', face.id)"
    >
      <Badge
        as="span"
        data-face-status-badge
        class="absolute -left-1 -top-6 size-5 rounded-full border-background p-0 shadow-sm [&>svg]:size-3"
        :class="faceStatusBadgeClasses[face.status]"
        :title="face.status === 'assigned' ? 'Assigned' : 'Unassigned'"
        aria-hidden="true"
      >
        <component :is="faceStatusIcons[face.status]" />
      </Badge>
    </button>
  </div>
</template>
