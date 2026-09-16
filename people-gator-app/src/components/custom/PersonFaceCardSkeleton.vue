<script setup lang="ts">
import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
</script>

<template>
  <Card class="h-full gap-2 overflow-hidden rounded-none border-0 bg-transparent py-0 shadow-none" role="status"
    aria-label="Loading person face">
    <CardHeader class="relative gap-0 px-0">
      <AspectRatio :ratio="210 / 297" class="overflow-hidden bg-muted">
        <Skeleton class="h-full w-full rounded-none" />
      </AspectRatio>
      <Skeleton class="absolute left-3 top-3 h-6 w-16 rounded-sm" />
    </CardHeader>
    <CardContent class="flex items-center gap-2 px-0">
      <Skeleton class="h-4 w-10" />
      <span class="text-xs text-primary/10">·</span>
      <Skeleton class="h-4 w-20" />
    </CardContent>
    <CardFooter class="gap-2 px-0">
      <Skeleton class="h-4 flex-1" />
      <Skeleton class="h-4 w-10" />
      <Skeleton class="size-4" />
    </CardFooter>
    <span class="sr-only">Loading person face</span>
  </Card>
</template>
