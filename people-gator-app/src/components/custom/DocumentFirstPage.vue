<script setup lang="ts">
import type { DocumentResponse } from '@/client'
import { usePageImageQuery } from '@/query/media'
import { useObjectUrl } from '@/composables/object-url'
import { documentTitle } from '@/viewmodels/document-list'
import LoadableImage from './LoadableImage.vue'
import UiTooltip from './UiTooltip.vue'
import { Button } from '@/components/ui/button'

const props = defineProps<{ document: DocumentResponse }>()
const image = usePageImageQuery(() => props.document.first_page_source_id ?? '', 256)
const url = useObjectUrl(() => image.data.value)
</script>

<template>
  <div class="relative h-28 w-20">
    <LoadableImage
      :src="url"
      :alt="`First registered page of ${documentTitle(document)}`"
      :loading="Boolean(document.first_page_source_id) && image.isPending.value"
      class="size-full"
      image-class="object-contain"
    >
      <template #fallback>
        <span class="flex h-full items-center whitespace-normal text-sm text-muted-foreground">{{
          document.registered_page_count === 0 ? 'No pages' : 'No preview'
        }}</span>
      </template>
    </LoadableImage>
    <UiTooltip text="Národní digitální knihovna">
      <Button as-child size="xs" class="absolute bottom-1 left-1/2 -translate-x-1/2 bg-primary/90">
        <a
          :href="document.url"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="NDK – Národní digitální knihovna"
          data-slot="document-source-link"
          >NDK</a
        >
      </Button>
    </UiTooltip>
  </div>
</template>
