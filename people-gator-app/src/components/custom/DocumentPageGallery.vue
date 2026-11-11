<script setup lang="ts">
import { ImageOff } from '@lucide/vue'
import { useIntersectionObserver } from '@vueuse/core'
import { nextTick, ref, watch } from 'vue'
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
import type { SortOption, SortState } from '@/lib/sorting'

const props = defineProps<{
  items: PageGalleryItem[]
  documentName?: string | null
  pageNumber?: number | null
  documentPageCount?: number | null
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
const personOnly = defineModel<boolean>('personOnly', { default: false })
const sort = defineModel<SortState<PageSortField>>('sort')

const emit = defineEmits<{
  'load-more': []
  retry: []
  retryHighlights: []
}>()

const list = ref<HTMLElement | null>(null)
const sentinel = ref<HTMLElement | null>(null)

function itemName(item: PageGalleryItem) {
  return `Page ${item.pageId}${item.current ? ', current page' : ''}${item.matchesSelectedPerson ? `, ${props.selectedPersonName || 'selected person'} appears on this page` : ''}`
}

/** Scroll only the strip, never the window, so the scan stays where it is. */
function scrollCurrentIntoView() {
  void nextTick(() => {
    const current = list.value?.querySelector<HTMLElement>('[aria-current="page"]')
    const viewport = list.value?.closest<HTMLElement>('[data-slot="scroll-area-viewport"]')
    if (!current || !viewport) return
    const target = current.getBoundingClientRect()
    const bounds = viewport.getBoundingClientRect()
    if (target.left >= bounds.left && target.right <= bounds.right) return
    viewport.scrollTo?.({
      left: viewport.scrollLeft + target.left - bounds.left - (bounds.width - target.width) / 2,
    })
  })
}

watch(() => props.items.find((item) => item.current)?.pageId, scrollCurrentIntoView, {
  immediate: true,
})

// Reaching the end of the strip loads the next batch; the button covers keyboard use.
useIntersectionObserver(sentinel, ([entry]) => {
  if (entry?.isIntersecting && props.hasNextPage && !props.isFetchingNextPage && !props.error)
    emit('load-more')
})
</script>

<template>
  <nav
    class="document-page-gallery min-w-0 bg-background"
    aria-label="Document pages"
    @keydown.stop
  >
    <div class="px-3 pt-2 sm:px-5">
      <div class="w-full overflow-x-auto">
        <div
          class="gallery-header flex w-full min-w-[22rem] sm:min-w-[32rem] flex-row flex-nowrap items-center gap-2 pb-1"
        >
          <div class="flex min-w-0 items-center gap-2">
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
              :total="documentPageCount ?? (personOnly ? undefined : totalCount)"
            />
          </div>
          <div class="ml-auto flex shrink-0 flex-row flex-nowrap items-center gap-2">
            <Toggle
              :model-value="personOnly && Boolean(selectedPersonId)"
              variant="outline"
              size="sm"
              class="w-28 min-w-0 sm:w-36"
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
            <div v-if="sort && sortOptions" class="w-20 min-w-0 sm:w-44">
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
            (documentPageCount == null && !personOnly && props.totalCount === 1))
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
      <ScrollArea type="always" orientation="horizontal" class="w-full">
        <ol
          ref="list"
          class="flex min-h-32 sm:min-h-36 w-max min-w-full items-start gap-2 px-1 pb-4 pt-2"
        >
          <li v-if="!props.loading && !props.error && props.totalCount === 0" role="status">
            No matching pages.
          </li>
          <li v-for="item in props.items" :key="item.sourceId" class="w-14 shrink-0 sm:w-16">
            <RouterLink
              :to="props.location(item)"
              class="group flex flex-col items-center gap-1 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              :aria-label="itemName(item)"
              :aria-current="item.current ? 'page' : undefined"
              :title="`Page ${item.pageId}`"
              :data-current="item.current || undefined"
            >
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
            class="aspect-[8/11] w-14 shrink-0 animate-pulse rounded-md border bg-muted sm:w-16"
            aria-hidden="true"
          />
          <li v-if="props.hasNextPage && !props.error" class="flex shrink-0 self-center">
            <span ref="sentinel" class="block h-full w-px" aria-hidden="true" />
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
