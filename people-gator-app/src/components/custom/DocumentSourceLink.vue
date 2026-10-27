<script setup lang="ts">
import { ExternalLink } from '@lucide/vue'
import UiTooltip from './UiTooltip.vue'

defineProps<{ url: string }>()
</script>

<template>
  <UiTooltip text="Národní digitální knihovna">
    <a
      :href="url"
      target="_blank"
      rel="noopener noreferrer"
      aria-label="NDK – Národní digitální knihovna"
      data-slot="document-source-link"
      class="inline-flex items-center gap-1 underline underline-offset-4"
    >
      NDK
      <ExternalLink class="size-3 shrink-0" aria-hidden="true" />
    </a>
  </UiTooltip>
</template>
