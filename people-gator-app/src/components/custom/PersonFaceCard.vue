<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import AnnotationLastChange from './AnnotationLastChange.vue'
import FaceSelectionControl from './FaceSelectionControl.vue'
import LoadableImage from './LoadableImage.vue'
import type { PersonFace } from '@/viewmodels/person-detail.types'
import { relatedEvidenceQuery } from '@/viewmodels/evidence-filters'
import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardFooter } from '@/components/ui/card'

const props = defineProps<{
  face: PersonFace
  personName: string
  matching?: boolean
  selectable?: boolean
  selected?: boolean
  selectionEnabled?: boolean
  busy?: boolean
}>()
defineEmits<{ toggle: [event: MouseEvent]; add: [event: MouseEvent] }>()
const route = useRoute()
const source = computed(
  () =>
    `${props.face.library} · ${props.face.documentId} · ${props.face.pageId || 'Page unavailable'}`,
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
        query: relatedEvidenceQuery(route, { person: props.face.id }),
      }
    : undefined,
)
</script>

<template>
  <Card
    class="relative min-w-0 gap-0 overflow-hidden py-0"
    :class="selected && 'border-secondary bg-secondary/20'"
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
      class="group block min-w-0"
    >
      <div class="relative">
        <AspectRatio :ratio="1" class="overflow-hidden bg-muted">
          <LoadableImage
            :src="face.portrait"
            :loading="face.portraitLoading"
            :alt="`${personName} detection in ${face.documentId}`"
            class="size-full"
            image-class="object-cover grayscale duration-300 ease-out group-hover:scale-105"
          />
        </AspectRatio>
        <Badge
          v-if="matching"
          class="absolute left-2 top-2 max-w-[calc(100%-4rem)]"
          variant="secondary"
          >Matching detection</Badge
        >
        <EntityLinkStateBadge
          v-bind="face"
          :focusable="false"
          class="absolute bottom-2 right-2 max-w-[calc(100%-1rem)]"
        />
      </div>
      <CardContent class="px-3 pt-3">
        <small
          class="block h-20 overflow-y-auto break-words leading-4 [overflow-wrap:anywhere]"
          :title="source"
          data-face-source
          >{{ source }}</small
        >
        <small class="mt-2 flex min-w-0 items-baseline justify-between gap-2 text-muted-foreground">
          <span class="min-w-0 truncate" :title="`Detection ID: ${face.id}`">{{ face.id }}</span>
          <span class="shrink-0" :title="`Detection confidence: ${face.confidence}%`"
            >{{ face.confidence }}%</span
          >
        </small>
      </CardContent>
    </component>
    <CardFooter class="block px-3 pb-3 pt-2">
      <AnnotationLastChange
        :touched-at="face.metadata?.last_touched_at"
        :user-id="face.metadata?.last_touched_by_user_id"
        class="h-10"
      />
      <div class="mt-2 h-6 overflow-y-auto">
        <p v-if="!face.pageId" class="text-xs text-muted-foreground" role="status">
          {{ face.sourceLoading ? 'Loading source page…' : 'Source page unavailable.' }}
        </p>
      </div>
    </CardFooter>
  </Card>
</template>
