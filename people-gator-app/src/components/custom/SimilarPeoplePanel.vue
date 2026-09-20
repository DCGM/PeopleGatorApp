<script setup lang="ts">
import { ChevronsDown, ScanFace, Search, X } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { Face } from '@/components/custom/document-page.types'
import SelectedFaceItem from '@/components/custom/SelectedFaceItem.vue'
import SimilarPersonItem from '@/components/custom/SimilarPersonItem.vue'
import SimilarPersonItemSkeleton from '@/components/custom/SimilarPersonItemSkeleton.vue'
import type { SimilarPersonCandidate } from '@/components/custom/similar-people.types'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'
import { Item } from '@/components/ui/item'

const props = defineProps<{
  people: SimilarPersonCandidate[]
  selectedFace: Face | null
  viewedPersonId: string | null
  loading?: boolean
  assignmentPending?: boolean
}>()

const emit = defineEmits<{
  preview: [person: SimilarPersonCandidate]
  assign: [person: SimilarPersonCandidate]
  create: [person: SimilarPersonCandidate]
  unassign: []
}>()

const query = defineModel<string>('searchTerm', { default: '' })
const visiblePageCount = ref(1)
const resultsElement = ref<HTMLElement | null>(null)
const searchRegionElement = ref<HTMLElement | null>(null)
const loadMoreElement = ref<HTMLElement | null>(null)
const loadingMore = ref(false)

const mobilePageSize = 3
const minimumResultHeight = 120
const resultGap = 8
const isMobile = useMediaQuery('(max-width: 1023px)')
const resultsHeight = ref(0)
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
const hasMorePeople = computed(() => visiblePeople.value.length < props.people.length)

watch(query, () => {
  visiblePageCount.value = 1
})

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
        if (entry?.isIntersecting) loadMoreOnMobile()
      },
      { threshold: 0.75 },
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
  if (!hasMorePeople.value || loadingMore.value) return
  visiblePageCount.value += 1
}

function loadMoreOnMobile() {
  if (!isMobile.value || !hasMorePeople.value || loadingMore.value) return

  loadingMore.value = true
  loadMoreTimer = setTimeout(() => {
    visiblePageCount.value += 1
    loadingMore.value = false
    loadMoreTimer = undefined
  }, 150)
}

function createPerson(profile: { name: string; shortDescription?: string }) {
  const name = profile.name.trim()
  emit('create', {
    id: name
      .toLocaleLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, ''),
    name,
    shortDescription: profile.shortDescription,
    score: 100,
    nerMentions: 0,
    detections: 1,
    source: 'page',
  })
}

function focusSearch() {
  searchRegionElement.value?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  searchRegionElement.value?.querySelector<HTMLInputElement>('input')?.focus()
}

defineExpose({ focusSearch })
</script>

<template>
  <section
    class="flex min-h-0 flex-1 flex-col gap-5 border-t p-5"
    aria-label="Face identity assignment"
  >
    <div class="space-y-2" aria-live="polite">
      <p class="font-mono text-xs font-semibold uppercase text-secondary">Current face</p>
      <SelectedFaceItem
        v-if="props.selectedFace"
        :face="props.selectedFace"
        :assignment-pending="props.assignmentPending"
        @find-profile="focusSearch"
        @create-profile="createPerson"
        @unassign="emit('unassign')"
      />
      <div v-else class="flex items-start gap-2 border bg-muted/30 p-3 text-muted-foreground">
        <ScanFace class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <p class="text-sm">Choose a face in the gallery before assigning an identity.</p>
      </div>
    </div>

    <div ref="searchRegionElement" class="flex min-h-0 flex-1 flex-col gap-2">
      <p class="font-mono text-xs font-semibold uppercase text-secondary">
        {{ props.selectedFace?.personId ? 'Reassign to similar' : 'Assign to similar' }}
      </p>
      <InputGroup class="w-full">
        <InputGroupAddon align="inline-start">
          <Search aria-hidden="true" />
        </InputGroupAddon>
        <InputGroupInput
          v-model="query"
          placeholder="Search by name or alias"
          aria-label="Search people"
          :disabled="!props.selectedFace"
        />
        <InputGroupAddon align="inline-end">
          <InputGroupButton
            v-if="query"
            type="button"
            size="icon-sm"
            aria-label="Clear people search"
            @click="query = ''"
          >
            <X aria-hidden="true" />
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
      <div
        ref="resultsElement"
        class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1"
        aria-live="polite"
        :aria-busy="props.loading"
      >
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

        <div v-if="hasMorePeople" ref="loadMoreElement" class="shrink-0">
          <Item
            as="button"
            type="button"
            variant="outline"
            class="w-full justify-center gap-2 bg-card px-3 py-3 font-mono text-xs font-semibold uppercase text-accent hover:border-accent hover:bg-accent/10"
            :class="loadingMore && 'animate-pulse'"
            :disabled="loadingMore"
            @click="revealNextPage"
          >
            <ChevronsDown class="size-4" aria-hidden="true" />
            {{ loadingMore ? 'Loading more' : 'Load more people' }}
            <ChevronsDown class="size-4" aria-hidden="true" />
          </Item>
        </div>
      </div>
    </div>
  </section>
</template>
