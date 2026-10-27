<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { relatedQuery } from '@/viewmodels/shared-filters'
import ArchiveLink from './ArchiveLink.vue'
import FaceSelectionControl from './FaceSelectionControl.vue'
import SelectedFaceActions from './SelectedFaceActions.vue'
import SearchFilterPanel from './SearchFilterPanel.vue'
import FilterMultiSelect from './FilterMultiSelect.vue'
import {
  X,
  Check,
  ChevronRight,
  CircleUserRound,
  Images,
  Link as LinkIcon,
  UserRoundX,
  UserRoundSearch,
} from '@lucide/vue'
import { computed, ref, watch } from 'vue'

import PersonPortrait from './PersonPortrait.vue'
import LoadableImage from '@/components/custom/LoadableImage.vue'
import type {
  PersonDiscoveryCandidate,
  PersonDiscoveryFace,
} from '@/viewmodels/person-detail.types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Item, ItemContent, ItemMedia } from '@/components/ui/item'
import FilterSingleSelect from './FilterSingleSelect.vue'
import SortControl from './SortControl.vue'
import type { EntityAnnotation, EntitySortField, FaceSortField } from '@/client'
import type { SortOption, SortState } from '@/lib/sorting'

const route = useRoute()
const router = useRouter()
const props = defineProps<{
  faces: PersonDiscoveryFace[]
  people: PersonDiscoveryCandidate[]
  currentName: string
  referenceFaceCount: number
  modelOptions?: { value: string; label: string }[]
  defaultFaceModel?: string
  assigningFaces?: boolean
  assignmentFailed?: boolean
  mergingPeople?: boolean
  mergeSucceeded?: boolean
  mergeFailed?: boolean
  loadingFaces?: boolean
  loadingPeople?: boolean
  searchError?: unknown
  faceSortOptions?: SortOption<FaceSortField>[]
  peopleSortOptions?: SortOption<EntitySortField>[]
}>()

const searchTerm = defineModel<string>('searchTerm', { default: '' })
const annotations = defineModel<EntityAnnotation[]>('annotations', {
  default: () => ['faces', 'aliases', 'name'],
})
const faceModel = defineModel<string>('faceModel', { default: '' })
const hasReferenceFilters = computed(
  () => annotations.value.length > 0 && annotations.value.length < 3,
)
const hasModelOverride = computed(() =>
  Boolean(faceModel.value && faceModel.value !== props.defaultFaceModel),
)
const modelLabel = computed(
  () =>
    props.modelOptions?.find((option) => option.value === faceModel.value)?.label ??
    faceModel.value,
)
const inputSearch = ref('')
const inputOptions = computed(() =>
  [
    { id: 'faces', label: 'Faces' },
    { id: 'aliases', label: 'Aliases' },
    { id: 'name', label: 'Name' },
  ].filter((option) => option.label.toLowerCase().includes(inputSearch.value.toLowerCase())),
)
const selectedInputs = computed({
  get: () => annotations.value,
  set: (values: string[]) => {
    annotations.value = values.filter((value): value is EntityAnnotation =>
      ['faces', 'aliases', 'name'].includes(value),
    )
  },
})
const inputLabels = { faces: 'Faces', aliases: 'Aliases', name: 'Name' }
const faceSort = defineModel<SortState<FaceSortField>>('faceSort')
const peopleSort = defineModel<SortState<EntitySortField>>('peopleSort')

const emit = defineEmits<{
  retry: []
  clearFilters: []
  assignFaces: [faceIds: string[]]
  mergePeople: [entityIds: string[]]
}>()

