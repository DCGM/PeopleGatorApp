<script setup lang="ts">
import { Check } from '@lucide/vue'

defineProps<{ name: string; selected: boolean; disabled?: boolean }>()
defineEmits<{ toggle: [event: MouseEvent] }>()
</script>

<template>
  <button
    type="button"
    :disabled="disabled"
    class="absolute right-2 top-2 z-20 flex size-7 items-center justify-center rounded-sm border-2 shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
    :class="
      selected
        ? 'border-accent bg-accent text-accent-foreground'
        : 'border-border bg-card text-muted-foreground hover:border-accent hover:text-primary'
    "
    :aria-label="`${selected ? 'Remove' : 'Select'} ${name} ${selected ? 'from merge' : 'for merge'}`"
    :aria-pressed="selected"
    @click="$emit('toggle', $event)"
  >
    <Check v-if="selected" class="size-4" aria-hidden="true" />
    <span v-else class="size-2 rounded-full border border-current" aria-hidden="true"></span>
  </button>
</template>
