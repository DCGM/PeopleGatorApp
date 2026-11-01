<script setup lang="ts">
import { computed, ref } from 'vue'

import { mentionStateFillClasses } from '@/lib/entity-links'
import type { MinimapLine } from '@/viewmodels/teleprompter'

const props = defineProps<{
  lines: MinimapLine[]
  /** Original indices of the first and last lines inside the text viewport. */
  viewport: { first: number; last: number } | null
}>()

const emit = defineEmits<{ navigate: [index: number]; scroll: [deltaY: number] }>()

// Each line is a 2-unit bar with a 1-unit gap; the SVG scales to fit the column.
const ROW = 3
const BAR = 2
const height = computed(() => Math.max(1, props.lines.length * ROW))
const element = ref<SVGSVGElement | null>(null)
let dragging = false

function lineAt(event: PointerEvent) {
  const bounds = element.value?.getBoundingClientRect()
  if (!bounds || bounds.height <= 0 || !props.lines.length) return null
  const ratio = (event.clientY - bounds.top) / bounds.height
  return Math.min(props.lines.length - 1, Math.max(0, Math.floor(ratio * props.lines.length)))
}

function navigate(event: PointerEvent) {
  const index = lineAt(event)
  if (index !== null) emit('navigate', index)
}

function start(event: PointerEvent) {
  if (event.button !== 0) return
  dragging = true
  element.value?.setPointerCapture?.(event.pointerId)
  navigate(event)
}

function move(event: PointerEvent) {
  if (dragging) navigate(event)
}

function stop(event: PointerEvent) {
  dragging = false
  element.value?.releasePointerCapture?.(event.pointerId)
}
</script>

<template>
  <!-- Replaces the text column's scrollbar; the text column remains the accessible way to read and scroll. -->
  <svg
    ref="element"
    data-teleprompter-minimap
    aria-hidden="true"
    class="block max-h-full w-full cursor-pointer touch-none select-none"
    :style="{ height: `${height}px` }"
    :viewBox="`0 0 100 ${height}`"
    preserveAspectRatio="none"
    @pointerdown="start"
    @pointermove="move"
    @pointerup="stop"
    @pointercancel="stop"
    @wheel.prevent="emit('scroll', $event.deltaY)"
  >
    <g
      v-for="line in lines"
      :key="line.index"
      :data-minimap-line="line.index"
      :data-included="line.included ? 'true' : 'false'"
    >
      <rect
        x="0"
        :y="line.index * ROW"
        :width="line.width * 100"
        :height="BAR"
        :class="line.included ? 'minimap-included' : 'minimap-hidden'"
      />
      <template v-if="line.included">
        <rect
          v-for="segment in line.segments"
          :key="segment.key"
          data-minimap-segment
          :x="segment.start * 100"
          :y="line.index * ROW"
          :width="Math.max(1.5, segment.width * 100)"
          :height="BAR"
          :class="segment.related ? 'minimap-related' : mentionStateFillClasses[segment.state]"
        />
      </template>
    </g>
    <rect
      v-if="viewport"
      data-minimap-viewport
      class="minimap-viewport"
      x="0"
      :y="viewport.first * ROW - 0.5"
      width="100"
      :height="(viewport.last - viewport.first + 1) * ROW"
      vector-effect="non-scaling-stroke"
    />
  </svg>
</template>

<style scoped>
.minimap-included {
  fill: color-mix(in srgb, var(--muted-foreground) 55%, transparent);
}
.minimap-hidden {
  fill: color-mix(in srgb, var(--muted-foreground) 18%, transparent);
}
.minimap-related {
  fill: var(--accent);
}
.minimap-viewport {
  fill: color-mix(in srgb, var(--foreground) 8%, transparent);
  stroke: color-mix(in srgb, var(--foreground) 35%, transparent);
  stroke-width: 1px;
}
</style>
