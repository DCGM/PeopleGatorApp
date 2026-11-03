<script setup lang="ts">
import { ScrollArea } from '@/components/ui/scroll-area'
import { computed, nextTick, ref, watch } from 'vue'
import { watchDebounced } from '@vueuse/core'
import { ChevronDown, Plus, ScanFace, Search } from '@lucide/vue'
import ListPagination from './ListPagination.vue'
import SearchFaceAttachment from './SearchFaceAttachment.vue'
import SimilarPersonItem from './SimilarPersonItem.vue'
import SimilarPersonItemSkeleton from './SimilarPersonItemSkeleton.vue'
import SortSelect from './SortSelect.vue'
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
  InputGroupText,
  InputGroupTextarea,
} from '@/components/ui/input-group'
import { Separator } from '@/components/ui/separator'
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
  removeFace: []
  /** Attach the face selected on the scan as the search reference. */
  attachSelectedFace: []
  preview: [person: SimilarPersonCandidate]
  assign: [person: SimilarPersonCandidate]
}>()

const draft = ref(text.value)
// Back/Forward, links and face Search replace the draft with the applied text.
watch([text, () => props.searchFaceId], () => (draft.value = text.value))
const changed = computed(() => draft.value.trim() !== text.value.trim())
// Typing searches after a short pause; Enter or Search apply it at once.
watchDebounced(draft, () => search(), { debounce: 300 })
function search() {
  if (changed.value) text.value = draft.value.trim()
}
function keydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  search()
}

const scopeLabel = computed(
  () => PEOPLE_SCOPES.find((item) => item.value === scope.value)?.label ?? '',
)
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

// Keep the previewed candidate visible without scrolling the scan away.
watch(
  () => [props.viewedPersonId, props.people.length],
  async () => {
    if (!props.viewedPersonId) return
    await nextTick()
    results.value
      ?.querySelector<HTMLElement>('[data-person-viewed="true"]')
      ?.scrollIntoView?.({ block: 'nearest' })
  },
  { flush: 'post' },
)

defineExpose({ focus: () => group.value?.querySelector('textarea')?.focus() })
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col" aria-label="People">
    <form ref="group" class="shrink-0 px-3 pt-3" role="search" @submit.prevent="search">
      <InputGroup>
        <InputGroupTextarea
          v-model="draft"
          rows="1"
          class="min-h-0"
          aria-label="Search people"
          placeholder="Name or alias"
          @keydown="keydown"
        />
        <!-- Always present at a fixed height, so attaching context never resizes search. -->
        <InputGroupAddon
          align="block-end"
          aria-label="Search context"
          class="h-9 flex-nowrap overflow-x-auto pb-0"
        >
          <SearchFaceAttachment
            v-if="searchFaceId"
            :face-id="searchFaceId"
            @remove="emit('removeFace')"
          />
        </InputGroupAddon>
        <InputGroupAddon align="block-end">
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <InputGroupButton
                variant="outline"
                class="rounded-full"
                size="icon-xs"
                aria-label="Add search context"
              >
                <Plus class="size-4" aria-hidden="true" />
              </InputGroupButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start" class="[--radius:0.95rem]">
              <DropdownMenuItem :disabled="!canAttachSelected" @select="emit('attachSelectedFace')">
                <ScanFace aria-hidden="true" />Selected face
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <InputGroupButton variant="ghost" :aria-label="`Scope: ${scopeLabel}`">
                {{ scopeLabel }}<ChevronDown aria-hidden="true" />
              </InputGroupButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start" class="[--radius:0.95rem]">
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
          <InputGroupText class="ml-auto whitespace-nowrap" role="status">{{
            countLabel
          }}</InputGroupText>
          <Separator orientation="vertical" class="!h-4" />
          <InputGroupButton
            type="submit"
            variant="default"
            class="rounded-full"
            size="icon-xs"
            :disabled="!changed"
          >
            <Search class="size-4" aria-hidden="true" />
            <span class="sr-only">Search</span>
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
    </form>
    <div class="flex shrink-0 flex-row flex-wrap items-center justify-between gap-2 px-3 pt-3">
      <h3 id="people-results-title" class="text-sm font-semibold">Results</h3>
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
