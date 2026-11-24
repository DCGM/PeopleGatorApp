<script setup lang="ts">
import { ImageOff, Maximize2, Minimize2 } from '@lucide/vue'
import { useAutomaticPagination } from '@/composables/automatic-pagination'
import { computed, nextTick, ref, watch } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

import ArchiveLink from './ArchiveLink.vue'
import LoadableImage from '@/components/custom/LoadableImage.vue'
import { Toggle } from '@/components/ui/toggle'
import PagePosition from './PagePosition.vue'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { PageGalleryItem } from '@/viewmodels/document-page-gallery'
import type { PageSortField } from '@/client'
import SortControl from './SortControl.vue'
import VerificationBadge from './VerificationBadge.vue'
import VerificationProgress from './VerificationProgress.vue'
import type { SortOption, SortState } from '@/lib/sorting'

const props = defineProps<{
  items: PageGalleryItem[]
  documentName?: string | null
  pageNumber?: number | null
  documentPageCount?: number | null
  verifiedPageCount?: number | null
  selectedPersonId?: string | null
  selectedPersonName?: string | null
  documentUrl?: string
  totalCount: number | null
  loading?: boolean
  error?: boolean
  highlightError?: boolean
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  location: (item: PageGalleryItem) => RouteLocationRaw
  sortOptions?: SortOption<PageSortField>[]
}>()
const expanded = defineModel<boolean>('expanded', { default: false })
const personOnly = defineModel<boolean>('personOnly', { default: false })
const notVerifiedOnly = defineModel<boolean>('notVerifiedOnly', { default: false })
const sort = defineModel<SortState<PageSortField>>('sort')

const emit = defineEmits<{
  'load-more': []
  retry: []
  retryHighlights: []
}>()

const list = ref<HTMLElement | null>(null)
const sentinel = ref<HTMLElement | null>(null)
const anyVerified = computed(() => props.items.some((item) => item.verified))

watch(
  [list, expanded],
  async () => {
    await nextTick()
    scrollCurrentIntoView()
  },
  { flush: 'post' },
)

function itemName(item: PageGalleryItem) {
  return `Page ${item.pageId}${item.current ? ', current page' : ''}${item.verified ? ', verified' : ''}${item.matchesSelectedPerson ? `, ${props.selectedPersonName || 'selected person'} appears on this page` : ''}`
}

/** Scroll only the strip, never the window, so the scan stays where it is. */
function scrollCurrentIntoView() {
  void nextTick(() => {
    const current = list.value?.querySelector<HTMLElement>('[aria-current="page"]')
    const viewport = list.value?.closest<HTMLElement>('[data-slot="scroll-area-viewport"]')
    if (!current || !viewport) return
    const target = current.getBoundingClientRect()
    const bounds = viewport.getBoundingClientRect()
    if (expanded.value) {
      if (target.top >= bounds.top && target.bottom <= bounds.bottom) return
      viewport.scrollTo?.({ top: viewport.scrollTop + target.top - bounds.top })
    } else {
      if (target.left >= bounds.left && target.right <= bounds.right) return
      viewport.scrollTo?.({
        left: viewport.scrollLeft + target.left - bounds.left - (bounds.width - target.width) / 2,
      })
    }
  })
}

/** A plain up/down wheel over the collapsed strip scrolls it sideways. */
function scrollStripWithWheel(event: WheelEvent) {
  if (expanded.value || event.ctrlKey || Math.abs(event.deltaX) >= Math.abs(event.deltaY)) return
  const viewport = list.value?.closest<HTMLElement>('[data-slot="scroll-area-viewport"]')
  if (!viewport) return
  const unit = [1, 16, viewport.clientWidth][event.deltaMode] ?? 1
  const delta = event.deltaY * unit
  const max = viewport.scrollWidth - viewport.clientWidth
  // At either end the wheel passes on, so the page can still scroll.
  if ((delta < 0 && viewport.scrollLeft <= 0) || (delta > 0 && viewport.scrollLeft >= max - 1))
    return
  event.preventDefault()
  viewport.scrollLeft += delta
}

watch(() => props.items.find((item) => item.current)?.pageId, scrollCurrentIntoView, {
  immediate: true,
})

