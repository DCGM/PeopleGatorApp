<script setup lang="ts">
import { computed } from 'vue'
import { verificationProgress } from '@/lib/verification'

const props = defineProps<{
  verified?: number | null
  total?: number | null
  hideCount?: boolean
  /** What is being verified; the default slot may show its icon after the ring. */
  noun?: string
}>()
const RADIUS = 6
const CIRCUMFERENCE = 2 * Math.PI * RADIUS
const share = computed(() => verificationProgress(props.verified, props.total))
const known = computed(() => props.verified != null && props.total != null)
const label = computed(() =>
  known.value
    ? `${props.verified} of ${props.total} ${props.noun ?? 'pages'} verified`
    : `Verified ${props.noun ?? 'pages'} unknown`,
)
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center gap-1 text-sm tabular-nums"
    role="img"
    :aria-label="label"
    :title="label"
    data-verification-progress
  >
    <svg viewBox="0 0 16 16" class="size-4 -rotate-90" aria-hidden="true">
      <circle cx="8" cy="8" :r="RADIUS" fill="none" stroke-width="2.5" class="stroke-muted" />
      <circle
        v-if="share > 0"
        cx="8"
        cy="8"
        :r="RADIUS"
        fill="none"
        stroke-width="2.5"
        stroke-linecap="round"
        class="stroke-emerald-500"
        :stroke-dasharray="`${share * CIRCUMFERENCE} ${CIRCUMFERENCE}`"
      />
    </svg>
    <slot />
    <span v-if="!hideCount" aria-hidden="true">{{ known ? `${verified}/${total}` : '–/–' }}</span>
  </span>
</template>
