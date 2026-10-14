<script setup lang="ts">
import { X } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
export type ActiveFilter = { key: string; value: string; label: string }
defineProps<{ filters: ActiveFilter[] }>()
const emit = defineEmits<{ remove: [filter: ActiveFilter]; clear: [] }>()
</script>
<template>
  <div
    v-if="filters.length"
    class="active-filters mt-3 flex w-full min-w-0 flex-row flex-wrap items-center gap-2"
    aria-label="Active filters"
  >
    <Badge
      v-for="filter in filters"
      :key="`${filter.key}:${filter.value}`"
      variant="secondary"
      class="max-w-full gap-2"
    >
      <span class="min-w-0 truncate">{{ filter.label }}</span>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        :aria-label="`Remove ${filter.label}`"
        @click="emit('remove', filter)"
        ><X aria-hidden="true"
      /></Button>
    </Badge>
    <Button type="button" variant="ghost" size="sm" @click="emit('clear')"
      >Clear all filters</Button
    >
  </div>
</template>
