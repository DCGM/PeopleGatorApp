<script setup lang="ts">
import { computed, ref } from 'vue'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { verificationProgress, type ProgressBreakdown } from '@/lib/verification'
import ProgressBreakdownPanel from './ProgressBreakdown.vue'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  verified?: number | null
  total?: number | null
  hideCount?: boolean
  /** What is being verified; the default slot may show its icon after the ring. */
  noun?: string
  /** Tooltip explaining the ring and splitting its total; makes the ring focusable. */
  breakdown?: ProgressBreakdown
}>()
// Closed here on Escape too: a parent may stop the key before it reaches the tooltip layer.
const open = ref(false)
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
  <TooltipProvider v-if="breakdown" :delay-duration="200">
    <Tooltip v-model:open="open">
      <TooltipTrigger as-child>
        <span
          class="inline-flex shrink-0 items-center gap-1 text-sm tabular-nums"
          role="img"
          :aria-label="label"
          tabindex="0"
          data-verification-progress
          @keydown.esc="open = false"
          v-bind="$attrs"
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
          <span v-if="!hideCount" aria-hidden="true">{{
            known ? `${verified}/${total}` : '–/–'
          }}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top"><ProgressBreakdownPanel :breakdown="breakdown" /></TooltipContent>
    </Tooltip>
  </TooltipProvider>
  <span
    v-else
    class="inline-flex shrink-0 items-center gap-1.5 text-sm tabular-nums"
    role="img"
    :aria-label="label"
    :title="label"
    data-verification-progress
    v-bind="$attrs"
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
