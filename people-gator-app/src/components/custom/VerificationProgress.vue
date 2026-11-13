<script setup lang="ts">
import { computed } from 'vue'
import { verificationProgress } from '@/lib/verification'

const props = defineProps<{
  verified?: number | null
  total?: number | null
  hideCount?: boolean
}>()
const RADIUS = 6
const CIRCUMFERENCE = 2 * Math.PI * RADIUS
const share = computed(() => verificationProgress(props.verified, props.total))
const known = computed(() => props.verified != null && props.total != null)
const label = computed(() =>
  known.value ? `${props.verified} of ${props.total} pages verified` : 'Verified pages unknown',
)
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center gap-1.5 text-sm tabular-nums"
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
    <span v-if="!hideCount" aria-hidden="true">{{ known ? `${verified}/${total}` : '–/–' }}</span>
  </span>
</template>
