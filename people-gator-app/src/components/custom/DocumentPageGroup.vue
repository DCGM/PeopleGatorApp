<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpRight } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import EntityLinkStatistics from './EntityLinkStatistics.vue'
import { useLinkStateFilter } from '@/composables/link-state-filter'
import type { DocumentResponse } from '@/client'
import DocumentCard from '@/components/custom/DocumentCard.vue'
import DocumentCardSkeleton from '@/components/custom/DocumentCardSkeleton.vue'
import { Button } from '@/components/ui/button'
import { documentTitle, useDocumentGroup } from '@/viewmodels/document-list'

const linkStates = useLinkStateFilter()
const props = defineProps<{ document: DocumentResponse }>()
const { cards, totalCount, filteredCount, error, isLoading, retry } = useDocumentGroup(
  () => props.document,
  4,
  linkStates,
)
const widePreviews = useMediaQuery('(min-width: 640px)')
const visibleCards = computed(() => cards.value.slice(0, widePreviews.value ? 4 : 2))
</script>

<template>
  <article
    class="document-row flex w-full min-w-0 flex-col gap-4 border-b py-4 lg:flex-row"
    :aria-label="documentTitle(document)"
  >
    <header class="document-heading w-full min-w-0 lg:w-1/3 lg:shrink-0">
      <RouterLink
        class="document-link group block rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
        :aria-label="`View document ${documentTitle(document)} in ${document.library}`"
        :to="{
          name: 'document-search',
          query: {
            library: document.library,
            document: document.document_id,
            ...(linkStates.length && { link_state: linkStates }),
          },
        }"
      >
        <div class="flex items-start gap-1">
          <h2
            class="line-clamp-3 break-all underline underline-offset-4"
            :title="documentTitle(document)"
          >
            {{ documentTitle(document) }}
          </h2>
          <ArrowUpRight class="mt-1 size-4 shrink-0" aria-hidden="true" />
        </div>
        <p class="mt-1 break-all text-sm text-muted-foreground">
          <span class="font-bold text-secondary">{{ document.library }} · </span
          >{{ document.document_id }}
        </p>
      </RouterLink>
      <p v-if="totalCount !== null" class="mt-1 text-sm text-muted-foreground">
        <template v-if="linkStates.length">{{ filteredCount }} matching of </template
        >{{ totalCount }} registered {{ totalCount === 1 ? 'page' : 'pages' }}
      </p>
      <EntityLinkStatistics :stats="document.entity_link_stats" unassigned class="mt-2" />
      <p class="mt-2 text-sm text-muted-foreground">
        {{
          document.last_touched_at
            ? `Last processed: ${new Date(document.last_touched_at).toLocaleString()}`
            : 'Processing not recorded'
        }}
      </p>
      <p v-if="document.last_touched_at" class="mt-1 break-all text-sm text-muted-foreground">
        User: {{ document.last_touched_by_user_id }} · API key:
        {{ document.last_touched_by_api_key_id ?? 'None' }}
      </p>
    </header>
    <div
      class="document-previews flex min-w-0 flex-1 flex-row flex-wrap content-start items-start gap-2"
    >
      <RouterLink
        v-for="card in visibleCards"
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
          :show-library="false"
          :document-uuid="card.documentId"
          :page-uuid="card.pageId"
          :names="card.names"
          :thumbnail-url="card.thumbnailUrl"
          :thumbnail-loading="card.thumbnailLoading"
        />
      </RouterLink>
      <DocumentCardSkeleton
        v-for="index in isLoading ? (widePreviews ? 4 : 2) : 0"
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
        {{
          linkStates.length
            ? 'No pages match the selected link states.'
            : 'No pages have been registered for this document yet.'
        }}
      </p>
      <p
        v-if="filteredCount !== null && filteredCount > visibleCards.length"
        class="w-full text-sm text-muted-foreground"
      >
        Showing {{ visibleCards.length }} of {{ filteredCount }}
        {{ linkStates.length ? 'matching' : 'registered' }} pages. Open the document to see all
        pages.
      </p>
    </div>
  </article>
</template>

<style scoped>
.document-previews > .scan-card {
  flex: 0 0 calc((100% - 0.5rem) / 2);
}
@media (min-width: 640px) {
  .document-previews > .scan-card {
    flex-basis: calc((100% - 1.5rem) / 4);
  }
}
</style>
