<script setup lang="ts">
import { useAutomaticPagination } from '@/composables/automatic-pagination'
import { relatedQuery, useSharedFilters, queryValues } from '@/viewmodels/shared-filters'
import { useDocumentScopeResolution } from '@/viewmodels/document-scope'
import { useRoute, useRouter } from 'vue-router'
import { computed, ref, watch } from 'vue'
import DocumentCard from '@/components/custom/DocumentCard.vue'
import DocumentCardSkeleton from '@/components/custom/DocumentCardSkeleton.vue'
import DocumentSearchBar from '@/components/custom/DocumentSearchBar.vue'
import { Button } from '@/components/ui/button'
import Separator from '@/components/ui/separator/Separator.vue'
import { useDocumentSearch } from '@/viewmodels/document-search'
import { normalizePageContentFilter } from '@/viewmodels/assignment'
import { useSourceLabels } from '@/query/people-filter-options'
import { DEFAULT_SORT_KEYS, useRouteSort } from '@/lib/sorting'
import {
  PAGE_BROWSE_DEFAULT,
  PAGE_SORTS,
  RELEVANCE,
  scoredOptions,
} from '@/viewmodels/sort-options'

const route = useRoute()
const router = useRouter()
const shared = useSharedFilters()
const scope = useDocumentScopeResolution()
const documentNames = useSourceLabels('document', () => shared.filters.value.documentIds)
const scopeError = scope.error
const unregisteredLabels = computed(() =>
  Object.fromEntries(scope.unregistered.value.map((id) => [id, `${id} (not registered)`])),
)
const heading = computed(() => {
  const { documentIds, libraries } = shared.filters.value
  if (documentIds.length === 1 || queryValues(route.query.archive_document).length)
    return 'Document pages'
  return libraries.length ? 'Library scans' : 'Browse scans'
})
const subtitle = computed(() => {
  const { documentIds, libraries } = shared.filters.value
  if (documentIds.length === 1) {
    const id = documentIds[0]!
    return documentNames.labels.value[id] ?? unregisteredLabels.value[id] ?? ''
  }
  return scope.unregistered.value.length
    ? scope.unregistered.value.join(', ')
    : libraries.join(', ')
})

const resultsPerPage = 12
const searchTerm = ref(typeof route.query.q === 'string' ? route.query.q : '')
const assignment = ref(normalizePageContentFilter(route.query.assignment))
const searching = computed(() => Boolean(searchTerm.value.trim()))
const sortOptions = computed(() => scoredOptions(PAGE_SORTS, searching.value))
const sort = useRouteSort(DEFAULT_SORT_KEYS, sortOptions, () =>
  searching.value ? RELEVANCE : PAGE_BROWSE_DEFAULT,
)
const {
  cards,
  error,
  isFetching,
  hasNextPage,
  isFetchingNextPage,
  isLoading,
  loadMore,
  resultCount,
} = useDocumentSearch(
  searchTerm,
  assignment,
  resultsPerPage,
  scope.apply(shared.params),
  computed(() => !shared.error.value && !scope.resolving.value && !scope.error.value),
  sort,
)

watch(
  () => route.query,
  (query) => {
    searchTerm.value = typeof query.q === 'string' ? query.q : ''
    assignment.value = normalizePageContentFilter(query.assignment)
  },
)

function updateSearch() {
  void router.replace({
    name: 'document-search',
    query: {
      ...route.query,
      cursor: undefined,
      q: searchTerm.value || undefined,
      assignment: assignment.value !== 'all' ? assignment.value : undefined,
    },
  })
}
const listEnd = ref<HTMLElement | null>(null)
useAutomaticPagination({
  target: listEnd,
  hasNextPage,
  isFetching,
  error,
  enabled: computed(() => !shared.error.value && !scope.resolving.value && !scope.error.value),
  loadMore,
})
</script>

<template>
  <main class="mx-auto w-full max-w-6xl md:px-4 px-2">
    <header class="pt-6 pb-4">
      <small class="font-semibold uppercase text-secondary">Scans index</small>
      <h1>{{ heading }}</h1>
      <p v-if="subtitle" class="mt-1 truncate text-sm text-muted-foreground" :title="subtitle">
        {{ subtitle }}
      </p>
    </header>

    <DocumentSearchBar
      v-model:search-term="searchTerm"
      v-model:assignment="assignment"
      v-model:sort="sort"
      :sort-options="sortOptions"
      :document-labels="unregisteredLabels"
      :result-count="resultCount"
      :has-more-results="hasNextPage"
      @update:search-term="updateSearch()"
      @update:assignment="updateSearch()"
    />
    <p v-if="scopeError" role="alert">
      Could not resolve the document scope.
      <Button variant="link" @click="scope.retry()">Retry</Button>
    </p>
    <section class="stable-search-results pt-6" aria-live="polite">
      <h2 class="mb-4">Search Results</h2>
      <Separator orientation="horizontal" />
      <div class="pt-6 grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        <RouterLink
          v-for="result in cards"
          :key="result.sourceId"
          class="group"
          :to="{
            name: 'document-page',
            query: relatedQuery(route),
            params: {
              libraryId: result.library,
              documentId: result.documentId,
              pageId: result.pageId,
            },
          }"
        >
          <DocumentCard
            :library="result.library"
            :document-uuid="result.documentId"
            :page-uuid="result.pageId"
            :names="result.names"
            :thumbnail-url="result.thumbnailUrl"
            :thumbnail-loading="result.thumbnailLoading"
          />
        </RouterLink>
        <DocumentCardSkeleton
          v-for="index in isLoading || isFetchingNextPage ? 4 : 0"
          :key="`loading-${index}`"
        />
      </div>
      <p v-if="error" class="py-10 text-center text-sm text-destructive">Could not load scans.</p>
      <p
        v-else-if="!isLoading && cards.length === 0"
        class="py-10 text-center text-sm text-muted-foreground"
      >
        No scans match this search.
      </p>
      <div ref="listEnd" class="h-px" aria-hidden="true" />
    </section>

    <div v-if="hasNextPage || isFetchingNextPage" class="flex justify-center pt-6">
      <Button type="button" variant="outline" :disabled="isFetching" @click="loadMore()">
        {{ isFetchingNextPage ? 'Loading scans…' : 'Load more scans' }}
      </Button>
    </div>

    <footer class="pt-6 pb-4">
      <p class="text-center text-sm text-muted-foreground">PeopleGator</p>
    </footer>
  </main>
</template>
