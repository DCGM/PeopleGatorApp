<script setup lang="ts">
import { Skeleton } from '@/components/ui/skeleton'
defineProps<{ compact?: boolean }>()
</script>

<template>
  <div
    class="flex min-w-0 items-start gap-3 border-b py-2 last:border-b-0"
    aria-hidden="true"
    data-mention-skeleton
  >
    <Skeleton class="mt-1 size-4 shrink-0" />
    <div class="flex min-w-0 flex-1 items-start gap-2">
      <div
        class="min-w-0 flex-1 space-y-1"
        :class="compact && 'flex flex-wrap items-center gap-x-2 gap-y-1 space-y-0'"
      >
        <div class="flex min-w-0 items-center gap-2" :class="compact && 'max-w-full shrink-0'">
          <Skeleton class="h-4 max-w-full" :class="compact ? 'w-16' : 'w-48'" />
          <Skeleton class="h-4 w-16 shrink-0 rounded-full" />
        </div>
        <Skeleton
          class="h-5 w-4/5 max-w-full"
          :class="compact && 'basis-full sm:basis-0 sm:flex-1'"
        />
      </div>
      <div class="flex size-7 shrink-0 items-center justify-center">
        <Skeleton class="size-4 rounded-full" />
      </div>
    </div>
  </div>
</template>
