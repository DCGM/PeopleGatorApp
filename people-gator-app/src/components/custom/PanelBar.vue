<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

// One height for every page editor top bar. Controls stay on one line, centered
// when they fit and scrolling horizontally from the first control when they do not.
const props = withDefaults(
  defineProps<{
    as?: string
    label?: string
    class?: HTMLAttributes['class']
  }>(),
  { as: 'div', label: undefined, class: undefined },
)
</script>

<template>
  <component
    :is="props.as"
    :class="
      cn(
        '@container flex h-14 min-w-0 shrink-0 items-center gap-2 border-b bg-background px-3',
        props.class,
      )
    "
  >
    <slot name="start" />
    <ScrollArea orientation="horizontal" class="min-w-0 flex-1">
      <div
        :role="props.label ? 'toolbar' : undefined"
        :aria-label="props.label"
        class="mx-auto flex w-max items-center gap-2 py-3"
      >
        <slot />
      </div>
    </ScrollArea>
    <slot name="end" />
  </component>
</template>
