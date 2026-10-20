<script setup lang="ts">
import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Item } from '@/components/ui/item'
import { Skeleton } from '@/components/ui/skeleton'
</script>

<template>
  <Item
    class="min-w-0 flex-col flex-nowrap items-stretch gap-2 rounded-none border bg-card p-2"
    role="status"
    aria-label="Loading person face"
  >
    <AspectRatio :ratio="1" class="overflow-hidden bg-muted"
      ><Skeleton class="size-full rounded-none"
    /></AspectRatio>
    <div class="flex justify-between gap-2">
      <Skeleton class="h-4 w-20" /><Skeleton class="h-4 w-12" />
    </div>
    <Skeleton class="h-3 w-24" />
    <div class="space-y-1"><Skeleton class="h-3 w-24" /><Skeleton class="h-3 w-20" /></div>
  </Item>
</template>
