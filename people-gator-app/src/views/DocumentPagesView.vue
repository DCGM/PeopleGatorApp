<script setup lang="ts">
import { computed, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import ArchiveLink from '@/components/custom/ArchiveLink.vue'
import { Button } from '@/components/ui/button'
import { retryUnlessClientError } from '@/query/api'
import { documentTitle } from '@/viewmodels/document-list'
import {
  documentBrowseQuery,
  resolveDocumentEntry,
  type DocumentEntry,
} from '@/viewmodels/document-navigation'

const route = useRoute()
const router = useRouter()
const entry = computed<DocumentEntry>(() =>
  route.name === 'document-source'
    ? { sourceId: String(route.params.documentSourceId) }
    : { library: String(route.params.libraryId), documentId: String(route.params.documentId) },
)
const legacyLibrary = computed(() =>
  typeof route.query.library === 'string' ? route.query.library : undefined,
)
const result = useQuery({
  queryKey: computed(() => ['document-entry', entry.value, legacyLibrary.value]),
  queryFn: ({ signal }) => resolveDocumentEntry(entry.value, legacyLibrary.value, signal),
  retry: retryUnlessClientError,
})
const document = computed(() => result.data.value?.document)
watch(
  [result.data, () => route.fullPath],
  ([value]) => {
    if (!value?.page) return
    const page = value.page
    void router.replace({
      name: 'document-page',
      params: { libraryId: page.library, documentId: page.document_id, pageId: page.page_id },
      query: documentBrowseQuery(route.query),
    })
  },
  { immediate: true },
)
</script>

<template>
  <main class="mx-auto w-full max-w-6xl space-y-4 p-4 sm:p-6">
    <p v-if="result.isPending.value || result.data.value?.page" role="status">Opening document…</p>
    <template v-else-if="result.error.value">
      <p role="alert">Could not open this document.</p>
      <Button variant="outline" :disabled="result.isFetching.value" @click="result.refetch()"
        >Retry document</Button
      >
    </template>
    <template v-else-if="document">
      <header class="flex flex-wrap items-center gap-3">
        <h1>{{ documentTitle(document) }}</h1>
        <ArchiveLink :url="document.url" kind="document" />
      </header>
      <p role="status">No pages in this document.</p>
    </template>
    <p v-else role="alert">Document not found.</p>
    <Button variant="outline" as-child
      ><RouterLink :to="{ name: 'document-list' }">Documents</RouterLink></Button
    >
  </main>
</template>