const selectedFaceIds = ref<Set<string>>(new Set())
const selectedPersonIds = ref<Set<string>>(new Set())
const selectionAnchorId = ref<string | null>(null)
const personSelectionAnchorId = ref<string | null>(null)
type FaceFilter = 'all' | 'unassigned' | 'assigned'
const fallbackFaceFilter = ref<FaceFilter>('all')
const faceFilter = computed({
  get: () => {
    const value = route?.query.discovery_assignment
    return value === 'unassigned' || value === 'assigned'
      ? value
      : route
        ? 'all'
        : fallbackFaceFilter.value
  },
  set: (value: FaceFilter) => {
    fallbackFaceFilter.value = value
    if (route)
      void router.push({
        query: { ...route.query, discovery_assignment: value === 'all' ? undefined : value },
      })
  },
})
const faceFilterOptions: Array<{ value: FaceFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'unassigned', label: 'Unassigned' },
  { value: 'assigned', label: 'Assigned elsewhere' },
]
const visibleFaces = computed(() =>
  props.faces.filter((face) => {
    if (faceFilter.value === 'unassigned') return !face.assignedEntityId
    if (faceFilter.value === 'assigned') return Boolean(face.assignedEntityId)
    return true
  }),
)
const selectedFaces = computed(() =>
  props.faces.filter((face) => selectedFaceIds.value.has(face.id)),
)
const selectedPeople = computed(() =>
  props.people.filter((person) => selectedPersonIds.value.has(person.id)),
)
const selectionEnabled = computed(() => selectedFaceIds.value.size > 0)
const selectedReassignmentCount = computed(
  () => selectedFaces.value.filter((face) => face.assignedEntityId).length,
)

function toggleFaceSelection(faceId: string, event: MouseEvent) {
  clearPersonSelection()
  if (event.shiftKey && addFaceRangeToSelection(faceId)) {
    event.preventDefault()
    return
  }

  toggleFaceFromControl(faceId)
}

function addFaceRangeToSelection(faceId: string) {
  const faceIndex = props.faces.findIndex((face) => face.id === faceId)
  const anchorIndex = props.faces.findIndex((face) => face.id === selectionAnchorId.value)

  if (anchorIndex < 0 || faceIndex < 0) return false

  const rangeStart = Math.min(anchorIndex, faceIndex)
  const rangeEnd = Math.max(anchorIndex, faceIndex)
  selectedFaceIds.value = new Set([
    ...selectedFaceIds.value,
    ...props.faces.slice(rangeStart, rangeEnd + 1).map((face) => face.id),
  ])
  return true
}

function toggleFaceFromControl(faceId: string) {
  const nextSelection = new Set(selectedFaceIds.value)
  if (nextSelection.has(faceId)) nextSelection.delete(faceId)
  else nextSelection.add(faceId)
  selectedFaceIds.value = nextSelection
  selectionAnchorId.value = faceId
}

function addFaceToSelection(faceId: string, event: MouseEvent) {
  clearPersonSelection()
  if (event.shiftKey && addFaceRangeToSelection(faceId)) return
  if (selectedFaceIds.value.has(faceId)) return
  selectedFaceIds.value = new Set([...selectedFaceIds.value, faceId])
  selectionAnchorId.value = faceId
}

function clearFaceSelection() {
  selectedFaceIds.value = new Set()
  selectionAnchorId.value = null
}

function addPersonRangeToSelection(personId: string) {
  const personIndex = props.people.findIndex((person) => person.id === personId)
  const anchorIndex = props.people.findIndex(
    (person) => person.id === personSelectionAnchorId.value,
  )
  if (personIndex < 0 || anchorIndex < 0) return false
  const start = Math.min(personIndex, anchorIndex)
  const end = Math.max(personIndex, anchorIndex)
  selectedPersonIds.value = new Set([
    ...selectedPersonIds.value,
    ...props.people.slice(start, end + 1).map((person) => person.id),
  ])
  return true
}

function togglePersonSelection(personId: string, event: MouseEvent) {
  clearFaceSelection()
  if (event.shiftKey && addPersonRangeToSelection(personId)) return
  const nextSelection = new Set(selectedPersonIds.value)
  if (nextSelection.has(personId)) nextSelection.delete(personId)
  else nextSelection.add(personId)
  selectedPersonIds.value = nextSelection
  personSelectionAnchorId.value = personId
}

