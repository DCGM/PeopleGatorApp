<script setup lang="ts">
import { useRoute } from 'vue-router'
import { relatedQuery } from '@/viewmodels/shared-filters'
const route = useRoute()
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import IdentityFacePreview from './IdentityFacePreview.vue'
import UiTooltip from './UiTooltip.vue'
import {
  Check,
  ChevronRight,
  ExternalLink,
  Link,
  Link2,
  RefreshCw,
  Trash2,
  Unlink,
  UserPlus,
  UserRoundX,
  X,
} from '@lucide/vue'
import { ref, watch } from 'vue'

import ContentEditable from '@/components/custom/ContentEditable.vue'
import type { Face } from '@/viewmodels/document-workspace.types'
import LoadableImage from '@/components/custom/LoadableImage.vue'
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

const props = defineProps<{
  face: Face
  assignmentPending?: boolean
  canDelete?: boolean
  actionError?: string
}>()

const emit = defineEmits<{
  findProfile: []
  createProfile: [profile: { name: string; shortDescription?: string }]
  unassign: []
  delete: []
}>()

const isCreating = ref(false)
const draftName = ref('')
const draftShortDescription = ref('')

function wikidataHref(value: string) {
  return /^https?:\/\//i.test(value) ? value : `https://www.wikidata.org/wiki/${value}`
}

function startCreating() {
  draftName.value = ''
  draftShortDescription.value = ''
  isCreating.value = true
}

function cancelCreating() {
  isCreating.value = false
  draftName.value = ''
  draftShortDescription.value = ''
}

function createProfile() {
  const name = draftName.value.trim()
  const shortDescription = draftShortDescription.value.trim()
  if (!name) return

  emit('createProfile', {
    name,
    shortDescription: shortDescription || undefined,
  })
  cancelCreating()
}

watch(() => props.face.id, cancelCreating)
</script>

