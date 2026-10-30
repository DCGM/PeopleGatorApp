<script setup lang="ts">
import { Skeleton } from '@/components/ui/skeleton'
import PersonMentionItemSkeleton from './PersonMentionItemSkeleton.vue'
withDefaults(
  defineProps<{
    mode?: 'flat' | 'mention' | 'document' | 'page'
    compact?: boolean
    count?: number
  }>(),
  { mode: 'flat', count: 3 },
)
</script>

<template>
  <div
    role="status"
    :aria-label="mode === 'flat' ? 'Loading mentions' : 'Loading mention groups'"
    aria-busy="true"
  >
    <template v-if="mode === 'flat'">
      <PersonMentionItemSkeleton v-for="item in count" :key="item" :compact="compact" />
    </template>
    <div v-else class="divide-y" aria-hidden="true">
      <div v-for="group in count" :key="group" data-mention-group-skeleton>
        <div class="flex min-w-0 items-center gap-2 py-3">
          <Skeleton class="size-4 shrink-0" />
          <div class="min-w-0 flex-1 space-y-1">
            <Skeleton class="h-4 w-40 max-w-full" />
            <Skeleton v-if="mode !== 'mention'" class="h-3 w-48 max-w-full" />
          </div>
          <Skeleton class="h-5 w-24 shrink-0 rounded-full" />
        </div>
        <div v-if="!compact" class="pl-7">
          <PersonMentionItemSkeleton v-for="item in 2" :key="item" />
        </div>
      </div>
    </div>
    <span class="sr-only">{{
      mode === 'flat' ? 'Loading mentions' : 'Loading mention groups'
    }}</span>
  </div>
</template>
