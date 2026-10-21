<script setup lang="ts">
import { ImageOff } from '@lucide/vue'
import { useIntersectionObserver } from '@vueuse/core'
import { nextTick, ref, watch } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

import LoadableImage from '@/components/custom/LoadableImage.vue'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { PageGalleryItem } from '@/viewmodels/document-page-gallery'
import type { PageSortField } from '@/client'
import SortControl from './SortControl.vue'
import type { SortOption, SortState } from '@/lib/sorting'

const props = defineProps<{
  items: PageGalleryItem[]
  totalCount: number | null
  loading?: boolean
  error?: boolean
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  location: (item: PageGalleryItem) => RouteLocationRaw
  sortOptions?: SortOption<PageSortField>[]
}>()
const sort = defineModel<SortState<PageSortField>>('sort')

const emit = defineEmits<{
  'load-more': []
  retry: []
}>()

const list = ref<HTMLElement | null>(null)
const sentinel = ref<HTMLElement | null>(null)

function itemName(item: PageGalleryItem) {
  return `Page ${item.pageId}${item.current ? ', current page' : ''}`
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

watch(
  () => props.items.find((item) => item.current)?.pageId,
  scrollCurrentIntoView,
  { immediate: true },
)

// Reaching the end of the strip loads the next batch; the button covers keyboard use.
useIntersectionObserver(sentinel, ([entry]) => {
  if (entry?.isIntersecting && props.hasNextPage && !props.isFetchingNextPage && !props.error)
    emit('load-more')
})
</script>

<template>
  <nav
    class="document-page-gallery min-w-0 bg-background"
    aria-labelledby="document-pages-title"
    @keydown.stop
  >
    <div class="px-3 pt-2 sm:px-5">
      <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id="document-pages-title" class="font-mono text-xs font-semibold uppercase text-secondary">
          Document pages
          <span v-if="props.totalCount !== null" class="font-normal text-muted-foreground">
            · {{ props.totalCount }} {{ props.totalCount === 1 ? 'page' : 'pages' }}
          </span>
        </h2>
        <div class="flex flex-wrap items-center gap-2">
          <p id="document-pages-order" class="text-xs text-muted-foreground">
            Page IDs are not page numbers
          </p>
          <SortControl
            v-if="sort && sortOptions"
            v-model="sort"
            :options="sortOptions"
            label="Sort pages"
            size="sm"
          />
        </div>
      </div>
      <div v-if="props.error" class="flex flex-wrap items-center gap-2 py-3" role="alert">
        <p class="text-sm text-destructive">Could not load document pages.</p>
        <Button type="button" variant="outline" size="sm" @click="emit('retry')">
          Retry pages
        </Button>
      </div>
      <p
        v-else-if="!props.loading && props.totalCount === 1"
        class="sr-only"
        role="status"
      >
        This document has one registered page.
      </p>
      <ScrollArea type="always" orientation="horizontal" class="w-full">
        <ol
          ref="list"
          class="flex w-max items-start gap-2 px-1 pb-4 pt-2"
          aria-describedby="document-pages-order"
        >
          <li v-for="item in props.items" :key="item.sourceId" class="w-14 shrink-0 sm:w-16">
            <RouterLink
              :to="props.location(item)"
              class="group flex flex-col items-center gap-1 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              :aria-label="itemName(item)"
              :aria-current="item.current ? 'page' : undefined"
              :title="`Page ${item.pageId}`"
              :data-current="item.current || undefined"
            >
              <LoadableImage
                :src="item.thumbnailUrl"
                :loading="item.thumbnailLoading"
                alt=""
                class="aspect-[8/11] w-full rounded-md border-2 bg-muted transition-[border-color] group-hover:border-accent"
                :class="item.current ? 'border-secondary ring-2 ring-secondary ring-offset-2' : 'border-border'"
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