<template>
  <Item
    :as="isCreating ? 'form' : 'div'"
    variant="outline"
    class="w-full relative items-start gap-x-4 gap-y-2 bg-card px-3 py-3"
    @submit.prevent="createProfile"
  >
    <ItemMedia class="self-start">
      <div class="relative size-15 overflow-hidden rounded-full bg-muted">
        <LoadableImage
          :src="face.portrait"
          :loading="face.portraitLoading"
          :alt="face.personId ? face.name : 'Unassigned face'"
          class="size-full"
          image-class="size-full object-cover grayscale"
        />
      </div>
    </ItemMedia>

    <ItemActions class="absolute right-0 top-0 pt-1 pr-1">
      <Badge
        variant="outline"
        class="font-mono text-xs py-0 uppercase border-none"
        :class="face.personId ? 'text-emerald-700' : 'text-muted-foreground'"
      >
        <Link v-if="face.personId" aria-hidden="true" />
        <UserRoundX v-else aria-hidden="true" />
        Current
      </Badge>
    </ItemActions>

    <ItemContent v-if="isCreating" class="min-w-0 gap-1 overflow-hidden pt-1">
      <ItemTitle class="min-w-0 w-full max-w-full">
        <ContentEditable
          v-model="draftName"
          as="h4"
          editable
          single-line
          aria-label="New person name"
          data-placeholder="Full name"
          class="min-h-8 w-full rounded-sm border border-ring bg-accent/10 px-1 py-0.5 empty:before:text-muted-foreground empty:before:content-[attr(data-placeholder)]"
          @keydown.enter.prevent="createProfile"
        />
      </ItemTitle>
      <ContentEditable
        v-model="draftShortDescription"
        as="p"
        editable
        single-line
        aria-label="New person short description"
        data-placeholder="Short description (optional)"
        class="min-h-[calc(2lh+0.25rem)] min-w-0 w-full rounded-sm border border-ring bg-accent/10 px-1 py-0.5 text-xs leading-snug text-muted-foreground empty:before:content-[attr(data-placeholder)]"
      />
    </ItemContent>

    <ItemContent v-else class="min-w-0 gap-1 overflow-hidden pt-1">
      <ItemTitle class="min-w-0 w-full max-w-full">
        <RouterLink
          v-if="face.personId"
          :to="{
            name: 'person-detail',
            params: { personId: face.personId },
            query: relatedQuery(route, {
              origin_matched_face: face.id,
            }),
          }"
          class="flex min-w-0 w-full items-center gap-1 underline-offset-4 transition-transform group hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <h4
            class="flex min-h-8 min-w-0 w-full items-center gap-1.5 rounded-sm border border-transparent px-1 py-0.5"
          >
            <span class="min-w-0 truncate">{{ face.name }}</span>
            <ChevronRight
              class="size-[1.15em] shrink-0 group-hover:translate-x-1 group-focus-visible:translate-x-1"
              aria-hidden="true"
            />
          </h4>
        </RouterLink>
        <h4
          v-else
          class="min-h-8 w-full truncate rounded-sm border border-transparent px-1 py-0.5 text-muted-foreground"
        >
          Unknown
        </h4>
      </ItemTitle>

      <EntityLinkStateBadge v-bind="face" />
      <p
        class="min-h-[calc(2lh+0.25rem)] min-w-0 truncate text-wrap rounded-sm border border-transparent px-1 py-0.5 text-xs leading-snug text-muted-foreground"
        :title="face.shortDescription"
      >
        {{
          face.shortDescription ? face.shortDescription : 'Unknown person, no description available'
        }}
      </p>
    </ItemContent>

    <ItemFooter class="w-full shrink-0 flex-wrap items-center justify-start gap-2 border-t pt-2">
      <a
        v-if="!isCreating && face.wikidataId"
        :href="wikidataHref(face.wikidataId)"
        target="_blank"
        rel="noopener noreferrer"
        class="flex min-w-0 basis-full items-center gap-1 text-xs text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground hover:decoration-current"
      >
        <span class="truncate">Wikidata</span>
        <ExternalLink class="size-3 shrink-0" aria-hidden="true" />
      </a>

      <div v-if="isCreating" class="flex min-w-0 flex-wrap items-center gap-1">
        <Button
          type="submit"
          size="xs"
          variant="outline"
          class="border-emerald-600 text-emerald-700 hover:text-emerald-700 dark:border-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-400"
          :disabled="!draftName.trim() || props.assignmentPending"
          aria-label="Create and assign profile"
          title="Create and assign profile"
        >
          <Check aria-hidden="true" />
          Save
        </Button>
        <Button
          type="button"
          size="xs"
          variant="outline"
          class="border-destructive text-destructive hover:text-destructive dark:border-destructive"
          :disabled="props.assignmentPending"
          aria-label="Cancel new profile"
          title="Cancel new profile"
          @click="cancelCreating"
        >
          <X aria-hidden="true" />
          Cancel
        </Button>
      </div>

      <div v-else class="flex min-w-0 w-full flex-wrap items-center gap-1">
        <IdentityFacePreview
          v-if="face.personId"
          :key="face.personId"
          :person-id="face.personId"
          :name="face.name"
        />
        <div class="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-1">
          <UiTooltip v-if="face.personId" text="Reassign to another profile">
            <Button
              type="button"
              size="icon-xs"
              variant="outline"
              class="border-amber-600 text-amber-700 hover:text-amber-700 dark:border-amber-500 dark:text-amber-400 dark:hover:text-amber-400"
              :disabled="props.assignmentPending"
              aria-label="Reassign to another profile"
              @click="emit('findProfile')"
            >
              <RefreshCw aria-hidden="true" />
            </Button>
          </UiTooltip>
          <UiTooltip v-else text="Link to an existing profile">
            <Button
              type="button"
              size="icon-xs"
              variant="outline"
              :disabled="props.assignmentPending"
              class="border-amber-600 text-amber-700 hover:text-amber-700 dark:border-amber-500 dark:text-amber-400 dark:hover:text-amber-400"
              aria-label="Link to an existing profile"
              @click="emit('findProfile')"
            >
              <Link2 aria-hidden="true" />
            </Button>
          </UiTooltip>
          <UiTooltip text="Create and assign a new profile">
            <Button
              type="button"
              size="icon-xs"
              variant="outline"
              class="border-violet-600 text-violet-700 hover:text-violet-700 dark:border-violet-500 dark:text-violet-400 dark:hover:text-violet-400"
              :disabled="props.assignmentPending"
              aria-label="Create and assign a new profile"
              @click="startCreating"
            >
              <UserPlus aria-hidden="true" />
            </Button>
          </UiTooltip>
          <UiTooltip v-if="face.personId" text="Unassign current profile">
            <Button
              type="button"
              size="icon-xs"
              variant="outline"
              class="border-destructive text-destructive hover:text-destructive dark:border-destructive"
              :disabled="props.assignmentPending"
              aria-label="Unassign current profile"
              @click="emit('unassign')"
            >
              <Unlink aria-hidden="true" />
            </Button>
          </UiTooltip>
          <!-- Same order as the scan action bar: link, unlink, verify, delete. -->
          <slot name="actions" />
          <UiTooltip v-if="canDelete" text="Delete detection">
            <Button
              type="button"
              size="icon-xs"
              variant="outline"
              class="border-destructive text-destructive hover:text-destructive dark:border-destructive"
              :disabled="props.assignmentPending"
              aria-label="Delete detection"
              @click="emit('delete')"
            >
              <Trash2 aria-hidden="true" />
            </Button>
          </UiTooltip>
        </div>
      </div>
      <p v-if="actionError" role="alert" class="basis-full text-xs text-destructive">
        {{ actionError }}
      </p>
    </ItemFooter>
  </Item>
</template>
