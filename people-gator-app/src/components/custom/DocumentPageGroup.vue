<script setup lang="ts">
import EntityLinkStatistics from './EntityLinkStatistics.vue'
import { useLinkStateFilter } from '@/composables/link-state-filter'
import type { DocumentResponse } from '@/client'
import DocumentCard from '@/components/custom/DocumentCard.vue'
import DocumentCardSkeleton from '@/components/custom/DocumentCardSkeleton.vue'
import { Button } from '@/components/ui/button'
import { documentTitle, useDocumentGroup } from '@/viewmodels/document-list'

const linkStates = useLinkStateFilter()
const props = defineProps<{ document: DocumentResponse }>()
const { cards, totalCount, filteredCount, error, isLoading, hasNextPage, isFetchingNextPage, loadMore, retry } =
  useDocumentGroup(() => props.document, 12, linkStates)
</script>

<template>
  <!-- Multiple roots deliberately render directly into the shared flex container. -->
  <header class="document-heading w-full basis-full border-b pb-3 pt-4">
    <h2 class="break-words">{{ documentTitle(document) }}</h2>
    <p class="mt-1 break-all text-sm text-muted-foreground">
      {{ document.library }} · {{ document.document_id }}
    </p>
    <p v-if="totalCount !== null" class="mt-1 text-sm text-muted-foreground">
      <template v-if="linkStates.length">{{ filteredCount }} matching of </template>{{ totalCount }} registered {{ totalCount === 1 ? 'page' : 'pages' }}
    </p>
    <EntityLinkStatistics :stats="document.entity_link_stats" unassigned class="mt-2" />
  </header>
  <RouterLink
    v-for="card in cards"
    :key="card.sourceId"
    class="scan-card group min-w-0"
    :to="{
      name: 'document-page',
      query: { link_state: linkStates },
      params: { libraryId: card.library, documentId: card.documentId, pageId: card.pageId },
    }"
  >
    <DocumentCard
      :library="card.library"
      :document-uuid="card.documentId"
      :page-uuid="card.pageId"
      :names="card.names"
      :thumbnail-url="card.thumbnailUrl"
      :thumbnail-loading="card.thumbnailLoading"
    />
  </RouterLink>
  <DocumentCardSkeleton
    v-for="index in isLoading || isFetchingNextPage ? 4 : 0"
    :key="`loading-${index}`"
    class="scan-card min-w-0"
  />
  <div v-if="error" class="w-full basis-full py-4" role="alert">
    <p class="text-sm text-destructive">Could not load pages for this document.</p>
    <Button type="button" variant="outline" class="mt-2" @click="retry()">Retry pages</Button>
  </div>
  <p
    v-else-if="!isLoading && cards.length === 0"
    class="w-full basis-full py-4 text-sm text-muted-foreground"
  >
    {{ linkStates.length ? 'No pages match the selected link states.' : 'No pages have been registered for this document yet.' }}
  </p>
  <div v-if="hasNextPage && !error" class="flex w-full basis-full justify-center py-2">
    <Button
      type="button"
      variant="outline"
      :disabled="isFetchingNextPage"
      :aria-label="`Load more pages for ${documentTitle(document)}`"
      @click="loadMore()"
    >
      {{ isFetchingNextPage ? 'Loading pages…' : 'Load more pages' }}
    </Button>
  </div>
</template>
