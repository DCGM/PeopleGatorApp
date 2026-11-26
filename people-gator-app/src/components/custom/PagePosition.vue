<script setup lang="ts">
import { ExternalLink } from '@lucide/vue'
import { pagePosition, pagePositionLabel } from '@/lib/page-position'
import { sourceLinkClass, sourceLinkTextClass } from '@/lib/source-link'

/** With `url`, the position opens that page in the digital library. */
defineProps<{ number?: number | null; total?: number | null; url?: string | null }>()
</script>

<template>
  <small class="tabular-nums">
    <a
      v-if="url"
      :href="url"
      target="_blank"
      rel="noopener noreferrer"
      title="Open page in Digitální knihovna"
      :class="sourceLinkClass"
      data-slot="page-source-link"
      ><span :class="sourceLinkTextClass" aria-hidden="true">{{ pagePosition(number, total) }}</span
      ><span class="sr-only"
        >{{ pagePositionLabel(number, total) }}: open page in Digitální knihovna (new tab)</span
      ><ExternalLink class="size-3 shrink-0" aria-hidden="true"
    /></a>
    <template v-else
      ><span aria-hidden="true">{{ pagePosition(number, total) }}</span
      ><span class="sr-only">{{ pagePositionLabel(number, total) }}</span></template
    >
  </small>
</template>
