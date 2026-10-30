<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ChevronRight } from '@lucide/vue'
import { linkStateVisuals, linkTooltip } from '@/lib/entity-links'
import AnnotationLastChange from './AnnotationLastChange.vue'
import FaceSelectionControl from './FaceSelectionControl.vue'
import LoadableImage from './LoadableImage.vue'
import type { PersonFace } from '@/viewmodels/person-detail.types'
import { relatedQuery } from '@/viewmodels/shared-filters'
import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Item } from '@/components/ui/item'
import ArchiveLink from './ArchiveLink.vue'

const props = defineProps<{
  face: PersonFace
  personName: string
  selectable?: boolean
  selected?: boolean
  selectionEnabled?: boolean
  busy?: boolean
  portrait?: boolean
}>()
defineEmits<{ toggle: [event: MouseEvent]; add: [event: MouseEvent] }>()
const route = useRoute()
const assignment = computed(() => linkStateVisuals[props.face.linkState ?? 'unassigned'])
const assignmentTextClasses = computed(() =>
  assignment.value.classes.split(' ').filter((name) => name.split(':').pop()?.startsWith('text-')),
)
const sourceTarget = computed(() =>
  props.face.pageId
    ? {
        name: 'document-page',
        params: {
          libraryId: props.face.library,
          documentId: props.face.documentId,
          pageId: props.face.pageId,
        },
        query: relatedQuery(route, { person: props.face.id }),
      }
    : undefined,
)
</script>

<template>
  <Item
    class="group/face relative h-full min-h-[var(--face-card-height)] min-w-0 flex-col flex-nowrap items-stretch gap-2 overflow-hidden rounded-none border bg-card p-2 text-muted-foreground shadow-none transition-colors hover:border-accent hover:text-primary"
    :class="selected && 'border-secondary bg-secondary/20 text-primary hover:bg-secondary/20'"
    data-person-face-card
  >
    <button
      v-if="selectionEnabled"
      type="button"
      class="absolute inset-0 z-10 rounded-[inherit] outline-none focus-visible:ring-2 focus-visible:ring-ring"
      :disabled="busy"
      :aria-label="selected ? `Face ${face.id} is selected` : `Add face ${face.id} to selection`"
      @click="$emit('add', $event)"
    ></button>
    <FaceSelectionControl
      v-if="selectable"
      :face-id="face.id"
      :selected="Boolean(selected)"
      :disabled="busy"
      @toggle="$emit('toggle', $event)"
    />
    <component
      :is="sourceTarget && !selectionEnabled ? 'RouterLink' : 'div'"
      :to="!selectionEnabled ? sourceTarget : undefined"
      class="group block min-w-0 space-y-2 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      :aria-label="
        sourceTarget && !selectionEnabled
          ? `Open ${personName} face on its source document`
          : undefined
      "
    >
      <AspectRatio :ratio="1" class="overflow-hidden bg-muted">
        <LoadableImage
          :src="face.portrait"
          :loading="face.portraitLoading"
          :alt="`${personName} face`"
          class="size-full"
          image-class="object-cover grayscale duration-300 ease-out group-hover/face:scale-105 group-focus-within/face:scale-102"
        />
      </AspectRatio>
      <p
        class="flex min-w-0 items-center gap-1 text-sm"
        :class="assignmentTextClasses"
        :title="linkTooltip(face)"
        :aria-label="linkTooltip(face)"
        data-face-assignment
      >
        <component :is="assignment.icon" class="size-4 shrink-0" aria-hidden="true" />
        <b class="min-w-0 flex-1 truncate">{{ assignment.label }}</b>
        <code
          class="ml-auto shrink-0 text-sm text-muted-foreground"
          :title="`Detection confidence: ${face.confidence}%`"
          >conf {{ face.confidence }}%</code
        >
      </p>
      <div class="flex min-w-0 items-center gap-1 text-xs text-muted-foreground" data-face-source>
        <span class="min-w-0 flex-1 truncate" :title="`${face.library} · ${face.documentId}`">
          <b class="text-secondary">{{ face.library }}</b> · {{ face.documentId }}
        </span>
        <ChevronRight
          v-if="sourceTarget"
          class="size-4 shrink-0 transition-transform group-hover/face:translate-x-1"
          aria-hidden="true"
        />
      </div>
    </component>
    <p v-if="portrait || face.matched" class="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
      <span v-if="portrait" data-person-portrait>Profile photo</span>
      <span v-if="face.matched" data-person-match>Search hit</span>
    </p>
    <ArchiveLink :url="face.pageUrl" class="absolute left-3 top-3" />
    <AnnotationLastChange
      :touched-at="face.metadata?.last_touched_at"
      :user-id="face.metadata?.last_touched_by_user_id"
    />
    <p v-if="!face.pageId" class="text-xs text-muted-foreground" role="status">
      {{ face.sourceLoading ? 'Loading source page…' : 'Source page unavailable.' }}
    </p>
  </Item>
</template>
