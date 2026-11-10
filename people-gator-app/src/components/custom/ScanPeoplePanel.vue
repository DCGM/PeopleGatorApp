<script setup lang="ts">
import { ScrollArea } from '@/components/ui/scroll-area'
import { computed, nextTick, ref, watch } from 'vue'
import { useMediaQuery, watchDebounced } from '@vueuse/core'
import { ChevronDown, Plus, ScanFace, Search, SlidersHorizontal } from '@lucide/vue'
import ListPagination from './ListPagination.vue'
import SearchFaceAttachment from './SearchFaceAttachment.vue'
import SimilarPersonItem from './SimilarPersonItem.vue'
import SimilarPersonItemSkeleton from './SimilarPersonItemSkeleton.vue'
import SortSelect from './SortSelect.vue'
import SharedFilterControls from './SharedFilterControls.vue'
import SharedFilterTags from './SharedFilterTags.vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { SIDEBAR_TITLE } from './sidebar-title'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'
import { Button } from '@/components/ui/button'
import type { Face } from '@/viewmodels/document-workspace.types'
import type { SimilarPersonCandidate } from '@/viewmodels/similar-people.types'
import {
  PEOPLE_ORDERS,
  PEOPLE_SCOPES,
  type PeopleOrder,
  type PeopleScope,
} from '@/viewmodels/scan-sidebar'

const props = defineProps<{
  people: SimilarPersonCandidate[]
  scored: boolean
  loading: boolean
  totalCount?: number
  hasNextPage: boolean
  isFetching: boolean
  error?: unknown
  searchFaceId: string | null
  /** Embedding models available for the attached face. */
  faceModels?: string[]
  faceModel?: string | null
  selectedFace: Face | null
  viewedPersonId: string | null
  assignmentPending?: boolean
  loadMore: () => Promise<unknown>
  retry: () => unknown
}>()
/** The applied name text; typing applies it after a pause, or at once on Search. */
const text = defineModel<string>('text', { required: true })
const scope = defineModel<PeopleScope>('scope', { required: true })
const order = defineModel<PeopleOrder>('order', { required: true })
const emit = defineEmits<{
  'update:faceModel': [model: string]
  removeFace: []
  /** Attach the face selected on the scan as the search reference. */
  attachSelectedFace: []
  preview: [person: SimilarPersonCandidate]
  assign: [person: SimilarPersonCandidate]
}>()

const desktopFilters = useMediaQuery('(min-width: 640px)')
const mobileFiltersOpen = ref(false)
const filtersOpen = computed({
  get: () => desktopFilters.value || mobileFiltersOpen.value,
  set: (value) => {
    mobileFiltersOpen.value = value
  },
})
const draft = ref(text.value)
// Back/Forward, links and face Search replace the draft with the applied text.
watch([text, () => props.searchFaceId], () => (draft.value = text.value))
const changed = computed(() => draft.value.trim() !== text.value.trim())
// Typing searches after a short pause; Enter or Search apply it at once.
watchDebounced(draft, () => search(), { debounce: 300 })
function search() {
  if (changed.value) text.value = draft.value.trim()
}

const scopeLabel = computed(
  () => PEOPLE_SCOPES.find((item) => item.value === scope.value)?.label ?? '',
)
const faceModelValue = computed({
  get: () => props.faceModel ?? '',
  set: (value: string) => emit('update:faceModel', value),
})
const scopeValue = computed({
  get: () => scope.value,
  set: (value: string) => (scope.value = value as PeopleScope),
})
const orderOptions = computed(() =>
  PEOPLE_ORDERS.filter((option) => props.scored || !option.scored),
)
const orderValue = computed({
  get: () => order.value,
  set: (value: string) => (order.value = value as PeopleOrder),
})
// Search attaches one face for now; the menu is where aliases and more faces will go.
const canAttachSelected = computed(
  () =>
    Boolean(props.selectedFace?.embeddingModel) && props.selectedFace?.id !== props.searchFaceId,
)
const countLabel = computed(() =>
  props.loading || props.totalCount === undefined
    ? ''
    : `${props.totalCount} ${props.totalCount === 1 ? 'result' : 'results'}`,
)
const group = ref<HTMLElement | null>(null)
const results = ref<HTMLElement | null>(null)
const resetKey = computed(() => `${scope.value}:${order.value}:${text.value}:${props.searchFaceId}`)

// Bring a newly previewed candidate into view once it is loaded. Later batches
// leave the scroll position alone, so loading more never jumps back to it.
let revealPending = false
watch(
  () => props.viewedPersonId,
  (id) => (revealPending = Boolean(id)),
  { immediate: true },
)
watch(
  () => [props.viewedPersonId, props.people.length],
  async () => {
    if (!revealPending) return
    await nextTick()
    const viewed = results.value?.querySelector<HTMLElement>('[data-person-viewed="true"]')
    if (!viewed) return
    revealPending = false
    viewed.scrollIntoView?.({ block: 'nearest' })
  },
  { flush: 'post', immediate: true },
)

