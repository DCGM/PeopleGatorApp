<script setup lang="ts">
import { useDocumentCounts } from '@/viewmodels/document-counts'
import { useMediaQuery } from '@vueuse/core'
import { useAutomaticPagination } from '@/composables/automatic-pagination'
import { hasSharedFilters, useSharedFilters } from '@/viewmodels/shared-filters'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DocumentTable from '@/components/custom/DocumentTable.vue'
import { useDocumentColumnOrder, useDocumentColumns } from '@/viewmodels/document-table'
import DocumentListSearchBar from '@/components/custom/DocumentListSearchBar.vue'
import DocumentFilters from '@/components/custom/DocumentFilters.vue'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { useDocumentList } from '@/viewmodels/document-list'
import { useDocumentFilters, verificationQuery } from '@/viewmodels/document-filters'
import { DEFAULT_SORT_KEYS, useRouteSort } from '@/lib/sorting'
import {
  DOCUMENT_BROWSE_DEFAULT,
  DOCUMENT_SORTS,
  RELEVANCE,
  scoredOptions,
} from '@/viewmodels/sort-options'
const route = useRoute()
const router = useRouter()
const visibility = useDocumentColumns()
const columnOrder = useDocumentColumnOrder()
const shared = useSharedFilters()
const counts = useDocumentCounts()
// Filters sit in a sidebar from 1024px and in a drawer below that (#111).
const desktop = useMediaQuery('(min-width: 1024px)')
const filtersOpen = ref(false)
const { searchTerm, unassigned, verification } = useDocumentFilters()
const sourceParams = computed(() => ({
  ...shared.params.value,
  ...counts.params.value,
  ...verificationQuery(verification.value),
}))
const searching = computed(() => Boolean(searchTerm.value.trim()))
const sortOptions = computed(() => scoredOptions(DOCUMENT_SORTS, searching.value))
const sort = useRouteSort(
  DEFAULT_SORT_KEYS,
  sortOptions,
  () => (searching.value ? RELEVANCE : DOCUMENT_BROWSE_DEFAULT),
  'push',
  true,
)
const explicitSort = computed({
  get: () => (route.query.sort === sort.value.field ? sort.value : undefined),
  set: (value) => {
    if (value) sort.value = value
    else
      void router.push({
        query: { ...route.query, sort: undefined, dir: undefined, cursor: undefined },
      })
  },
})
const {
  documents,
  resultCount,
  error,
  isLoading,
  hasNextPage,
  isFetching,
  isFetchingNextPage,
  loadMore,
  retry,
} = useDocumentList(
  searchTerm,
  sourceParams,
  unassigned,
  12,
  computed(() => !shared.error.value && !counts.error.value),
  sort,
)
const filtered = computed(
  () =>
    counts.tags.value.length ||
    searchTerm.value.trim() ||
    unassigned.value !== 'all' ||
    verification.value !== 'all' ||
    hasSharedFilters(shared.filters.value),
)
const listEnd = ref<HTMLElement | null>(null)
useAutomaticPagination({
  target: listEnd,
  resetKey: computed(() => route.fullPath),
  hasNextPage,
  isFetching,
  error,
  enabled: computed(() => !shared.error.value && !counts.error.value),
  loadMore,
})
</script>

<template>
  <main class="mx-auto w-full min-w-0 px-2 pb-4 md:px-4 lg:flex lg:min-h-0 lg:flex-1 lg:flex-col">
    <header class="pb-2 pt-4 lg:shrink-0">
      <small class="font-semibold uppercase text-secondary">Documents index</small>
    </header>
    <div class="lg:flex lg:min-h-0 lg:flex-1 lg:gap-4">
      <aside
        v-if="desktop"
        class="w-60 shrink-0 overflow-y-auto pb-1"
        aria-label="Document filters"
      >
        <DocumentFilters tags />
      </aside>
      <div class="flex min-w-0 flex-col gap-2 lg:min-h-0 lg:flex-1">
        <div class="flex min-w-0 flex-col gap-2 lg:shrink-0">
          <DocumentListSearchBar
            v-model:search-term="searchTerm"
            v-model:sort="sort"
            v-model:filters-open="filtersOpen"
            :sort-options="sortOptions"
            :result-count="resultCount"
          />
          <p v-if="searchTerm.trim()" class="text-sm text-muted-foreground">
            Search reports a bounded set of ranked document candidates.
          </p>
        </div>
        <DocumentTable
          v-model:visibility="visibility"
          v-model:order="columnOrder"
          v-model:sort="explicitSort"
          :documents="documents"
          :loading-more="isFetchingNextPage"
          class="pt-2 lg:min-h-0 lg:flex-1"
        >
          <template #list-end>
            <div class="sticky left-0 w-max max-w-full px-4" data-slot="document-list-status">
              <p v-if="isLoading" class="py-6 text-sm text-muted-foreground" role="status">
                Loading documents…
              </p>
              <p v-if="isFetchingNextPage" class="sr-only" role="status">Loading more documents…</p>
              <div v-if="error" class="py-6" role="alert">
                <p class="text-sm text-destructive">Could not load documents.</p>
                <Button
                  type="button"
                  variant="outline"
                  class="mt-2"
                  :disabled="isFetching"
                  @click="retry()"
                  >Retry documents</Button
                >
              </div>
              <p
                v-else-if="
                  !isLoading && !shared.error.value && !counts.error.value && documents.length === 0
                "
                class="py-10 text-sm text-muted-foreground"
              >
                {{
                  filtered
                    ? 'No documents match your search and filters.'
                    : 'No documents have been registered yet.'
                }}
              </p>
            </div>
            <div ref="listEnd" class="sticky left-0 h-px w-px" aria-hidden="true" />
          </template>
        </DocumentTable>
      </div>
    </div>
    <Sheet v-if="!desktop" v-model:open="filtersOpen">
      <SheetContent side="left" class="overflow-y-auto" :aria-describedby="undefined">
        <SheetHeader><SheetTitle>Filters</SheetTitle></SheetHeader>
        <div class="px-4 pb-4"><DocumentFilters /></div>
      </SheetContent>
    </Sheet>
  </main>
</template>
