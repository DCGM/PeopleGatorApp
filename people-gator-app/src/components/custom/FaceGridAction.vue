<script setup lang="ts">
import { LoaderCircle, Minus, Plus } from '@lucide/vue'
import { Item } from '@/components/ui/item'
defineProps<{
  label: string
  description?: string
  expanded?: boolean
  fullWidth?: boolean
  disabled?: boolean
  loading?: boolean
}>()
defineEmits<{ activate: [] }>()
</script>
<template>
  <Item
    as="button"
    type="button"
    variant="outline"
    class="min-w-0 cursor-pointer justify-center gap-2 rounded-none border-dashed border-border/40 bg-transparent p-4 text-center text-muted-foreground shadow-none transition-colors hover:border-border hover:bg-accent/30 hover:text-foreground disabled:cursor-default disabled:opacity-50"
    :class="fullWidth ? 'col-span-full flex-row' : 'h-full min-h-40 flex-col'"
    :aria-label="label"
    :aria-description="description"
    :aria-expanded="expanded"
    :aria-busy="loading || undefined"
    :disabled="disabled || loading"
    @click="$emit('activate')"
  >
    <component
      :is="loading ? LoaderCircle : expanded ? Minus : Plus"
      :class="[
        fullWidth ? 'size-4' : 'size-10 text-muted-foreground/60',
        loading && 'animate-spin',
      ]"
      :stroke-width="1.25"
      aria-hidden="true"
    />
    <span class="font-light">{{ label }}</span>
    <small v-if="description">{{ description }}</small>
  </Item>
</template>
