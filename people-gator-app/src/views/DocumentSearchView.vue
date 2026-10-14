<script setup lang="ts">
import { useLinkStateFilter } from '@/composables/link-state-filter'
import { useRoute, useRouter } from 'vue-router'
import { computed, ref, watch } from 'vue'
import DocumentCard from '@/components/custom/DocumentCard.vue'
import DocumentCardSkeleton from '@/components/custom/DocumentCardSkeleton.vue'
import DocumentSearchBar from '@/components/custom/DocumentSearchBar.vue'
import { Button } from '@/components/ui/button'
import Separator from '@/components/ui/separator/Separator.vue'
import { useDocumentSearch } from '@/viewmodels/document-search'
import { normalizePageContentFilter } from '@/viewmodels/assignment'

const linkStates = useLinkStateFilter()
const route = useRoute()
const router = useRouter()

const scope = computed(() => ({
  library: typeof route.query.library === 'string' ? route.query.library : undefined,
  documentId: typeof route.query.document === 'string' ? route.query.document : undefined,
}))

const resultsPerPage = 12
const searchTerm = ref(typeof route.query.q === 'string' ? route.query.q : '')
const assignment = ref(normalizePageContentFilter(route.query.assignment))
const { cards, error, hasNextPage, isFetchingNextPage, isLoading, loadMore, resultCount } =
  useDocumentSearch(searchTerm, assignment, resultsPerPage, scope, linkStates)

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
      ...(linkStates.value.length && { link_state: linkStates.value }),
      ...(scope.value.library && { library: scope.value.library }),
      ...(scope.value.documentId && { document: scope.value.documentId }),
      ...(searchTerm.value && { q: searchTerm.value }),
      ...(assignment.value !== 'all' && { assignment: assignment.value }),
    },
  })
}
function removeScope(key: 'library' | 'document') {
  void router.push({ query: { ...route.query, [key]: undefined } })
}
function clearFilters() {
  void router.push({
    name: 'document-search',
    query: searchTerm.value ? { q: searchTerm.value } : {},
  })
}
</script>

<template>
  <main class="mx-auto w-full max-w-6xl md:px-4 px-2">
    <header class="pt-6 pb-4">
      <small class="font-semibold uppercase text-secondary">Scans index</small>
      <h1>
        {{ scope.documentId ? 'Document pages' : scope.library ? 'Library scans' : 'Browse scans' }}
      </h1>
      <p
        v-if="scope.library"
        class="mt-1 truncate text-sm text-muted-foreground"
        :title="[scope.library, scope.documentId].filter(Boolean).join(' / ')"
      >
        {{ scope.library }}<span v-if="scope.documentId"> / {{ scope.documentId }}</span>
      </p>
    </header>

    <DocumentSearchBar
      v-model:link-states="linkStates"
      v-model:search-term="searchTerm"
      v-model:assignment="assignment"
      :library="scope.library"
      :document-id="scope.documentId"
      @remove-scope="removeScope"
      @clear-filters="clearFilters"
      :result-count="resultCount"
      :has-more-results="hasNextPage"
      @update:search-term="updateSearch()"
      @update:assignment="updateSearch()"
    />
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
            query: { link_state: linkStates.length ? linkStates : undefined },
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
    </section>

    <div v-if="hasNextPage || isFetchingNextPage" class="flex justify-center pt-6">
      <Button type="button" variant="outline" :disabled="isFetchingNextPage" @click="loadMore()">
        {{ isFetchingNextPage ? 'Loading scans…' : 'Load more scans' }}
      </Button>
    </div>

    <footer class="pt-6 pb-4">
      <p class="text-center text-sm text-muted-foreground">PeopleGator</p>
    </footer>
  </main>
</template>
