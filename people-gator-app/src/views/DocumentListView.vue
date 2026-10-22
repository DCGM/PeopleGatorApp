<script setup lang="ts">
import { useAutomaticPagination } from '@/composables/automatic-pagination'
import { hasSharedFilters, useSharedFilters } from '@/viewmodels/shared-filters'
import { computed, ref } from 'vue'
import DocumentPageGroup from '@/components/custom/DocumentPageGroup.vue'
import DocumentListSearchBar from '@/components/custom/DocumentListSearchBar.vue'
import { Button } from '@/components/ui/button'
import { useDocumentList } from '@/viewmodels/document-list'
import { useDocumentFilters } from '@/viewmodels/document-filters'
import { DEFAULT_SORT_KEYS, useRouteSort } from '@/lib/sorting'
import {
  DOCUMENT_BROWSE_DEFAULT,
  DOCUMENT_SORTS,
  RELEVANCE,
  scoredOptions,
} from '@/viewmodels/sort-options'
const shared = useSharedFilters()
const { searchTerm, unassigned } = useDocumentFilters()
const searching = computed(() => Boolean(searchTerm.value.trim()))
const sortOptions = computed(() => scoredOptions(DOCUMENT_SORTS, searching.value))
const sort = useRouteSort(DEFAULT_SORT_KEYS, sortOptions, () =>
  searching.value ? RELEVANCE : DOCUMENT_BROWSE_DEFAULT,
)
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
  shared.params,
  unassigned,
  12,
  computed(() => !shared.error.value),
  sort,
)
const filtered = computed(
  () =>
    searchTerm.value.trim() || unassigned.value !== 'all' || hasSharedFilters(shared.filters.value),
)
const listEnd = ref<HTMLElement | null>(null)
useAutomaticPagination({
  target: listEnd,
  hasNextPage,
  isFetching,
  error,
  enabled: computed(() => !shared.error.value),
  loadMore,
})
</script>

<template>
  <main class="mx-auto w-full max-w-6xl px-2 md:px-4">
    <header class="pb-4 pt-6">
      <small class="font-semibold uppercase text-secondary">Documents index</small>
      <h1>Browse documents</h1>
      <p class="mt-2 text-sm text-muted-foreground">Registered documents and their page scans.</p>
    </header>
    <DocumentListSearchBar
      v-model:search-term="searchTerm"
      v-model:unassigned="unassigned"
      v-model:sort="sort"
      :sort-options="sortOptions"
      :result-count="resultCount"
    />
    <p v-if="searchTerm.trim()" class="mt-2 text-sm text-muted-foreground">
      Search reports a bounded set of ranked document candidates.
    </p>
    <section
      class="document-pages flex w-full min-w-0 flex-col gap-4 pt-4"
      aria-label="Registered documents"
      aria-live="polite"
    >
      <DocumentPageGroup
        v-for="document in documents"
        :key="document.source_id"
        :document="document"
      />
    </section>
    <p
      v-if="isLoading || isFetchingNextPage"
      class="py-6 text-center text-sm text-muted-foreground"
      role="status"
    >
      Loading documents…
    </p>
    <div v-if="error" class="py-6 text-center" role="alert">
      <p class="text-sm text-destructive">Could not load documents.</p>
      <Button type="button" variant="outline" class="mt-2" :disabled="isFetching" @click="retry()"
        >Retry documents</Button
      >
    </div>
    <p
      v-else-if="!isLoading && !shared.error.value && documents.length === 0"
      class="py-10 text-center text-sm text-muted-foreground"
    >
      {{
        filtered
          ? 'No documents match your search and filters.'
          : 'No documents have been registered yet.'
      }}
    </p>
    <div ref="listEnd" class="h-px" aria-hidden="true" />

    <div v-if="hasNextPage && !error" class="flex justify-center pt-6">
      <Button type="button" variant="outline" :disabled="isFetching" @click="loadMore()">{{
        isFetchingNextPage ? 'Loading documents…' : 'Load more documents'
      }}</Button>
    </div>
    <footer class="pb-4 pt-6">
      <p class="text-center text-sm text-muted-foreground">PeopleGator</p>
    </footer>
  </main>
</template>
