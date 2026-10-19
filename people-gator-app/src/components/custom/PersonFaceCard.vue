<script setup lang="ts">
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import { ChevronRight } from '@lucide/vue'

import LoadableImage from '@/components/custom/LoadableImage.vue'
import type { PersonFace } from '@/viewmodels/person-detail.types'
import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'

const props = defineProps<{
  face: PersonFace
  personName: string
}>()
</script>

<template>
  <Card
    class="gap-2 overflow-hidden rounded-none border-0 bg-transparent py-0 text-muted-foreground shadow-none transition-transform group-hover:text-primary group-focus:text-primary"
  >
    <CardHeader class="relative gap-0 px-0">
      <AspectRatio :ratio="1" class="overflow-hidden bg-muted">
        <LoadableImage
          :src="props.face.portrait"
          :loading="props.face.portraitLoading"
          :alt="`${props.personName} detection in ${props.face.documentId}`"
          class="size-full"
          image-class="object-cover grayscale duration-300 ease-out group-hover:scale-105 group-focus:scale-102"
        />
      </AspectRatio>
    </CardHeader>
    <CardContent class="min-w-0 px-0">
      <small class="block truncate">
        <span class="font-bold text-secondary">{{ props.face.library }} · </span>
        {{ props.face.pageLabel }}
      </small>
      <EntityLinkStateBadge v-bind="face" class="mt-2" />
    </CardContent>
    <CardFooter class="gap-1 px-0">
      <small class="flex-1 truncate font-heading">{{ props.face.id }}</small>
      <small
        class="whitespace-nowrap text-secondary"
        :title="`Detection confidence: ${props.face.confidence}%`"
        >Detection {{ props.face.confidence }}%</small
      >
      <ChevronRight
        class="size-4 shrink-0 transition-all duration-200 group-hover:translate-x-1 group-focus:-translate-x-1"
        aria-hidden="true"
      />
    </CardFooter>
  </Card>
</template>
