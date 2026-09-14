<script setup lang="ts">
import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
</script>

<template>
  <Card class="h-full gap-2 overflow-hidden rounded-none border-0 bg-transparent py-0 shadow-none" role="status"
    aria-label="Loading scan result">
    <CardHeader class="gap-0 px-0">
      <AspectRatio :ratio="210 / 297" class="overflow-hidden bg-muted">
        <Skeleton class="h-full w-full rounded-none" />
      </AspectRatio>
    </CardHeader>
    <CardContent class="flex items-center gap-2 px-0">
      <Skeleton class="h-6 w-10 max-w-[20%] text-xs" />
      <span class="text-sm text-primary/10"> · </span>
      <Skeleton class="h-5 w-32 max-w-[65%]" />
    </CardContent>
    <CardFooter class="gap-2 px-0">
      <Skeleton class="h-4 flex-1" />
      <Skeleton class="h-4 max-w-10 flex-1" />
      <Skeleton class="h-4 max-w-4 flex-1" />
    </CardFooter>
    <span class="sr-only">Loading scan result</span>
  </Card>
</template>
