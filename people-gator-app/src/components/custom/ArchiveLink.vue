<script setup lang="ts">
import { ExternalLink } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'

// Compact links show only the icon below `sm`; the accessible name keeps the NDK label.
defineProps<{ url?: string | null; kind?: 'page' | 'document'; compact?: boolean }>()
</script>

<template>
  <Badge
    v-if="url"
    as="a"
    variant="outline"
    :href="url"
    title="Digitální knihovna"
    target="_blank"
    rel="noopener noreferrer"
    :aria-label="`NDK: open ${kind ?? 'page'} in Digitální knihovna (new tab)`"
    class="relative z-20 max-w-full self-start whitespace-normal bg-background/95 text-foreground"
    @click.stop
    @keydown.stop
  >
    <span :class="compact && 'max-sm:sr-only'">NDK</span>
    <ExternalLink class="size-3 shrink-0" aria-hidden="true" />
  </Badge>
</template>
