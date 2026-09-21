<script setup lang="ts">
import { Link, UserRoundX } from '@lucide/vue'
import type { Component } from 'vue'

import type { Face, FaceStatus } from '@/viewmodels/document-workspace.types'
import LoadableImage from '@/components/custom/LoadableImage.vue'
import { Item, ItemContent, ItemMedia } from '@/components/ui/item'

defineProps<{
  face: Face
  selected?: boolean
}>()

const emit = defineEmits<{
  select: [faceId: string]
}>()

const faceStatusClasses = {
  assigned: 'text-emerald-700',
  unassigned: 'text-muted-foreground',
} satisfies Record<FaceStatus, string>

const faceStatusIcons = {
  assigned: Link,
  unassigned: UserRoundX,
} satisfies Record<FaceStatus, Component>
</script>

<template>
  <Item as="button" type="button" variant="outline" size="default" :data-face-id="face.id" :aria-pressed="selected"
    class="bg-card p-2 text-left flex-col hover:border-accent"
    :class="selected && 'border-secondary bg-secondary/20 hover:bg-secondary/20'" @click="emit('select', face.id)">
    <ItemMedia variant="image" class="rounded-none size-26">
      <LoadableImage :src="face.portrait" :loading="face.portraitLoading" :alt="face.name" class="size-full"
        image-class="object-cover grayscale" />
    </ItemMedia>
    <ItemContent class="min-w-0 flex-row items-center gap-1 text-sm" :class="faceStatusClasses[face.status]">
      <component :is="faceStatusIcons[face.status]" aria-hidden="true" class="size-[1.15em]" />
      <span class="truncate max-w-full">{{ face.status == 'assigned' ? face.name : 'Unassigned' }}</span>
    </ItemContent>
  </Item>
</template>
