<script setup lang="ts">
import { pagePosition, pagePositionLabel } from '@/lib/page-position'

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
      class="rounded-sm underline decoration-dotted underline-offset-4 outline-none hover:decoration-solid focus-visible:ring-3 focus-visible:ring-ring/50"
      data-slot="page-source-link"
      ><span aria-hidden="true">{{ pagePosition(number, total) }}</span
      ><span class="sr-only"
        >{{ pagePositionLabel(number, total) }}: open page in Digitální knihovna (new tab)</span
      ></a
    >
    <template v-else
      ><span aria-hidden="true">{{ pagePosition(number, total) }}</span
      ><span class="sr-only">{{ pagePositionLabel(number, total) }}</span></template
    >
  </small>
</template>
