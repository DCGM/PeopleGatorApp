<script setup lang="ts">
import {
  Item,
  ItemActions,
  ItemContent,
  ItemFooter,
  ItemMedia,
} from '@/components/ui/item'
import { Skeleton } from '@/components/ui/skeleton'
</script>

<template>
  <Item variant="outline" class="w-full gap-x-4 gap-y-2 bg-card px-3 py-3" role="status"
    aria-label="Loading similar person">
    <ItemMedia>
      <Skeleton class="size-15 rounded-full" />
    </ItemMedia>
    <ItemContent class="min-w-0 gap-2">
      <Skeleton class="h-5 w-32 max-w-full" />
      <Skeleton class="h-3 w-44 max-w-full" />
    </ItemContent>
    <ItemActions>
      <Skeleton class="h-7 w-16" />
    </ItemActions>
    <ItemFooter class="w-full shrink-0 items-center border-t pt-2">
      <Skeleton class="h-3 w-32" />
      <Skeleton class="ml-auto h-5 w-12" />
    </ItemFooter>
    <span class="sr-only">Loading similar person</span>
  </Item>
</template>
