<script setup lang="ts">
import { pagePosition } from '@/lib/page-position'
import type { DocumentResponse } from '@/client'
import { usePageImageQuery } from '@/query/media'
import { useObjectUrl } from '@/composables/object-url'
import { documentTitle } from '@/viewmodels/document-list'
import LoadableImage from './LoadableImage.vue'

const props = defineProps<{ document: DocumentResponse }>()
const image = usePageImageQuery(() => props.document.first_page_source_id ?? '', 256)
const url = useObjectUrl(() => image.data.value)
</script>

<template>
  <div class="space-y-1">
    <LoadableImage
      :src="url"
      :alt="`First registered page of ${documentTitle(document)}`"
      :loading="Boolean(document.first_page_source_id) && image.isPending.value"
      class="h-28 w-20"
      image-class="object-contain"
    >
      <template #fallback>
        <span class="flex h-full items-center whitespace-normal text-sm text-muted-foreground">{{
          document.registered_page_count === 0 ? 'No pages' : 'No preview'
        }}</span>
      </template>
    </LoadableImage>
    <small
      v-if="document.first_page_source_id"
      class="tabular-nums"
      aria-label="Page position among registered pages"
      >{{ pagePosition(document.first_page_number, document.registered_page_count) }}</small
    >
  </div>
</template>
