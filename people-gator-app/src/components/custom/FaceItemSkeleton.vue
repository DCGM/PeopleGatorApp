<script setup lang="ts">
import { Item, ItemContent, ItemMedia } from '@/components/ui/item'
import { Skeleton } from '@/components/ui/skeleton'
</script>

<template>
  <Item variant="outline" size="default" class="min-w-52 flex-nowrap bg-card p-2" role="status"
    aria-label="Loading face">
    <ItemMedia class="size-14">
      <Skeleton class="size-14 rounded-none" />
    </ItemMedia>
    <ItemContent class="min-w-0 gap-2">
      <Skeleton class="h-5 w-32" />
      <div class="flex items-center gap-2">
        <Skeleton class="size-4" />
        <Skeleton class="h-4 w-14" />
        <Skeleton class="ml-auto h-4 w-12" />
      </div>
    </ItemContent>
    <span class="sr-only">Loading face</span>
  </Item>
</template>
