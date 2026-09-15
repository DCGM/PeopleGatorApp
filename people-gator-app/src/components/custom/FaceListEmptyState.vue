<script setup lang="ts">
import { UserRoundX } from '@lucide/vue'

import { Item, ItemContent, ItemDescription, ItemMedia, ItemTitle } from '@/components/ui/item'
</script>

<template>
  <Item variant="muted" role="status" aria-label="No faces found"
    class="w-64 flex-nowrap bg-card p-2 2xl:@md:w-44 2xl:@md:flex-col 2xl:@md:items-stretch">
    <ItemMedia variant="icon" class="size-14 2xl:@md:aspect-square 2xl:@md:size-auto 2xl:@md:w-full">
      <UserRoundX class="size-5 text-muted-foreground @md:size-8" aria-hidden="true" />
    </ItemMedia>
    <ItemContent class="min-w-0 gap-2 2xl:@md:w-full 2xl:@md:flex-none">
      <ItemTitle class="font-serif text-base">No faces found</ItemTitle>
      <ItemDescription class="text-sm">Try another status filter.</ItemDescription>
    </ItemContent>
  </Item>
</template>
