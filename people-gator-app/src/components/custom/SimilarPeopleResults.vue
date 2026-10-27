<script setup lang="ts">
import { ChevronsDown } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import SimilarPersonItem from '@/components/custom/SimilarPersonItem.vue'
import SimilarPersonItemSkeleton from '@/components/custom/SimilarPersonItemSkeleton.vue'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { Face } from '@/viewmodels/document-workspace.types'
import type { SimilarPersonCandidate } from '@/viewmodels/similar-people.types'

const props = defineProps<{
  people: SimilarPersonCandidate[]
  selectedFace: Face | null
  viewedPersonId: string | null
  loading?: boolean
  assignmentPending?: boolean
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  searchTerm?: string
}>()

const emit = defineEmits<{
  preview: [person: SimilarPersonCandidate]
  assign: [person: SimilarPersonCandidate]
  loadMore: []
}>()

const visiblePageCount = ref(1)
const resultsElement = ref<HTMLElement | null>(null)
const loadMoreElement = ref<HTMLElement | null>(null)
const localLoadingMore = ref(false)
const resultsHeight = ref(0)
const isMobile = useMediaQuery('(max-width: 1023px)')
const mobilePageSize = 3
const minimumResultHeight = 120
const resultGap = 8
let resultsResizeObserver: ResizeObserver | undefined
let loadMoreObserver: IntersectionObserver | undefined
let loadMoreTimer: ReturnType<typeof setTimeout> | undefined

const pageSize = computed(() => {
  if (isMobile.value || resultsHeight.value === 0) return mobilePageSize
  return Math.max(
    1,
    Math.floor((resultsHeight.value + resultGap) / (minimumResultHeight + resultGap)),
  )
})
const visiblePeople = computed(() => props.people.slice(0, visiblePageCount.value * pageSize.value))
const hasMoreLoadedPeople = computed(() => visiblePeople.value.length < props.people.length)
const hasMorePeople = computed(() => hasMoreLoadedPeople.value || Boolean(props.hasNextPage))
const loadingMore = computed(() => localLoadingMore.value || Boolean(props.isFetchingNextPage))

watch(
  () => props.searchTerm,
  () => {
    visiblePageCount.value = 1
  },
)

watch(
  [() => props.viewedPersonId, () => props.people],
  async ([personId]) => {
    if (!personId) return
    const personIndex = props.people.findIndex((person) => person.id === personId)
    if (personIndex < 0) return

    visiblePageCount.value = Math.max(
      visiblePageCount.value,
      Math.ceil((personIndex + 1) / pageSize.value),
    )
    await nextTick()
    const selected = resultsElement.value?.querySelector<HTMLElement>('[data-person-viewed="true"]')
    const viewport = resultsElement.value?.querySelector<HTMLElement>(
      '[data-slot="scroll-area-viewport"]',
    )
    if (selected && viewport) {
      const item = selected.getBoundingClientRect()
      const bounds = viewport.getBoundingClientRect()
      const top =
        item.top < bounds.top ? item.top - bounds.top : Math.max(0, item.bottom - bounds.bottom)
      // Keep the candidate visible without scrolling the scan's action panel offscreen.
      viewport.scrollBy?.({ top, behavior: 'smooth' })
    }
  },
  { immediate: true, flush: 'post' },
)

watch(loadMoreElement, (element, previousElement) => {
  if (previousElement) loadMoreObserver?.unobserve(previousElement)
  if (element) loadMoreObserver?.observe(element)
})

onMounted(async () => {
  await nextTick()
  if (resultsElement.value) {
    resultsHeight.value = resultsElement.value.getBoundingClientRect().height
    if (typeof ResizeObserver !== 'undefined') {
      resultsResizeObserver = new ResizeObserver(([entry]) => {
        if (entry) resultsHeight.value = entry.contentRect.height
      })
      resultsResizeObserver.observe(resultsElement.value)
    }
  }

  if (typeof IntersectionObserver !== 'undefined') {
    loadMoreObserver = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) loadNextPage()
      },
      {
        root: resultsElement.value?.querySelector('[data-slot="scroll-area-viewport"]'),
        threshold: 0.75,
      },
    )
    if (loadMoreElement.value) loadMoreObserver.observe(loadMoreElement.value)
  }
})

onBeforeUnmount(() => {
  resultsResizeObserver?.disconnect()
  loadMoreObserver?.disconnect()
  if (loadMoreTimer) clearTimeout(loadMoreTimer)
})

function revealNextPage() {
  if (loadingMore.value) return
  if (hasMoreLoadedPeople.value) {
    visiblePageCount.value += 1
    return
  }
  if (!props.hasNextPage) return

  visiblePageCount.value += 1
  emit('loadMore')
}

function loadNextPage() {
  if (!hasMorePeople.value || loadingMore.value) return

  localLoadingMore.value = true
  loadMoreTimer = setTimeout(() => {
    localLoadingMore.value = false
    loadMoreTimer = undefined
    revealNextPage()
  }, 150)
}
</script>

<template>
  <section ref="resultsElement" aria-label="Similar people results">
    <ScrollArea type="always" class="size-full" aria-live="polite" :aria-busy="props.loading">
      <div class="flex min-h-full flex-col gap-2 pr-3">
        <SimilarPersonItem
          v-for="person in visiblePeople"
          :key="person.id"
          :person="person"
          class="shrink-0"
          :assigned="props.selectedFace?.personId === person.id"
          :reassignment="
            Boolean(props.selectedFace?.personId && props.selectedFace.personId !== person.id)
          "
          :assignment-disabled="!props.selectedFace"
          :assignment-pending="props.assignmentPending"
          :viewed="viewedPersonId === person.id"
          :data-person-viewed="viewedPersonId === person.id"
          @preview="emit('preview', $event)"
          @assign="emit('assign', $event)"
        />
        <SimilarPersonItemSkeleton
          v-if="props.loading && visiblePeople.length === 0"
          class="shrink-0"
        />

        <p
          v-if="props.people.length === 0 && !props.loading"
          class="flex flex-1 items-center justify-center py-6 text-center text-sm text-muted-foreground"
        >
          No matching people. Add a new identity instead.
        </p>

        <div v-if="hasMorePeople" ref="loadMoreElement" class="shrink-0 text-center">
          <Button
            type="button"
            variant="link"
            size="sm"
            class="font-mono text-xs font-semibold uppercase text-accent"
            :class="loadingMore && 'animate-pulse'"
            :disabled="loadingMore"
            @click="revealNextPage"
          >
            <ChevronsDown class="size-4" aria-hidden="true" />
            {{ loadingMore ? 'Loading more' : 'Load more people' }}
          </Button>
        </div>
      </div>
    </ScrollArea>
  </section>
</template>
