<script setup lang="ts">
import { useLinkStateFilter } from '@/composables/link-state-filter'
import EntityLinkStateFilter from '@/components/custom/EntityLinkStateFilter.vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import DocumentPageGroup from '@/components/custom/DocumentPageGroup.vue'
import { Button } from '@/components/ui/button'
import { useDocumentList } from '@/viewmodels/document-list'

const linkStates = useLinkStateFilter()
const route = useRoute()
const library = computed(() =>
  typeof route.query.library === 'string' ? route.query.library : undefined,
)
const { documents, error, isLoading, hasNextPage, isFetchingNextPage, loadMore, retry } =
  useDocumentList(library, 12, linkStates)
</script>

<template>
  <main class="mx-auto w-full max-w-6xl px-2 md:px-4">
    <header class="pb-4 pt-6">
      <small class="font-semibold uppercase text-secondary">Documents index</small>
      <h1>{{ library ? 'Library documents' : 'Browse documents' }}</h1>
      <p v-if="library" class="mt-1 break-all text-sm text-muted-foreground">{{ library }}</p>
      <p class="mt-2 text-sm text-muted-foreground">Registered documents and their page scans.</p>
      <EntityLinkStateFilter v-model="linkStates" class="mt-3" />
    </header>
    <section
      class="document-pages flex flex-wrap gap-4"
      aria-label="Registered documents"
      aria-live="polite"
    >
      <DocumentPageGroup
        v-for="document in documents"
        :key="`${document.library}/${document.document_id}`"
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
      v-else-if="!isLoading && documents.length === 0"
      class="py-10 text-center text-sm text-muted-foreground"
    >
      No documents have been registered{{ library ? ' in this library' : '' }} yet.
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

<style>
.document-pages > .scan-card {
  flex: 0 0 100%;
}
@media (min-width: 640px) {
  .document-pages > .scan-card {
    flex-basis: calc((100% - 1rem) / 2);
  }
}
@media (min-width: 768px) {
  .document-pages > .scan-card {
    flex-basis: calc((100% - 2rem) / 3);
  }
}
@media (min-width: 1024px) {
  .document-pages > .scan-card {
    flex-basis: calc((100% - 3rem) / 4);
  }
}
</style>