function addPersonToSelection(personId: string, event: MouseEvent) {
  clearFaceSelection()
  if (event.shiftKey && addPersonRangeToSelection(personId)) return
  if (selectedPersonIds.value.has(personId)) return
  selectedPersonIds.value = new Set([...selectedPersonIds.value, personId])
  personSelectionAnchorId.value = personId
}

function clearPersonSelection() {
  selectedPersonIds.value = new Set()
  personSelectionAnchorId.value = null
}

function mergeSelectedPeople() {
  emit(
    'mergePeople',
    selectedPeople.value.map((person) => person.id),
  )
}

function assignSelectedFaces() {
  emit(
    'assignFaces',
    selectedFaces.value.map((face) => face.id),
  )
}

watch(
  () => props.faces.map((face) => face.id),
  (availableFaceIds) => {
    const available = new Set(availableFaceIds)
    selectedFaceIds.value = new Set(
      [...selectedFaceIds.value].filter((faceId) => available.has(faceId)),
    )
    if (selectionAnchorId.value && !available.has(selectionAnchorId.value)) {
      selectionAnchorId.value = null
    }
  },
)

watch(
  () => props.people.map((person) => person.id),
  (availablePersonIds) => {
    const available = new Set(availablePersonIds)
    selectedPersonIds.value = new Set(
      [...selectedPersonIds.value].filter((personId) => available.has(personId)),
    )
    if (personSelectionAnchorId.value && !available.has(personSelectionAnchorId.value)) {
      personSelectionAnchorId.value = null
    }
  },
)

watch(
  () => props.mergeSucceeded,
  (succeeded) => {
    if (succeeded) clearPersonSelection()
  },
)
</script>

