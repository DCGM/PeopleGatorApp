<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { ref } from 'vue'
import DocumentCard from '@/components/custom/DocumentCard.vue'
import DocumentCardSkeleton from '@/components/custom/DocumentCardSkeleton.vue'
import DocumentSearchBar from '@/components/custom/DocumentSearchBar.vue'
import { Button } from '@/components/ui/button'
import Separator from '@/components/ui/separator/Separator.vue'
import { useDocumentSearch } from '@/query/document-search'

const route = useRoute()
const router = useRouter()

const resultsPerPage = 12
const searchTerm = ref(typeof route.query.q === 'string' ? route.query.q : '')
const { cards, error, hasNextPage, isFetchingNextPage, isLoading, loadMore, resultCount } =
  useDocumentSearch(searchTerm, resultsPerPage)

function updateSearch() {
  void router.push({
    name: 'document-search',
    query: {
      ...(searchTerm.value && { q: searchTerm.value }),
    },
  })
}
</script>

<template>
  <main class="mx-auto w-full max-w-6xl md:px-4 px-2">
    <header class="pt-6 pb-4">
      <small class="font-semibold uppercase text-secondary">Scans index</small>
      <h1>Browse scans</h1>
    </header>

    <DocumentSearchBar
      v-model:search-term="searchTerm"
      :result-count="resultCount"
      :has-more-results="hasNextPage"
      @update:search-term="updateSearch()"
    />
    <section class="pt-6" aria-live="polite">
      <h2 class="mb-4">Search Results</h2>
      <Separator orientation="horizontal" />
      <div class="pt-6 grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        <RouterLink
          v-for="result in cards"
          :key="result.sourceId"
          class="group"
          :to="{
            name: 'document-page',
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
