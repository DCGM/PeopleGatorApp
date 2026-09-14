<script setup lang="ts">
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
</script>

<template>
  <Card
    class="h-full flex-row items-center gap-6 rounded-none bg-background p-4 shadow-none outline-none transition-colors"
    role="status" aria-label="Loading person">
    <CardHeader class="size-20 shrink-0 px-0">
      <Skeleton class="size-20 rounded-full" />
    </CardHeader>
    <CardContent class="min-w-0 flex-1 space-y-2 px-0">
      <Skeleton class="h-7 w-full" />
      <Skeleton class="h-5 w-3/4" />
    </CardContent>
    <CardFooter class="shrink-0 px-0">
      <Skeleton class="size-8" />
    </CardFooter>
  </Card>
</template>
