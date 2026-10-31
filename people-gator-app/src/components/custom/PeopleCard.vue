<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'

import PersonPortrait from './PersonPortrait.vue'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'

const props = defineProps<{
  thumbnailFaceId?: string | null
  name: string
  faces: number | null
  names: number | null
}>()
</script>

<template>
  <Card
    class="h-full w-full min-w-0 flex-row items-center gap-4 overflow-hidden rounded-none bg-transparent p-4 text-muted-foreground shadow-none outline-none transition-colors group-hover:bg-card group-hover:text-primary group-focus-visible:bg-card group-focus:text-primary sm:gap-6"
  >
    <CardHeader class="size-20 shrink-0 px-0">
      <PersonPortrait
        :name="props.name"
        :face-id="props.thumbnailFaceId"
        large-initials
        class="size-20"
      />
    </CardHeader>
    <CardContent class="min-w-0 flex-1 px-0">
      <h3 class="block max-w-full truncate" :title="props.name">
        {{ props.name }}
      </h3>
      <p class="flex flex-wrap gap-x-2">
        <small
          ><b>{{ props.faces ?? '—' }}</b> faces
        </small>
        <small
          ><b>{{ props.names ?? '—' }}</b> text mentions</small
        >
        <small
          ><b>{{
            props.faces !== null && props.names !== null ? props.faces + props.names : '—'
          }}</b>
          all annotations</small
        >
      </p>
    </CardContent>
    <CardFooter class="shrink-0 px-0">
      <ChevronRight
        class="size-8 transition-transform group-hover:translate-x-1 group-focus:translate-x-1"
        aria-hidden="true"
      />
    </CardFooter>
  </Card>
</template>
