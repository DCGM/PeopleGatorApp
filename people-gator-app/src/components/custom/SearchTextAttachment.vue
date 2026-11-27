<script setup lang="ts">
import { TextQuote, X } from '@lucide/vue'
import { InputGroupButton } from '@/components/ui/input-group'

defineProps<{ text: string }>()
defineEmits<{ remove: [] }>()
</script>

<template>
  <span
    class="flex shrink-0 items-center gap-1.5 rounded-full border py-0.5 pl-2 text-xs text-foreground"
    data-search-text
    :title="text"
  >
    <TextQuote class="size-3.5 shrink-0" aria-hidden="true" />
    <span class="max-w-40 truncate">{{ text }}</span>
    <InputGroupButton
      type="button"
      size="icon-xs"
      class="rounded-full"
      :aria-label="`Remove mention text ${text}`"
      @click="$emit('remove')"
      ><X aria-hidden="true"
    /></InputGroupButton>
  </span>
</template>
