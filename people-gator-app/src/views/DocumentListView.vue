<script setup lang="ts">
import { computed } from 'vue'
import DocumentPageGroup from '@/components/custom/DocumentPageGroup.vue'
import DocumentListSearchBar from '@/components/custom/DocumentListSearchBar.vue'
import { Button } from '@/components/ui/button'
import { useDocumentList } from '@/viewmodels/document-list'
import { useDocumentFilters } from '@/viewmodels/document-filters'
const { searchTerm, filters } = useDocumentFilters()
const {
  documents,
  resultCount,
  filterError,
  error,
  isLoading,
  hasNextPage,
  isFetchingNextPage,
  loadMore,
  retry,
} = useDocumentList(searchTerm, filters)
const filtered = computed(
  () =>
    searchTerm.value.trim() ||
    Object.entries(filters.value).some(([key, value]) =>
      Array.isArray(value) ? value.length : key === 'unassigned' ? value !== 'all' : !!value,
    ),
)
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
      v-model:filters="filters"
      :result-count="resultCount"
      :filter-error="filterError"
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
      <Button type="button" variant="outline" class="mt-2" @click="retry()">Retry documents</Button>
    </div>
    <p
      v-else-if="!isLoading && !filterError && documents.length === 0"
      class="py-10 text-center text-sm text-muted-foreground"
    >
      {{
        filtered
          ? 'No documents match your search and filters.'
          : 'No documents have been registered yet.'
      }}
    </p>
    <div v-if="hasNextPage && !error" class="flex justify-center pt-6">
      <Button type="button" variant="outline" :disabled="isFetchingNextPage" @click="loadMore()">{{
        isFetchingNextPage ? 'Loading documents…' : 'Load more documents'
      }}</Button>
    </div>
    <footer class="pb-4 pt-6">
      <p class="text-center text-sm text-muted-foreground">PeopleGator</p>
    </footer>
  </main>
</template>
