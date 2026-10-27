<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
  containerClass?: HTMLAttributes['class']
}>()
</script>

<template>
  <div
    data-slot="table-container"
    :class="cn('relative w-full min-w-0 max-w-full overflow-auto', props.containerClass)"
    tabindex="0"
    role="region"
    aria-label="Table, scroll for more rows and columns"
  >
    <table data-slot="table" :class="cn('w-full caption-bottom text-sm', props.class)">
      <slot />
    </table>
    <slot name="after" />
  </div>
</template>
