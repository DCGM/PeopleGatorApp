<script setup lang="ts">
import { Check, ExternalLink, LetterText, ScanFace, TextCursor } from '@lucide/vue'
import { computed } from 'vue'

import type {
  SimilarPersonCandidate,
  SimilarPersonMatchSource,
} from '@/viewmodels/similar-people.types'
import PersonNameTitle from './PersonNameTitle.vue'
import PersonPortrait from './PersonPortrait.vue'
import IdentityFacePreview from './IdentityFacePreview.vue'
import EvidenceSourceBadge from './EvidenceSourceBadge.vue'
import { Button } from '@/components/ui/button'
import { Item, ItemContent, ItemFooter, ItemMedia } from '@/components/ui/item'

/** What Assign to face would do for the scan's selected face, if any. */
export type FaceAssignment = 'none' | 'assign' | 'reassign' | 'assigned'

const props = withDefaults(
  defineProps<{
    person: SimilarPersonCandidate
    /** Show Assign to mentions and Assign to face; each is disabled without its target. */
    canAssign?: boolean
    faceAssignment?: FaceAssignment
    /** Name mentions selected on the scan. */
    mentionCount?: number
    /** Every selected mention already links to this person. */
    mentionsAssigned?: boolean
    assignmentPending?: boolean
    viewed?: boolean
  }>(),
  { canAssign: true, faceAssignment: 'none', mentionCount: 0 },
)

const emit = defineEmits<{
  preview: [person: SimilarPersonCandidate]
  assign: [person: SimilarPersonCandidate]
  assignMentions: [person: SimilarPersonCandidate]
}>()

const mentionsLabel = computed(() => {
  const count = props.mentionCount
  if (props.mentionsAssigned) return `Mentions assigned to ${props.person.name}`
  if (!count) return `Assign mentions to ${props.person.name}`
  return `Assign ${count} ${count === 1 ? 'mention' : 'mentions'} to ${props.person.name}`
})
const faceLabel = computed(
  () =>
    ({
      none: `Assign face to ${props.person.name}`,
      assign: `Assign face to ${props.person.name}`,
      reassign: `Reassign face to ${props.person.name}`,
      assigned: `Face assigned to ${props.person.name}`,
    })[props.faceAssignment],
)

function wikidataHref(value: string) {
  return /^https?:\/\//i.test(value) ? value : `https://www.wikidata.org/wiki/${value}`
}

