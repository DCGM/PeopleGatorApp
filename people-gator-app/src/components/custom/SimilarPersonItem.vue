<script setup lang="ts">
import { useRoute } from 'vue-router'
import { relatedQuery } from '@/viewmodels/shared-filters'
import {
  Check,
  ChevronRight,
  ExternalLink,
  LetterText,
  Scan,
  ScanFace,
  Search,
  UserRound,
} from '@lucide/vue'

import type {
  SimilarPersonCandidate,
  SimilarPersonMatchSource,
} from '@/viewmodels/similar-people.types'
import PersonPortrait from './PersonPortrait.vue'
import IdentityFacePreview from './IdentityFacePreview.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemFooter,
  ItemMedia,
  ItemTitle,
} from '@/components/ui/item'

const route = useRoute()
const props = defineProps<{
  person: SimilarPersonCandidate
  assigned?: boolean
  reassignment?: boolean
  assignmentDisabled?: boolean
  assignmentPending?: boolean
  viewed?: boolean
}>()

const emit = defineEmits<{
  preview: [person: SimilarPersonCandidate]
  assign: [person: SimilarPersonCandidate]
}>()

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
      return `Face match cosine distance ${source.distance.toFixed(2)}`
    case 'scan-text':
      return 'Found in scanned text'
    case 'scan-face':
      return 'Found in scanned faces'
  }
}

function formatTextScore(score: number) {
  return Math.round(score).toString().padStart(2, '0')
}
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

    <ItemMedia class="self-start">
      <PersonPortrait :name="person.name" :face-id="person.thumbnailFaceId" class="size-15" />
    </ItemMedia>
    <ItemActions
      v-if="person.matchSources?.length"
      class="absolute self-start flex-row items-end gap-1 pt-0.5 pr-0.5 right-0 top-0"
      aria-label="Match sources"
    >
      <Badge
        v-for="(source, index) in person.matchSources"
        :key="`${source.type}-${index}`"
        variant="outline"
        class="min-h-5 font-mono text-xs py-0 text-muted-foreground border-none"
        :aria-label="sourceLabel(source)"
        :title="sourceLabel(source)"
      >
        <template v-if="source.type === 'text-search'">
          <Search aria-hidden="true" />
          <span class="inline-block w-[3ch] text-right tabular-nums">
            {{ formatTextScore(source.score) }}
          </span>
        </template>
        <template v-else-if="source.type === 'face-match'">
          <ScanFace aria-hidden="true" />
          <span class="inline-block w-[4ch] text-right tabular-nums">
            {{ source.distance.toFixed(2) }}
          </span>
        </template>
        <template v-else-if="source.type === 'scan-text'">
          <Scan aria-hidden="true" />
          <LetterText aria-hidden="true" />
          <span class="sr-only">Found in scanned text</span>
        </template>
        <template v-else>
          <Scan aria-hidden="true" />
          <UserRound aria-hidden="true" />
          <span class="sr-only">Found in scanned faces</span>
        </template>
      </Badge>
    </ItemActions>

    <ItemContent class="min-w-0 gap-1 overflow-hidden pt-1">
      <ItemTitle class="min-w-0 w-full max-w-full">
        <RouterLink
          :to="{
            name: 'person-detail',
            params: { personId: person.id },
            query: relatedQuery(route, {
              origin_matched_face: person.faceId || undefined,
              origin_reference_face: person.referenceFaceId || undefined,
            }),
          }"
          class="group z-20 flex min-w-0 w-full items-center gap underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          :aria-label="`Open ${person.name}`"
        >
          <h4
            class="flex min-h-8 min-w-0 w-full items-center gap-1.5 rounded-sm border border-transparent px-1 py-0.5"
          >
            <span class="min-w-0 truncate">{{ person.name }}</span>
            <ChevronRight
              class="size-[1.15em] shrink-0 transition-transform group-hover:translate-x-1 group-focus-visible:translate-x-1"
              aria-hidden="true"
            />
          </h4>
        </RouterLink>
      </ItemTitle>
      <p
        class="min-h-[calc(2lh+0.25rem)] min-w-0 truncate text-wrap rounded-sm border border-transparent px-1 py-0.5 text-xs leading-snug text-muted-foreground"
        :title="person.shortDescription"
      >
        {{ person.shortDescription || 'No description available' }}
      </p>
    </ItemContent>

    <ItemFooter
      class="relative z-20 w-full shrink-0 items-center border-t pt-2 text-muted-foreground"
    >
      <div class="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        <IdentityFacePreview :person-id="person.id" :name="person.name" />
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

      <Button
        v-if="!props.assignmentDisabled"
        type="button"
        size="xs"
        :variant="assigned ? 'secondary' : 'outline'"
        :class="!assigned && 'text-accent hover:text-accent'"
        :aria-pressed="assigned"
        :aria-label="
          assigned
            ? `Assigned to ${person.name}`
            : `${reassignment ? 'Reassign' : 'Assign'} to ${person.name}`
        "
        :disabled="assigned || props.assignmentPending"
        @click="emit('assign', person)"
      >
        <Check v-if="assigned" aria-hidden="true" />
        {{ assigned ? 'Assigned' : reassignment ? 'Reassign' : 'Assign' }}
      </Button>
    </ItemFooter>
  </Item>
</template>
