<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
// Attributes such as aria-describedby describe the table, not its scroll region.
defineOptions({ inheritAttrs: false })
</script>

<template>
  <div
    data-slot="table-container"
    class="relative w-full min-w-0 max-w-full overflow-auto"
    tabindex="0"
    role="region"
    aria-label="Table, scroll for more columns"
  >
    <table
      v-bind="$attrs"
      data-slot="table"
      :class="cn('w-full caption-bottom text-sm', props.class)"
    >
      <slot />
    </table>
  </div>
</template>