function nlcrAuthorityHref(value: string) {
  if (/^https?:\/\//i.test(value)) return value
  return `https://aleph.nkp.cz/F/?func=find-c&local_base=aut&ccl_term=ica=${encodeURIComponent(value)}`
}

function sourceLabel(source: SimilarPersonMatchSource) {
  switch (source.type) {
    case 'text-search':
      return `Text search score ${formatTextScore(source.score)}`
    case 'face-match':
      return `Face similarity ${faceSimilarity(source.distance)}%`
    case 'scan-text':
      return 'Mentioned on this page'
    case 'scan-face':
      return 'Face on this page'
    case 'in-document':
      return 'In this document'
  }
}

function formatTextScore(score: number) {
  return Math.round(score).toString()
}

function faceSimilarity(distance: number) {
  return Math.round((1 - distance) * 1000) / 10
}

const scores = computed(() =>
  (props.person.matchSources ?? []).filter(
    (source) => source.type === 'text-search' || source.type === 'face-match',
  ),
)
</script>

<template>
  <Item
    variant="outline"
    class="relative w-full items-start gap-x-4 gap-y-2 bg-card px-3 py-3 hover:border-accent"
    :class="viewed && 'border-accent bg-accent/15 ring-1 ring-accent hover:bg-accent/15'"
  >
    <button
      type="button"
      class="absolute inset-0 z-10 rounded-[inherit] outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      :aria-label="`Preview ${person.name} on this page`"
      :aria-pressed="viewed"
      @click="emit('preview', person)"
    ></button>

    <ItemMedia class="w-24 shrink-0 flex-col items-center gap-2 self-start">
      <div class="relative">
        <PersonPortrait :name="person.name" :face-id="person.thumbnailFaceId" class="size-15" />
        <!-- Above the card's preview layer, like the card's other controls. -->
        <span v-if="person.linkedFaces !== 0" class="absolute -right-1 -bottom-1 z-20">
          <IdentityFacePreview :person-id="person.id" :name="person.name" />
        </span>
      </div>
      <EvidenceSourceBadge :source="person.source" />
      <div
        v-if="scores.length"
        class="flex flex-col items-center gap-1"
        aria-label="Similarity scores"
      >
        <small
          v-for="source in scores"
          :key="source.type"
          class="flex items-center gap-1 text-muted-foreground tabular-nums"
          :aria-label="sourceLabel(source)"
          :title="sourceLabel(source)"
        >
          <template v-if="source.type === 'text-search'">
            <LetterText class="size-3.5 shrink-0" aria-hidden="true" />
            {{ formatTextScore(source.score) }}
          </template>
          <template v-else>
            <ScanFace class="size-3.5 shrink-0" aria-hidden="true" />
            {{ faceSimilarity(source.distance) }}%
          </template>
        </small>
      </div>
    </ItemMedia>

    <ItemContent class="min-w-0 gap-1 overflow-hidden pt-1">
      <PersonNameTitle
        :name="person.name"
        :person-id="person.id"
        :query="{
          origin_matched_face: person.faceId || undefined,
          origin_reference_face: person.referenceFaceId || undefined,
        }"
        link-class="z-20"
        :aria-label="`Open ${person.name}`"
      />
      <p
        class="min-h-[calc(2lh+0.25rem)] min-w-0 truncate text-wrap rounded-sm border border-transparent px-1 py-0.5 text-xs leading-snug text-muted-foreground"
        :title="person.shortDescription"
      >
        {{ person.shortDescription || 'No description available' }}
      </p>
    </ItemContent>

    <ItemFooter
      v-if="person.wikidataId || person.nlcrAuthorityId || canAssign"
      class="relative z-20 w-full shrink-0 flex-wrap items-center gap-2 border-t pt-2 text-muted-foreground"
    >
      <div
        v-if="person.wikidataId || person.nlcrAuthorityId"
        class="flex min-w-0 flex-1 flex-wrap items-center gap-2"
      >
        <a
          v-if="person.wikidataId"
          :href="wikidataHref(person.wikidataId)"
          target="_blank"
          rel="noopener noreferrer"
          class="flex min-w-0 items-center gap-1 text-xs underline decoration-border underline-offset-4 hover:text-foreground hover:decoration-current"
        >
          <span class="truncate">Wikidata</span>
          <ExternalLink class="size-3 shrink-0" aria-hidden="true" />
        </a>
        <a
          v-if="person.nlcrAuthorityId"
          :href="nlcrAuthorityHref(person.nlcrAuthorityId)"
          target="_blank"
          rel="noopener noreferrer"
          class="flex min-w-0 items-center gap-1 text-xs underline decoration-border underline-offset-4 hover:text-foreground hover:decoration-current"
        >
          <span class="truncate">NLCR AUT</span>
          <ExternalLink class="size-3 shrink-0" aria-hidden="true" />
        </a>
      </div>

      <!-- Each target has its own button, disabled while nothing of its kind is selected. -->
      <div v-if="canAssign" class="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-1">
        <Button
          type="button"
          size="xs"
          :variant="mentionsAssigned ? 'secondary' : 'outline'"
          :class="!mentionsAssigned && mentionCount > 0 && 'text-accent hover:text-accent'"
          :aria-pressed="mentionsAssigned"
          :aria-label="mentionsLabel"
          :title="mentionsLabel"
          :disabled="!mentionCount || mentionsAssigned || assignmentPending"
          @click="emit('assignMentions', person)"
        >
          <Check v-if="mentionsAssigned" aria-hidden="true" />
          <TextCursor v-else aria-hidden="true" />
          {{ mentionsAssigned ? 'Assigned' : 'Assign to mentions' }}
        </Button>
        <Button
          type="button"
          size="xs"
          :variant="faceAssignment === 'assigned' ? 'secondary' : 'outline'"
          :class="
            (faceAssignment === 'assign' || faceAssignment === 'reassign') &&
            'text-accent hover:text-accent'
          "
          :aria-pressed="faceAssignment === 'assigned'"
          :aria-label="faceLabel"
          :title="faceLabel"
          :disabled="
            faceAssignment === 'none' || faceAssignment === 'assigned' || assignmentPending
          "
          @click="emit('assign', person)"
        >
          <Check v-if="faceAssignment === 'assigned'" aria-hidden="true" />
          <ScanFace v-else aria-hidden="true" />
          {{
            faceAssignment === 'assigned'
              ? 'Assigned'
              : faceAssignment === 'reassign'
                ? 'Reassign face'
                : 'Assign to face'
          }}
        </Button>
      </div>
    </ItemFooter>
  </Item>
</template>
