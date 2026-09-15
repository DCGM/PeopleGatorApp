<script setup lang="ts">
import {
  BadgeCheck,
  CircleAlert,
  RefreshCcw,
  UserRoundX,
  WandSparkles,
} from '@lucide/vue'
import type { Component } from 'vue'

import type { Face, FaceStatus } from '@/components/custom/document-page.types'
import { Item, ItemContent, ItemMedia, ItemTitle } from '@/components/ui/item'

defineProps<{
  face: Face
  selected?: boolean
}>()

const emit = defineEmits<{
  select: [faceId: string]
}>()

const faceStatusLabels = {
  auto: 'Auto',
  valid: 'Valid',
  change: 'Changed',
  empty: 'Empty',
  fail: 'Fail',
} satisfies Record<FaceStatus, string>

const faceStatusClasses = {
  auto: 'text-accent',
  valid: 'text-emerald-700',
  change: 'text-secondary',
  empty: 'text-muted-foreground',
  fail: 'text-destructive',
} satisfies Record<FaceStatus, string>

const faceStatusIcons = {
  auto: WandSparkles,
  valid: BadgeCheck,
  change: RefreshCcw,
  empty: UserRoundX,
  fail: CircleAlert,
} satisfies Record<FaceStatus, Component>
</script>

<template>
  <Item as="button" type="button" variant="outline" size="default" :data-face-id="face.id" :aria-pressed="selected"
    class="bg-card p-2 text-left hover:border-accent"
    :class="selected && 'border-secondary bg-secondary/20 hover:bg-secondary/20'" @click="emit('select', face.id)">
    <ItemMedia variant="image" class="size-14 rounded-none">
      <img :src="face.portrait" :alt="face.name" class="grayscale" />
    </ItemMedia>
    <ItemContent class="min-w-0 gap-0.5">
      <ItemTitle class="block w-full font-serif text-base">{{ face.name }}</ItemTitle>
      <span class="flex items-center gap-1" :class="faceStatusClasses[face.status]">
        <component :is="faceStatusIcons[face.status]" class="size-4" aria-hidden="true" />
        <b>{{ faceStatusLabels[face.status] }}</b>
        <code class="ml-auto text-sm text-muted-foreground">c={{ face.confidence }}%</code>
      </span>
    </ItemContent>
  </Item>
</template>
