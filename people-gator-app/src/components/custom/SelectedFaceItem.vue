<script setup lang="ts">
import EntityLinkStateBadge from './EntityLinkStateBadge.vue'
import IdentityFacePreview from './IdentityFacePreview.vue'
import UiTooltip from './UiTooltip.vue'
import {
  Check,
  ChevronRight,
  Link2,
  RefreshCw,
  Search,
  Trash2,
  Unlink,
  UserPlus,
  X,
} from '@lucide/vue'
import { ref, watch } from 'vue'

import ContentEditable from '@/components/custom/ContentEditable.vue'
import type { Face } from '@/viewmodels/document-workspace.types'
import LoadableImage from '@/components/custom/LoadableImage.vue'
import { Button } from '@/components/ui/button'
import { Item, ItemContent, ItemFooter, ItemMedia, ItemTitle } from '@/components/ui/item'

const props = withDefaults(
  defineProps<{
    face: Face
    assignmentPending?: boolean
    canAnnotate?: boolean
    canDelete?: boolean
    actionError?: string
  }>(),
  { canAnnotate: true },
)

const emit = defineEmits<{
  findProfile: []
  searchFace: []
  createProfile: [profile: { name: string; shortDescription?: string }]
  unassign: []
  delete: []
}>()

const isCreating = ref(false)
const draftName = ref('')
const draftShortDescription = ref('')

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
    class="w-full items-center gap-x-3 gap-y-2 px-3 py-2.5"
    @submit.prevent="createProfile"
    @keydown.esc="isCreating && ($event.stopPropagation(), cancelCreating())"
  >
    <ItemMedia class="relative self-start">
      <div class="size-12 overflow-hidden rounded-full bg-muted">
        <LoadableImage
          :src="face.portrait"
          :loading="face.portraitLoading"
          :alt="face.personId ? face.name : 'Unassigned face'"
          class="size-full"
          image-class="size-full object-cover grayscale"
        />
      </div>
      <!-- The person's other faces open from a small + over this face. -->
      <span v-if="face.personId && !isCreating" class="absolute -right-1 -bottom-1">
        <IdentityFacePreview :key="face.personId" :person-id="face.personId" :name="face.name" />
      </span>
    </ItemMedia>

    <ItemContent v-if="isCreating" class="min-w-0 gap-1 overflow-hidden">
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

    <ItemContent v-else class="min-w-0 items-start gap-1 overflow-hidden">
      <ItemTitle class="min-w-0 w-full max-w-full">
        <RouterLink
          v-if="face.personId"
          :to="{
            name: 'person-detail',
            params: { personId: face.personId },
            query: {
              origin_matched_face: face.id,
            },
          }"
          class="flex min-w-0 w-full items-center gap-1 underline-offset-4 transition-transform group hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <h4
            class="flex min-h-6 min-w-0 w-full items-center gap-1.5 rounded-sm border border-transparent px-1"
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
          class="min-h-6 w-full truncate rounded-sm border border-transparent px-1 text-muted-foreground"
        >
          Unassigned face
        </h4>
      </ItemTitle>

      <EntityLinkStateBadge v-bind="face" />
    </ItemContent>

    <ItemFooter class="w-full shrink-0 flex-wrap items-center justify-start gap-2 border-t pt-2">
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
        <div class="flex min-w-0 flex-wrap items-center justify-start gap-1">
          <UiTooltip
            :text="face.embeddingModel ? 'Search people by this face' : 'Face search unavailable'"
          >
            <Button
              type="button"
              size="icon-xs"
              variant="outline"
              :disabled="!face.embeddingModel"
              aria-label="Search people by this face"
              @click="emit('searchFace')"
            >
              <Search aria-hidden="true" />
            </Button>
          </UiTooltip>
          <template v-if="canAnnotate">
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
            <!-- Order: search, link, new, unlink, verify, delete. -->
            <slot name="actions" />
          </template>
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
