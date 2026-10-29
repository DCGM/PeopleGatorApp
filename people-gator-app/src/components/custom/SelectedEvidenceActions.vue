<script setup lang="ts">
import { Button } from '@/components/ui/button'
defineProps<{ count: number; busy?: boolean; singular: string; plural: string; label: string }>()
defineEmits<{ clear: [] }>()
</script>
<template>
  <div
    class="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-4xl flex-col gap-3 border border-accent bg-card p-3 shadow-lg sm:flex-row sm:items-center sm:justify-between"
    role="toolbar"
    :aria-label="label"
  >
    <div class="min-w-0">
      <p class="font-semibold">{{ count }} {{ count === 1 ? singular : plural }} selected</p>
      <div class="text-xs text-muted-foreground"><slot name="description" /></div>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <Button type="button" size="sm" variant="outline" :disabled="busy" @click="$emit('clear')"
        >Clear</Button
      >
      <slot />
    </div>
  </div>
</template>
