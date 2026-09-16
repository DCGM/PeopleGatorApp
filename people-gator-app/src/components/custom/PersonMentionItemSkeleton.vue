<script setup lang="ts">
import { Skeleton } from '@/components/ui/skeleton'
</script>

<template>
  <div class="grid gap-4 py-6 sm:grid-cols-[9rem_minmax(0,1fr)_auto] sm:items-center" role="status"
    aria-label="Loading person mention">
    <div class="space-y-2">
      <Skeleton class="h-3 w-24" />
      <Skeleton class="h-5 w-32" />
      <Skeleton class="h-3 w-20" />
    </div>
    <div class="space-y-2 border-l-2 pl-4">
      <Skeleton class="h-5 w-full" />
      <Skeleton class="h-5 w-4/5" />
      <Skeleton class="h-3 w-32" />
    </div>
    <div class="flex items-center gap-2">
      <Skeleton class="h-5 w-16" />
      <Skeleton class="size-4" />
    </div>
    <span class="sr-only">Loading person mention</span>
  </div>
</template>
