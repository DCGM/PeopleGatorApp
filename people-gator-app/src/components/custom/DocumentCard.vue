<script setup lang="ts">
import { pagePosition } from '@/lib/page-position'
import { ChevronRight, FileText } from '@lucide/vue'

import LoadableImage from '@/components/custom/LoadableImage.vue'
import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'

const props = withDefaults(
  defineProps<{
    library: string
    documentUuid: string
    pageUuid: string
    pageNumber?: number | null
    registeredPageCount?: number | null
    names: readonly string[]
    thumbnailUrl?: string
    thumbnailLoading?: boolean
    showLibrary?: boolean
  }>(),
  { showLibrary: true },
)
</script>

<template>
  <Card
    class="h-full gap-2 overflow-hidden rounded-none border-0 bg-transparent py-0 text-muted-foreground shadow-none transition-transform group-hover:text-primary group-focus:text-primary"
  >
    <CardHeader class="gap-0 px-0">
      <AspectRatio :ratio="210 / 297" class="overflow-hidden bg-muted">
        <LoadableImage
          :src="props.thumbnailUrl"
          :loading="props.thumbnailLoading"
          :alt="`Scan ${props.pageUuid} from document ${props.documentUuid}`"
          class="size-full"
          image-class="object-cover duration-300 ease-out group-hover:scale-105 group-focus:scale-102"
        >
          <template #fallback>
            <div class="flex size-full items-center justify-center text-muted-foreground">
              <FileText class="size-10" aria-hidden="true" />
            </div>
          </template>
        </LoadableImage>
      </AspectRatio>
    </CardHeader>
    <CardContent class="px-0">
      <small
        class="block tabular-nums"
        :aria-label="`Page ${props.pageNumber ?? 'unknown'} of ${props.registeredPageCount ?? 'unknown'} registered pages`"
        >{{ pagePosition(props.pageNumber, props.registeredPageCount) }}</small
      >
      <small class="block truncate" :title="props.pageUuid">
        <span v-if="props.showLibrary" class="font-bold text-secondary"
          >{{ props.library }} ·
        </span>
        {{ props.pageUuid }}
      </small>
    </CardContent>
    <CardFooter class="gap-1 px-0">
      <small class="flex-1 truncate font-heading">
        {{ props.names.slice(0, 2).join(', ') }}
      </small>
      <small v-if="props.names.length > 2" class="whitespace-nowrap text-secondary">
        +{{ props.names.length - 2 }} more
      </small>
      <ChevronRight
        class="size-4 shrink-0 transition-all duration-200 group-hover:translate-x-1 group-focus:-translate-x-1"
        aria-hidden="true"
      />
    </CardFooter>
  </Card>
</template>