<template>
  <div class="space-y-10 pt-6">
    <div>
      <SearchFilterPanel
        v-model="searchTerm"
        label="Discovery search"
        placeholder="Add search text"
        :result-count="props.faces.length + props.people.length"
      >
        <FilterMultiSelect
          v-model="selectedInputs"
          v-model:search="inputSearch"
          label="Reference inputs"
          :options="inputOptions"
        />
        <FilterSingleSelect
          v-if="props.modelOptions?.length"
          v-model="faceModel"
          label="Face model"
          :options="props.modelOptions"
        />
      </SearchFilterPanel>
      <div
        v-if="hasReferenceFilters || hasModelOverride"
        class="mt-3 flex min-w-0 flex-wrap items-center gap-2"
        aria-label="Active discovery filters"
      >
        <template v-if="hasReferenceFilters">
          <Badge
            v-for="input in annotations"
            :key="input"
            as="small"
            variant="outline"
            class="max-w-full gap-1"
          >
            <span class="min-w-0 break-all">Reference: {{ inputLabels[input] }}</span>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              class="rounded-full"
              :aria-label="`Remove reference ${inputLabels[input].toLowerCase()}`"
              @click="annotations = annotations.filter((item) => item !== input)"
              ><X aria-hidden="true"
            /></Button>
          </Badge>
        </template>
        <Badge v-if="hasModelOverride" as="small" variant="outline" class="max-w-full gap-1">
          <span class="min-w-0 break-all">Face model: {{ modelLabel }}</span>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            class="rounded-full"
            aria-label="Remove face model"
            @click="faceModel = ''"
            ><X aria-hidden="true"
          /></Button>
        </Badge>
        <Button type="button" variant="ghost" size="sm" @click="emit('clearFilters')"
          >Clear filters</Button
        >
      </div>
      <p v-if="!annotations.length && !searchTerm.trim()" role="status" class="mt-3">
        Choose a reference input or enter search text.
      </p>
      <div v-if="props.searchError" role="alert" class="mt-3 flex flex-wrap items-center gap-2">
        <p>Search failed. Choose other reference inputs or a face model, then retry.</p>
        <Button type="button" variant="outline" size="sm" @click="emit('retry')">Retry</Button>
      </div>
    </div>
    <section aria-labelledby="similar-faces-heading">
      <div class="flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
        <div>
          <small class="font-semibold uppercase text-secondary">Face similarity</small>
          <h3 id="similar-faces-heading">Found faces to review</h3>
          <p class="mt-1 max-w-3xl text-sm text-muted-foreground">
            Matches from the selected reference inputs for {{ props.currentName }}.
          </p>
        </div>
        <Badge variant="outline" class="font-mono">{{ props.faces.length }} matches</Badge>
      </div>

      <SearchFilterPanel label="Discovery faces" filters-only class="mt-4">
        <FilterSingleSelect
          v-model="faceFilter"
          label="Discovery assignment"
          :options="faceFilterOptions"
        />
        <SortControl
          v-if="faceSort && props.faceSortOptions"
          v-model="faceSort"
          :options="props.faceSortOptions"
          label="Sort similar faces"
        />
      </SearchFilterPanel>

      <p v-if="props.assignmentFailed" role="alert" class="mt-3">
        Assignment failed. Select faces and try Assign again.
      </p>
      <SelectedFaceActions
        v-if="selectedFaces.length"
        :count="selectedFaces.length"
        :busy="props.assigningFaces"
        @clear="clearFaceSelection"
      >
        <template #description>
          <template v-if="selectedReassignmentCount"
            >{{ selectedReassignmentCount }} will be reassigned from another person.</template
          >
          <template v-else
            >Click faces to add them; use the checkboxes to remove them or Shift-select a
            range.</template
          >
        </template>
        <Button
          type="button"
          size="sm"
          :disabled="props.assigningFaces"
          @click="assignSelectedFaces"
        >
          <LinkIcon aria-hidden="true" />
          {{ props.assigningFaces ? 'Assigning…' : `Assign to ${props.currentName}` }}
        </Button>
      </SelectedFaceActions>

      <div
        v-if="visibleFaces.length"
        class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6"
        aria-live="polite"
      >
        <Item
          v-for="face in visibleFaces"
          :key="face.id"
          class="group/face relative h-full min-w-0 flex-col flex-nowrap items-stretch gap-2 overflow-hidden rounded-none border bg-card p-2 text-muted-foreground shadow-none transition-colors hover:border-accent hover:text-primary"
          :class="
            selectedFaceIds.has(face.id) &&
            'border-secondary bg-secondary/20 text-primary hover:bg-secondary/20'
          "
        >
          <RouterLink
            v-if="!selectionEnabled && face.library && face.documentId && face.pageId"
            data-face-selection-target="open"
            :to="{
              name: 'document-page',
              params: {
                libraryId: face.library,
                documentId: face.documentId,
                pageId: face.pageId,
              },
              query: relatedQuery(route, { person: face.id, origin_matched_face: face.id }),
            }"
            class="absolute inset-0 z-10 rounded-[inherit] outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
            :aria-label="`Open face ${face.id} on its source document`"
          ></RouterLink>
          <button
            v-else-if="selectionEnabled"
            type="button"
            data-face-selection-target="add"
            class="absolute inset-0 z-10 rounded-[inherit] outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
            :aria-label="
              selectedFaceIds.has(face.id)
                ? `Face ${face.id} is selected`
                : `Add face ${face.id} to selection`
            "
            @click="addFaceToSelection(face.id, $event)"
          ></button>
          <ItemMedia
            variant="image"
            class="relative aspect-square size-auto w-full rounded-none bg-muted"
          >
            <LoadableImage
              :src="face.portrait"
              :loading="face.portraitLoading"
              :alt="`Face similar to ${props.currentName}`"
              class="size-full"
              image-class="object-cover grayscale duration-300 ease-out group-hover/face:scale-105 group-focus-within/face:scale-102"
            >
              <template #fallback>
                <div class="flex size-full items-center justify-center text-muted-foreground">
                  <CircleUserRound class="size-10" aria-hidden="true" />
                </div>
              </template>
            </LoadableImage>
          </ItemMedia>
          <ArchiveLink :url="face.pageUrl" class="absolute left-3 top-3" />
          <FaceSelectionControl
            :face-id="face.id"
            :selected="selectedFaceIds.has(face.id)"
            :disabled="props.assigningFaces"
            purpose="assignment"
            @toggle="toggleFaceSelection(face.id, $event)"
          />
          <ItemContent class="min-w-0 flex-none gap-0 overflow-hidden px-0">
            <p
              class="flex min-w-0 items-center gap-1 text-sm"
              :class="
                face.assignedEntityId
                  ? 'text-emerald-700 dark:text-emerald-400'
                  : 'text-muted-foreground'
              "
            >
              <LinkIcon v-if="face.assignedEntityId" class="size-4 shrink-0" aria-hidden="true" />
              <UserRoundX v-else class="size-4 shrink-0" aria-hidden="true" />
              <b
                class="min-w-0 flex-1 truncate"
                :title="face.assignedEntityName || face.assignedEntityId || 'Unassigned'"
              >
                {{ face.assignedEntityName || face.assignedEntityId || 'Unassigned' }}
              </b>
              <RouterLink
                v-if="face.assignedEntityId"
                :to="{
                  name: 'person-detail',
                  params: { personId: face.assignedEntityId },
                  query: relatedQuery(route, { origin_matched_face: face.id }),
                }"
                class="relative z-20"
                :aria-label="`Open matching person ${face.assignedEntityName || face.assignedEntityId}`"
                >Profile</RouterLink
              >
              <code class="ml-auto shrink-0 text-sm text-muted-foreground">
                <template v-if="face.score != null">sim {{ face.score }}%</template>
                <template v-else>Text match</template>
              </code>
            </p>
          </ItemContent>
          <div
            v-if="face.library && face.documentId && face.pageId"
            class="flex min-w-0 items-center gap-1 text-xs text-muted-foreground"
          >
            <span class="min-w-0 flex-1 truncate">
              <b class="text-secondary">{{ face.library }}</b>
              · {{ face.pageLabel }}
            </span>
            <ChevronRight
              class="size-4 transition-transform group-hover/face:translate-x-1"
              aria-hidden="true"
            />
          </div>
          <div v-else class="truncate text-xs text-muted-foreground">
            Archive location unavailable
          </div>
        </Item>
      </div>

      <div
        v-else
        class="mt-5 flex min-h-40 flex-col items-center justify-center border border-dashed px-5 text-center text-muted-foreground"
        aria-live="polite"
      >
        <Images class="mb-2 size-7" aria-hidden="true" />
        <p v-if="props.loadingFaces">Searching the archive for similar faces…</p>
        <p v-else-if="props.faces.length">No faces match this assignment filter.</p>
        <p v-else>No similar face matches were found.</p>
      </div>
    </section>

    <section class="border-t pt-8" aria-labelledby="similar-people-heading">
      <div class="flex w-full flex-row flex-wrap gap-4">
        <div>
          <small class="font-semibold uppercase text-secondary">Identity similarity</small>
          <h3 id="similar-people-heading">Similar people</h3>
          <p class="mt-1 max-w-2xl text-sm text-muted-foreground">
            Review possible duplicates before merging.
          </p>
        </div>
        <SearchFilterPanel label="Discovery people" filters-only>
          <SortControl
            v-if="peopleSort && props.peopleSortOptions"
            v-model="peopleSort"
            :options="props.peopleSortOptions"
            label="Sort similar people"
          />
        </SearchFilterPanel>
      </div>

      <p v-if="props.mergeFailed" role="alert" class="mt-3">
        Merge failed. Select people and try Merge again.
      </p>
      <div
        v-if="selectedPeople.length"
        class="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-4xl flex-col gap-3 border border-accent bg-card p-3 shadow-lg sm:flex-row sm:items-center sm:justify-between"
        role="toolbar"
        aria-label="Selected person actions"
      >
        <div class="min-w-0">
          <p class="font-semibold">
            {{ selectedPeople.length }}
            {{ selectedPeople.length === 1 ? 'person' : 'people' }} selected
          </p>
          <p class="text-xs text-muted-foreground">
            Their faces and mentions will move to {{ props.currentName }}. The selected records will
            be deleted.
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            :disabled="props.mergingPeople"
            @click="clearPersonSelection"
            >Clear</Button
          >
          <Button
            type="button"
            size="sm"
            :disabled="props.mergingPeople"
            @click="mergeSelectedPeople"
          >
            <LinkIcon aria-hidden="true" />
            {{ props.mergingPeople ? 'Merging…' : `Merge into ${props.currentName}` }}
          </Button>
        </div>
      </div>

      <div
        v-if="props.people.length"
        class="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
        aria-live="polite"
      >
        <div v-for="person in props.people" :key="person.id" class="group relative min-w-0">
          <RouterLink
            v-if="!selectedPersonIds.size"
            :to="{
              name: 'person-detail',
              params: { personId: person.id },
              query: relatedQuery(route, {
                origin_matched_face: person.matchedFaceIds?.length
                  ? person.matchedFaceIds
                  : undefined,
              }),
            }"
            class="absolute inset-0 z-10 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            :aria-label="`Open ${person.name}`"
          />
          <button
            v-else
            type="button"
            :disabled="props.mergingPeople"
            class="absolute inset-0 z-10 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            :aria-label="
              selectedPersonIds.has(person.id)
                ? `${person.name} is selected`
                : `Add ${person.name} to selection`
            "
            @click="addPersonToSelection(person.id, $event)"
          ></button>
          <Card
            class="h-full flex-row items-center gap-4 rounded-none p-4 shadow-none transition-colors group-hover:border-accent group-focus-visible:border-ring group-focus-visible:ring-2 group-focus-visible:ring-ring/50"
            :class="selectedPersonIds.has(person.id) && 'border-secondary bg-secondary/20'"
          >
            <button
              type="button"
              :disabled="props.mergingPeople"
              class="absolute right-2 top-2 z-20 flex size-7 items-center justify-center rounded-sm border-2 shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              :class="
                selectedPersonIds.has(person.id)
                  ? 'border-accent bg-accent text-accent-foreground'
                  : 'border-border bg-card text-muted-foreground hover:border-accent hover:text-primary'
              "
              :aria-label="`${selectedPersonIds.has(person.id) ? 'Remove' : 'Select'} ${person.name} ${selectedPersonIds.has(person.id) ? 'from merge' : 'for merge'}`"
              :aria-pressed="selectedPersonIds.has(person.id)"
              @click="togglePersonSelection(person.id, $event)"
            >
              <Check v-if="selectedPersonIds.has(person.id)" class="size-4" aria-hidden="true" />
              <span
                v-else
                class="size-2 rounded-full border border-current"
                aria-hidden="true"
              ></span>
            </button>
            <PersonPortrait
              :name="person.name"
              :face-id="person.thumbnailFaceId"
              class="size-16 shrink-0"
            />
            <div class="min-w-0 flex-1">
              <h4 class="truncate" :title="person.name">{{ person.name }}</h4>
              <p v-if="person.shortDescription" class="line-clamp-2 text-sm text-muted-foreground">
                {{ person.shortDescription }}
              </p>
              <p v-else-if="person.aliases.length" class="truncate text-sm text-muted-foreground">
                {{ person.aliases.join(' · ') }}
              </p>
              <div class="mt-2 flex flex-wrap gap-1">
                <Badge v-if="person.matchedFaceIds?.length" variant="outline">Face</Badge>
                <Badge v-if="person.textMatch" variant="outline">Text</Badge>
              </div>
            </div>
            <ChevronRight
              class="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1 group-focus-visible:translate-x-1"
              aria-hidden="true"
            />
          </Card>
        </div>
      </div>

      <div
        v-else
        class="mt-5 flex min-h-40 flex-col items-center justify-center border border-dashed px-5 text-center text-muted-foreground"
        aria-live="polite"
      >
        <UserRoundSearch class="mb-2 size-7" aria-hidden="true" />
        <p v-if="props.loadingPeople">Searching for similar people…</p>
        <p v-else>No other people match the selected inputs.</p>
      </div>
    </section>
  </div>
</template>
