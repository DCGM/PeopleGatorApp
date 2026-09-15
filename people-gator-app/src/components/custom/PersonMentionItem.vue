<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'

import type { PersonMention } from '@/components/custom/person-detail.types'

const props = defineProps<{
  mention: PersonMention
}>()
</script>

<template>
  <div class="grid gap-4 sm:grid-cols-[9rem_minmax(0,1fr)_auto] sm:items-center">
    <div>
      <p class="font-mono text-xs font-semibold text-secondary">
        {{ props.mention.library }} · P. {{ props.mention.pageLabel }}
      </p>
      <p class="mt-1 text-sm font-medium">{{ props.mention.documentTitle }}</p>
      <p class="text-xs text-muted-foreground">{{ props.mention.date }}</p>
    </div>
    <blockquote
      class="border-l-2 pl-4 font-serif text-lg leading-7 text-muted-foreground group-hover:text-foreground"
    >
      “{{ props.mention.excerpt }}”
      <footer class="mt-1 font-sans text-xs font-semibold text-accent">
        Matched “{{ props.mention.matchedText }}”
      </footer>
    </blockquote>
    <span
      class="flex items-center gap-2 text-sm font-semibold text-muted-foreground group-hover:text-primary"
    >
      View scan
      <ChevronRight
        class="size-4 transition-transform group-hover:translate-x-1 group-focus:translate-x-1"
        aria-hidden="true"
      />
    </span>
  </div>
</template>
