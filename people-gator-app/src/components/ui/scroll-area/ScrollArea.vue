<script setup lang="ts">
import type { ScrollAreaRootProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { ScrollAreaCorner, ScrollAreaRoot, ScrollAreaViewport } from 'reka-ui'
import { cn } from '@/lib/utils'
import ScrollBar from './ScrollBar.vue'

const props = withDefaults(
  defineProps<
    ScrollAreaRootProps & {
      class?: HTMLAttributes['class']
      orientation?: 'vertical' | 'horizontal' | 'both'
      viewportProps?: HTMLAttributes
    }
  >(),
  {
    orientation: 'vertical',
  },
)

const delegatedProps = reactiveOmit(props, 'class', 'orientation', 'viewportProps')
</script>

<template>
  <ScrollAreaRoot
    data-slot="scroll-area"
    v-bind="delegatedProps"
    :class="cn('relative', props.class)"
  >
    <ScrollAreaViewport
      v-bind="props.viewportProps"
      data-slot="scroll-area-viewport"
      class="focus-visible:ring-ring/50 size-full rounded-[inherit] transition-[color,box-shadow] outline-none focus-visible:ring-3 focus-visible:outline-1"
    >
      <slot />
    </ScrollAreaViewport>
    <ScrollBar v-if="props.orientation !== 'horizontal'" orientation="vertical" />
    <ScrollBar v-if="props.orientation !== 'vertical'" orientation="horizontal" />
    <ScrollAreaCorner />
  </ScrollAreaRoot>
</template>