// Recheck the visible end after every batch and when changing scroll direction.
useAutomaticPagination({
  target: sentinel,
  hasNextPage: () => Boolean(props.hasNextPage),
  isFetching: () => Boolean(props.loading || props.isFetchingNextPage),
  error: () => props.error,
  enabled: () => true,
  resetKey: expanded,
  loadMore: async () => {
    emit('load-more')
  },
})
</script>

<template>
  <nav
    class="document-page-gallery min-w-0 bg-background"
    :class="expanded && 'flex flex-col overflow-hidden'"
    :data-expanded="expanded || undefined"
    aria-label="Document pages"
    @keydown.stop
  >
    <div class="px-3 pt-2 sm:px-5" :class="expanded && 'flex min-h-0 flex-1 flex-col'">
      <div class="flex shrink-0 items-start gap-2">
        <div class="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 pb-1">
          <div class="flex min-h-7 min-w-0 flex-[1_1_12rem] items-center gap-2">
            <VerificationProgress
              v-if="verifiedPageCount != null && documentPageCount != null"
              :verified="verifiedPageCount"
              :total="documentPageCount"
              hide-count
            />
            <h2
              id="document-pages-title"
              class="min-w-0 truncate font-mono text-xs font-semibold text-secondary"
              :title="props.documentName || 'Document pages'"
            >
              {{ props.documentName || 'Document pages' }}
            </h2>
            <template v-if="documentUrl">
              <span aria-hidden="true">·</span>
              <ArchiveLink :url="documentUrl" kind="document" />
            </template>
            <span aria-hidden="true">·</span>
            <PagePosition
              class="shrink-0"
              :number="pageNumber"
              :total="documentPageCount ?? (personOnly || notVerifiedOnly ? undefined : totalCount)"
            />
          </div>
          <div class="flex min-w-0 max-w-full flex-wrap items-center gap-2">
            <Toggle
              :model-value="personOnly && Boolean(selectedPersonId)"
              variant="outline"
              size="sm"
              class="min-w-0 max-w-28 sm:max-w-36"
              :disabled="!selectedPersonId"
              :aria-label="
                selectedPersonId
                  ? `${selectedPersonName || 'Selected person'} only`
                  : 'Select a person in the right panel to filter pages'
              "
              :title="
                selectedPersonId
                  ? `${selectedPersonName || 'Selected person'} only`
                  : 'Select a person in the right panel to filter pages'
              "
              @update:model-value="personOnly = $event"
              ><span class="truncate">{{
                selectedPersonId ? `${selectedPersonName || 'Selected person'} only` : 'Person only'
              }}</span></Toggle
            >
            <Toggle v-model="notVerifiedOnly" variant="outline" size="sm">
              Not verified only
            </Toggle>
            <div v-if="sort && sortOptions" class="min-w-0 max-w-full sm:max-w-44">
              <SortControl
                v-model="sort"
                :options="sortOptions"
                label="Sort pages"
                size="sm"
                compact-on-mobile
              />
            </div>
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          class="shrink-0"
          :aria-label="expanded ? 'Collapse pages' : 'Expand pages'"
          :aria-expanded="expanded"
          aria-controls="document-pages-list"
          :title="expanded ? 'Collapse pages' : 'Expand pages'"
          @click="expanded = !expanded"
          ><Minimize2 v-if="expanded" aria-hidden="true" /><Maximize2 v-else aria-hidden="true"
        /></Button>
      </div>
      <div v-if="props.error" class="flex flex-wrap items-center gap-2 py-3" role="alert">
        <p class="text-sm text-destructive">Could not load document pages.</p>
        <Button type="button" variant="outline" size="sm" @click="emit('retry')">
          Retry pages
        </Button>
      </div>
      <p
        v-else-if="
          !props.loading &&
          (documentPageCount === 1 ||
            (documentPageCount == null &&
              !personOnly &&
              !notVerifiedOnly &&
              props.totalCount === 1))
        "
        class="sr-only"
        role="status"
      >
        This document has one registered page.
      </p>
      <div v-if="highlightError" class="flex items-center gap-2" role="alert">
        Could not check person matches.
        <Button variant="ghost" size="sm" @click="emit('retryHighlights')">Retry</Button>
      </div>
      <!-- Reka disables both scroll axes when either scrollbar unmounts. Give
           each orientation its own root so the old bar cannot disable the new one. -->
      <ScrollArea
        :key="expanded ? 'grid' : 'strip'"
        type="always"
        :orientation="expanded ? 'vertical' : 'horizontal'"
        class="w-full"
        :class="expanded && 'min-h-0 flex-1'"
        :viewport-props="{
          tabindex: 0,
          'aria-label': expanded ? 'Document pages grid' : 'Document pages strip',
        }"
        @wheel="scrollStripWithWheel"
      >
        <ol
          id="document-pages-list"
          ref="list"
          class="items-start gap-2 pb-4 pt-2"
          :class="
            expanded
              ? 'grid grid-cols-[repeat(auto-fill,minmax(min(100%,6rem),1fr))] w-full pl-1 pr-3'
              : 'flex min-h-32 sm:min-h-36 w-max min-w-full px-1'
          "
        >
          <li
            v-if="!props.loading && !props.error && props.totalCount === 0"
            role="status"
            :class="expanded && 'col-span-full'"
          >
            No matching pages.
          </li>
          <li
            v-for="item in props.items"
            :key="item.sourceId"
            :class="expanded ? 'min-w-0' : 'w-20 shrink-0'"
          >
            <RouterLink
              :to="props.location(item)"
              class="group flex flex-col items-center gap-1 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              :aria-label="itemName(item)"
              :aria-current="item.current ? 'page' : undefined"
              :title="`Page ${item.pageId}`"
              :data-current="item.current || undefined"
            >
              <!-- Badge sits above the page; the row is reserved so thumbnails stay aligned. -->
              <div v-if="anyVerified" class="flex h-5 w-full items-end">
                <VerificationBadge
                  v-if="item.verified"
                  state="verified"
                  class="max-w-full"
                  aria-hidden="true"
                />
              </div>
              <div
                data-page-thumbnail
                :data-person-match="item.matchesSelectedPerson || undefined"
                :aria-busy="item.matchesSelectedPerson === null && !highlightError"
                class="relative aspect-[8/11] w-full rounded-md"
                :class="
                  item.current
                    ? 'border-2 border-secondary ring-2 ring-secondary ring-offset-2'
                    : item.matchesSelectedPerson
                      ? 'border-0 p-0.5 ring-2 ring-secondary'
                      : 'border-2 border-border group-hover:border-accent'
                "
              >
                <LoadableImage
                  :src="item.thumbnailUrl"
                  :loading="item.thumbnailLoading"
                  alt=""
                  class="h-full w-full rounded-md bg-muted"
                  image-class="object-cover"
                >
                  <template #fallback>
                    <span
                      class="flex size-full flex-col items-center justify-center gap-1 text-muted-foreground"
                    >
                      <ImageOff class="size-4" aria-hidden="true" />
                      <span class="text-[0.625rem] leading-none">No preview</span>
                    </span>
                  </template>
                </LoadableImage>
              </div>
              <span
                class="w-full truncate text-center font-mono text-[0.6875rem] leading-tight"
                :class="item.current ? 'font-semibold text-foreground' : 'text-muted-foreground'"
              >
                {{ item.label }}
              </span>
            </RouterLink>
          </li>
          <li
            v-for="index in props.loading || props.isFetchingNextPage ? 3 : 0"
            :key="`loading-${index}`"
            class="aspect-[8/11] shrink-0 animate-pulse rounded-md border bg-muted"
            :class="expanded ? 'w-full' : 'w-20'"
            aria-hidden="true"
          />
          <li
            v-if="props.hasNextPage && !props.error"
            class="flex shrink-0 self-center"
            :class="expanded && 'col-span-full justify-center'"
          >
            <span ref="sentinel" class="block h-px w-px" aria-hidden="true" />
            <Button
              type="button"
              variant="outline"
              size="sm"
              :disabled="props.isFetchingNextPage"
              @click="emit('load-more')"
            >
              {{ props.isFetchingNextPage ? 'Loading pages…' : 'More pages' }}
            </Button>
          </li>
        </ol>
        <p v-if="props.loading" class="sr-only" role="status">Loading document pages…</p>
      </ScrollArea>
    </div>
  </nav>
</template>
