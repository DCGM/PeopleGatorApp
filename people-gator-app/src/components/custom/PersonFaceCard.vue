<script setup lang="ts">
import { BadgeCheck, ChevronRight, RefreshCcw, Sparkles } from '@lucide/vue'
import type { Component } from 'vue'

import type { PersonFace } from '@/components/custom/person-detail.types'
import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'

const props = defineProps<{
  face: PersonFace
  personName: string
}>()

const faceStatusMeta = {
  auto: { label: 'Auto', icon: Sparkles, class: 'border-accent bg-accent text-accent-foreground' },
  valid: {
    label: 'Valid',
    icon: BadgeCheck,
    class: 'border-emerald-700 bg-emerald-700 text-white',
  },
  change: {
    label: 'Changed',
    icon: RefreshCcw,
    class: 'border-secondary bg-secondary text-secondary-foreground',
  },
} satisfies Record<PersonFace['status'], { label: string; icon: Component; class: string }>
</script>

<template>
  <Card
    class="h-full gap-2 overflow-hidden rounded-none border-0 bg-transparent py-0 text-muted-foreground shadow-none transition-transform group-hover:text-primary group-focus:text-primary">
    <CardHeader class="relative gap-0 px-0">
      <AspectRatio :ratio="210 / 297" class="overflow-hidden bg-muted">
        <img :src="props.face.portrait" :alt="`${props.personName} detection in ${props.face.documentId}`"
          class="h-full w-full object-cover grayscale duration-300 ease-out group-hover:scale-105 group-focus:scale-102" />
      </AspectRatio>
      <Badge variant="outline" class="absolute left-3 top-3 gap-1 rounded-sm border shadow-sm"
        :class="faceStatusMeta[props.face.status].class">
        <component :is="faceStatusMeta[props.face.status].icon" class="size-3.5" aria-hidden="true" />
        {{ faceStatusMeta[props.face.status].label }}
      </Badge>
    </CardHeader>
    <CardContent class="min-w-0 px-0">
      <small class="block truncate">
        <span class="font-bold text-secondary">{{ props.face.library }} · </span>
        {{ props.face.pageLabel }}
      </small>
    </CardContent>
    <CardFooter class="gap-1 px-0">
      <small class="flex-1 truncate font-heading">{{ props.face.id }}</small>
      <small class="whitespace-nowrap text-secondary">{{ props.face.confidence }}%</small>
      <ChevronRight
        class="size-4 shrink-0 transition-all duration-200 group-hover:translate-x-1 group-focus:-translate-x-1"
        aria-hidden="true" />
    </CardFooter>
  </Card>
</template>
