<script setup lang="ts">
import { watch } from 'vue'
import { Check, ChevronsUpDown } from '@lucide/vue'
import type { FilterOption } from '@/query/people-filter-options'
import { Button } from '@/components/ui/button'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxEmpty,
  ComboboxGroup,
  ComboboxInput,
  ComboboxItem,
  ComboboxItemIndicator,
  ComboboxList,
  ComboboxTrigger,
  ComboboxViewport,
} from '@/components/ui/combobox'

defineProps<{
  label: string
  placeholder?: string
  showDone?: boolean
  options: FilterOption[]
  isLoading?: boolean
  error?: unknown
  hasMore?: boolean
  isLoadingMore?: boolean
}>()
const selected = defineModel<string[]>({ required: true })
const search = defineModel<string>('search', { default: '' })
const emit = defineEmits<{
  loadMore: []
  retry: []
  openChange: [value: boolean]
  interactOutside: [event: Event]
  escape: []
}>()
const open = defineModel<boolean>('open', { default: false })
watch(open, (value) => emit('openChange', value), { flush: 'sync' })

function updateSelection(value: unknown) {
  if (Array.isArray(value))
    selected.value = value.filter((id): id is string => typeof id === 'string')
}
</script>

<template>
  <Combobox
    v-model:open="open"
    :model-value="selected"
    multiple
    ignore-filter
    :reset-search-term-on-select="false"
    :reset-search-term-on-blur="false"
    class="min-w-0"
    @update:model-value="updateSelection"
  >
    <ComboboxAnchor class="w-full" as-child>
      <ComboboxTrigger as-child :aria-label="label">
        <Button type="button" variant="outline" class="w-full justify-between">
          <span class="min-w-0 truncate"
            >{{ placeholder ?? label
            }}<template v-if="selected.length"> ({{ selected.length }})</template></span
          >
          <ChevronsUpDown class="size-4 shrink-0" aria-hidden="true" />
        </Button>
      </ComboboxTrigger>
    </ComboboxAnchor>
    <ComboboxList
      @interact-outside="emit('interactOutside', $event)"
      @escape-key-down="emit('escape')"
      align="start"
      :collision-padding="12"
      class="w-(--reka-combobox-trigger-width) min-w-64 max-w-(--reka-combobox-content-available-width)"
      :aria-label="label"
    >
      <ComboboxInput
        v-model="search"
        :aria-label="`Search ${label.toLowerCase()}`"
        :placeholder="`Search ${label.toLowerCase()}…`"
      />
      <ComboboxViewport>
        <p v-if="isLoading" class="px-3 py-2 text-sm text-muted-foreground" role="status">
          Loading…
        </p>
        <div v-else-if="error" class="px-3 py-2 text-sm text-destructive" role="alert">
          Could not load {{ label.toLowerCase() }}.
          <Button type="button" variant="ghost" size="sm" @click="emit('retry')">Retry</Button>
        </div>
        <template v-else>
          <ComboboxEmpty>No matching {{ label.toLowerCase() }}.</ComboboxEmpty>
          <ComboboxGroup class="p-1">
            <ComboboxItem
              v-for="option in options"
              :key="option.id"
              :value="option.id"
              :text-value="option.label"
            >
              <span class="min-w-0 break-all">{{ option.label }}</span>
              <ComboboxItemIndicator
                ><Check class="size-4" aria-hidden="true"
              /></ComboboxItemIndicator>
            </ComboboxItem>
          </ComboboxGroup>
        </template>
      </ComboboxViewport>
      <div v-if="hasMore || showDone !== false" class="flex justify-between p-1">
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
        <Button
          v-if="showDone !== false"
          type="button"
          variant="ghost"
          size="sm"
          class="ml-auto"
          @click="open = false"
          >Done</Button
        >
      </div>
    </ComboboxList>
  </Combobox>
</template>
