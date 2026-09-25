<script setup lang="ts">
import { ScanFace } from '@lucide/vue'
import {
  Item,
  ItemContent,
  ItemFooter,
  ItemMedia,
  ItemTitle,
} from '@/components/ui/item'
import SelectedFaceItem from '@/components/custom/SelectedFaceItem.vue'
import type { Face } from '@/viewmodels/document-workspace.types'

const props = defineProps<{
  face: Face | null
  assignmentPending?: boolean
}>()

const emit = defineEmits<{
  findProfile: []
  create: [profile: { name: string; shortDescription?: string }]
  unassign: []
}>()

function createPerson(profile: { name: string; shortDescription?: string }) {
  const name = profile.name.trim()
  emit('create', {
    name,
    shortDescription: profile.shortDescription,
  })
}
</script>

<template>
  <section aria-labelledby="current-face-title">
    <p id="current-face-title" class="font-mono text-xs font-semibold uppercase text-secondary mb-2">
      {{ props.face ? "Current face" : "Select someone first" }}
    </p>
    <SelectedFaceItem v-if="props.face" :face="props.face" :assignment-pending="props.assignmentPending"
      @find-profile="emit('findProfile')" @create-profile="createPerson" @unassign="emit('unassign')" />
    <Item v-else variant="outline" class="w-full items-start gap-x-4 gap-y-2 bg-none px-3 py-3">
      <ItemMedia class="self-start">
        <div class="relative size-15 overflow-hidden bg-none">
          <ScanFace class="size-full text-muted-foreground" aria-hidden="true" />
        </div>
      </ItemMedia>
      <ItemContent class="min-w-0 gap-1 overflow-hidden">
        <ItemTitle class="min-w-0 w-full max-w-full">
          <h4 class="min-h-8 w-full truncate rounded-sm border border-transparent px-1 py-0.5 text-muted-foreground">
            No face selected
          </h4>
        </ItemTitle>
        <p class="min-h-[calc(2lh+0.25rem)] min-w-0 truncate text-wrap rounded-sm border border-transparent px-1 py-0.5 text-xs leading-snug text-muted-foreground"
          title="Select a face to view details">
          Select a face to view details
        </p>
      </ItemContent>
      <ItemFooter class="w-full shrink-0 items-center border-t pt-2 text-muted-foreground">
        <span class="min-w-0 flex-1" aria-hidden="true">... or search for someone below</span>
      </ItemFooter>
    </Item>
  </section>
</template>
