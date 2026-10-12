<script setup lang="ts">
import { ref } from 'vue'
import type { FilterOption } from '@/query/people-filter-options'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

defineProps<{
  label: string
  options: FilterOption[]
  isLoading?: boolean
  error?: unknown
  hasMore?: boolean
  isLoadingMore?: boolean
}>()
const selected = defineModel<string[]>({ required: true })
const search = defineModel<string>('search', { default: '' })
const emit = defineEmits<{ loadMore: []; retry: [] }>()
const open = ref(false)
function toggle(id: string) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((value) => value !== id)
    : [...selected.value, id]
}
</script>

<template>
  <div class="relative min-w-0" @keydown.esc="open = false">
    <Button
      type="button"
      variant="outline"
      class="w-full justify-between rounded-none"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ label }} <span v-if="selected.length">({{ selected.length }})</span>
    </Button>
    <div
      v-if="open"
      class="absolute top-full z-30 mt-1 w-full min-w-0 border bg-popover p-3 text-popover-foreground shadow-md"
    >
      <Input
        v-model="search"
        :aria-label="`Search ${label.toLowerCase()}`"
        :placeholder="`Search ${label.toLowerCase()}…`"
        class="mb-2 rounded-none"
      />
      <p v-if="isLoading" class="py-2 text-sm text-muted-foreground">Loading…</p>
      <div v-else-if="error" class="text-sm text-destructive" role="alert">
        Could not load {{ label.toLowerCase() }}.
        <Button type="button" variant="ghost" size="sm" @click="emit('retry')">Retry</Button>
      </div>
      <div v-else class="max-h-56 overflow-y-auto" :aria-label="label">
        <label
          v-for="option in options"
          :key="option.id"
          class="flex cursor-pointer items-start gap-2 py-2 text-sm"
        >
          <input
            type="checkbox"
            class="mt-1"
            :checked="selected.includes(option.id)"
            @change="toggle(option.id)"
          />
          <span class="break-all">{{ option.label }}</span>
        </label>
        <p v-if="!options.length" class="py-2 text-sm text-muted-foreground">
          No matching {{ label.toLowerCase() }}.
        </p>
      </div>
      <Button
        v-if="hasMore"
        type="button"
        variant="ghost"
        size="sm"
        :disabled="isLoadingMore"
        @click="emit('loadMore')"
      >
        {{ isLoadingMore ? 'Loading…' : 'Load more options' }}
      </Button>
      <Button type="button" variant="ghost" size="sm" @click="open = false">Done</Button>
    </div>
  </div>
</template>
