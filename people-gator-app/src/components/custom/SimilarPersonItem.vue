<script setup lang="ts">
import { Check, ChevronRight, Database, FileText } from '@lucide/vue'

import type { SimilarPersonCandidate } from '@/components/custom/similar-people.types'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Item, ItemContent, ItemMedia, ItemTitle, ItemActions } from '@/components/ui/item'

defineProps<{
  person: SimilarPersonCandidate
  assigned?: boolean
  viewed?: boolean
}>()

const emit = defineEmits<{
  preview: [person: SimilarPersonCandidate]
  assign: [person: SimilarPersonCandidate]
}>()

function initials(name: string) {
  return name.split(/\s+/).map((part) => part.charAt(0)).join('').slice(0, 2)
}
</script>

<template>
  <Item variant="outline" class="relative w-full flex-nowrap gap-4 bg-card px-3 py-3 hover:border-accent"
    :class="viewed && 'border-accent bg-accent/15 ring-1 ring-accent hover:bg-accent/15'">
    <button type="button"
      class="absolute inset-0 z-10 rounded-[inherit] outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      :aria-label="`Preview ${person.name} on this page`" :aria-pressed="viewed" @click="emit('preview', person)">
    </button>
    <ItemMedia>
      <Avatar class="size-15">
        <AvatarImage v-if="person.portrait" :src="person.portrait" :alt="person.name" class="object-cover grayscale" />
        <AvatarFallback class="font-serif">{{ initials(person.name) }}</AvatarFallback>
      </Avatar>
    </ItemMedia>
    <ItemContent class="min-w-0 gap-1">
      <ItemTitle>
        <RouterLink :to="{ name: 'person-detail', params: { personId: person.id } }"
          class="group z-20 flex min-w-0 items-center gap-1 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          :aria-label="`Open ${person.name}`">
          <h4 class="flex min-w-0 items-center gap-1.5 truncate">
            {{ person.name }}
            <ChevronRight
              class="size-[1em] shrink-0 transition-transform group-hover:translate-x-1 group-focus-visible:translate-x-1"
              aria-hidden="true" />
          </h4>
        </RouterLink>
      </ItemTitle>
      <span class="text-xs text-muted-foreground">
        <b class="text-foreground">{{ person.nerMentions }}</b> mentions
        <b class="text-foreground">{{ person.detections }}</b> detections
      </span>
      <div class="flex items-center gap-2">
        <code class="text-xs text-accent">{{ person.score }} sim.</code>
        <Badge v-if="person.source === 'database'" variant="outline"
          class="font-mono text-xs py-0 uppercase text-muted-foreground">
          <Database />DB
        </Badge>
        <Badge v-if="person.source === 'page'" variant="outline"
          class="font-mono text-xs py-0 uppercase text-muted-foreground">
          <FileText />scan
        </Badge>
      </div>
    </ItemContent>
    <ItemActions class="z-20">
      <Button type="button" size="xs" :variant="assigned ? 'secondary' : 'outline'" :aria-pressed="assigned"
        @click="emit('assign', person)">
        <Check v-if="assigned" aria-hidden="true" />
        {{ assigned ? 'Linked' : 'Assign' }}
      </Button>
    </ItemActions>
  </Item>
</template>