defineExpose({ focus: () => group.value?.querySelector('input')?.focus() })
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col" aria-label="People">
    <Collapsible v-model:open="filtersOpen" as-child>
      <form
        ref="group"
        class="flex w-full min-w-0 shrink-0 flex-row flex-wrap items-center gap-2 px-3 pt-3"
        role="search"
        aria-labelledby="people-search-title"
        @submit.prevent="search"
      >
        <h3 id="people-search-title" :class="SIDEBAR_TITLE" class="basis-full">Search</h3>
        <div class="flex min-w-0 basis-full items-center gap-2 sm:basis-[calc(66.6666667%-0.5rem)]">
          <InputGroup class="min-w-0 flex-1">
            <InputGroupInput
              v-model="draft"
              aria-label="Search people"
              placeholder="Name or alias"
            />
            <InputGroupAddon align="inline-end">
              <InputGroupButton type="submit" size="icon-xs" :disabled="!changed">
                <Search aria-hidden="true" />
                <span class="sr-only">Search</span>
              </InputGroupButton>
              <small class="shrink-0 whitespace-nowrap" role="status">{{ countLabel }}</small>
            </InputGroupAddon>
          </InputGroup>
          <CollapsibleTrigger v-if="!desktopFilters" as-child
            ><Button
              type="button"
              variant="outline"
              size="icon"
              :aria-label="mobileFiltersOpen ? 'Hide filters' : 'Show filters'"
              ><SlidersHorizontal aria-hidden="true" /></Button
          ></CollapsibleTrigger>
        </div>
        <!-- Always present at a fixed height, so attaching context never shifts results. -->
        <div
          class="flex h-8 min-w-0 basis-full flex-row flex-nowrap items-center gap-2 overflow-x-auto"
          role="group"
          aria-label="Search context"
        >
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button
                type="button"
                variant="outline"
                class="rounded-full"
                size="icon-xs"
                aria-label="Add search context"
              >
                <Plus aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="bottom" align="start" class="[--radius:0.95rem]">
              <DropdownMenuItem :disabled="!canAttachSelected" @select="emit('attachSelectedFace')">
                <ScanFace aria-hidden="true" />Selected face
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <SearchFaceAttachment
            v-if="searchFaceId"
            :face-id="searchFaceId"
            @remove="emit('removeFace')"
          />
        </div>
        <CollapsibleContent class="contents">
          <div
            class="flex min-w-0 basis-full flex-row flex-wrap items-center gap-1"
            aria-label="Search options"
          >
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  :aria-label="`Scope: ${scopeLabel}`"
                >
                  {{ scopeLabel }}<ChevronDown aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="bottom" align="start" class="[--radius:0.95rem]">
                <DropdownMenuRadioGroup v-model="scopeValue">
                  <DropdownMenuRadioItem
                    v-for="option in PEOPLE_SCOPES"
                    :key="option.value"
                    :value="option.value"
                    >{{ option.label }}</DropdownMenuRadioItem
                  >
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
            <DropdownMenu v-if="searchFaceId && faceModels?.length">
              <DropdownMenuTrigger as-child>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  class="min-w-0 shrink"
                  :aria-label="`Face model: ${faceModel ?? ''}`"
                  :title="faceModel ?? undefined"
                >
                  <span class="min-w-0 truncate">{{ faceModel }}</span
                  ><ChevronDown aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="bottom" align="start" class="[--radius:0.95rem]">
                <DropdownMenuRadioGroup v-model="faceModelValue">
                  <DropdownMenuRadioItem v-for="model in faceModels" :key="model" :value="model">{{
                    model
                  }}</DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <SharedFilterControls :controls="['creators', 'creationDates']" />
        </CollapsibleContent>
      </form>
    </Collapsible>
    <div class="px-3"><SharedFilterTags creation-only /></div>
    <div class="flex shrink-0 flex-row flex-wrap items-center justify-between gap-2 px-3 pt-3">
      <h3 id="people-results-title" :class="SIDEBAR_TITLE">Results</h3>
      <SortSelect v-model="orderValue" :strategies="orderOptions" label="Sort people" size="sm" />
    </div>
    <ScrollArea
      role="region"
      class="min-h-0 flex-1"
      aria-labelledby="people-results-title"
      :aria-busy="loading || isFetching"
    >
      <div ref="results" class="px-3 pb-3 pt-2">
        <ul class="flex flex-col gap-2">
          <li v-for="person in people" :key="person.id">
            <SimilarPersonItem
              :person="person"
              :assigned="selectedFace?.personId === person.id"
              :reassignment="Boolean(selectedFace?.personId && selectedFace.personId !== person.id)"
              :assignment-disabled="!selectedFace"
              :assignment-pending="assignmentPending"
              :viewed="viewedPersonId === person.id"
              :data-person-viewed="viewedPersonId === person.id"
              @preview="emit('preview', $event)"
              @assign="emit('assign', $event)"
            />
          </li>
        </ul>
        <SimilarPersonItemSkeleton v-if="loading" />
        <p
          v-else-if="!people.length && !hasNextPage && !error"
          class="py-6 text-center text-sm text-muted-foreground"
        >
          No matching people.
        </p>
        <ListPagination
          :has-next-page="hasNextPage"
          :is-fetching="isFetching"
          :error="error"
          error-text="Could not load people."
          :reset-key="resetKey"
          :load-more="loadMore"
          :retry="retry"
        />
      </div>
    </ScrollArea>
  </section>
</template>
