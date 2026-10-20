<script setup lang="ts">
import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
</script>

<template>
  <Card class="min-w-0 gap-0 overflow-hidden py-0" role="status" aria-label="Loading person face">
    <AspectRatio :ratio="1" class="overflow-hidden bg-muted">
      <Skeleton class="size-full rounded-none" />
    </AspectRatio>
    <CardContent class="px-3 pt-3">
      <div class="h-20 space-y-2">
        <Skeleton class="h-3 w-20" /><Skeleton class="h-3 w-full" /><Skeleton class="h-3 w-full" />
      </div>
      <Skeleton class="mt-2 h-4 w-full" />
    </CardContent>
    <CardFooter class="block px-3 pb-3 pt-2">
      <div class="h-10 space-y-2"><Skeleton class="h-3 w-24" /><Skeleton class="h-3 w-20" /></div>
      <div class="mt-2 h-16"><Skeleton class="h-6 w-20" /></div>
    </CardFooter>
  </Card>
</template>
