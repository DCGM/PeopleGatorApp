<script setup lang="ts">
import { Check } from '@lucide/vue'
defineProps<{ faceId: string; selected: boolean; disabled?: boolean; purpose?: string }>()
defineEmits<{ toggle: [event: MouseEvent] }>()
</script>
<template>
  <button
    type="button"
    data-face-selection-target="control"
    class="absolute right-3 top-3 z-20 flex size-7 items-center justify-center rounded-sm border-2 shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
    :class="
      selected
        ? 'border-accent bg-accent text-accent-foreground'
        : 'border-border bg-card text-muted-foreground hover:border-accent hover:text-primary'
    "
    :aria-label="`${selected ? 'Remove' : 'Select'} face ${faceId} ${selected ? 'from' : 'for'} ${purpose ?? 'review'}`"
    :aria-pressed="selected"
    :disabled="disabled"
    @click="$emit('toggle', $event)"
  >
    <Check v-if="selected" class="size-4" aria-hidden="true" />
    <span v-else class="size-2 rounded-full border border-current" aria-hidden="true"></span>
  </button>
</template>
