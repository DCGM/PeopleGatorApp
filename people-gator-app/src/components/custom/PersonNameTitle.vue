<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'
import type { LocationQueryRaw } from 'vue-router'
import { ChevronRight } from '@lucide/vue'
import { ItemTitle } from '@/components/ui/item'

/**
 * The person-card name: a heading that links to the person's page with an
 * arrow when it names a person, and the same text style when it does not.
 */
const props = defineProps<{
  name: string
  personId?: string | null
  /** Context added to the person link, such as the face it was opened from. */
  query?: LocationQueryRaw
  linkClass?: HTMLAttributes['class']
  ariaLabel?: string
}>()
const to = computed(() =>
  props.personId
    ? {
        name: 'person-detail',
        params: { personId: props.personId },
        // Only explicit context; source filters never follow (#109).
        query: props.query ?? {},
      }
    : undefined,
)
const heading =
  'flex min-h-8 min-w-0 w-full items-center gap-1.5 rounded-sm border border-transparent px-1 py-0.5'
</script>

<template>
  <ItemTitle class="min-w-0 w-full max-w-full">
    <RouterLink
      v-if="to"
      :to="to"
      class="group flex min-w-0 w-full items-center gap underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      :class="linkClass"
      :aria-label="ariaLabel"
    >
      <h4 :class="heading">
        <span class="min-w-0 truncate">{{ name }}</span>
        <ChevronRight
          class="size-[1.15em] shrink-0 transition-transform group-hover:translate-x-1 group-focus-visible:translate-x-1"
          aria-hidden="true"
        />
      </h4>
    </RouterLink>
    <h4 v-else :class="heading">
      <span class="min-w-0 truncate">{{ name }}</span>
    </h4>
  </ItemTitle>
</template>
