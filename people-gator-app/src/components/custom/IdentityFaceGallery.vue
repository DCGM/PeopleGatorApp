<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { useFaceListQuery, type FaceListParams } from '@/query/faces'
import IdentityReferenceFace from './IdentityReferenceFace.vue'

const props = defineProps<{ personId: string; name: string }>()
// Reference evidence includes every link state and source, independently of scan
// filters. ID ordering stays stable across cursor pages and review edits.
const query = useFaceListQuery((): FaceListParams => ({
  'filter.entity_id': [props.personId],
  sort: 'detection_id',
  sort_direction: 'asc',
  limit: 6,
  return_total_count: true,
}))
const faces = computed(() => {
  const seen = new Set<string>()
  return (query.data.value?.pages.flatMap((page) => page.items) ?? []).filter((face) => {
    if (face.entity_id !== props.personId || seen.has(face.detection_id)) return false
    seen.add(face.detection_id)
    return true
  })
})
const total = computed(() => query.data.value?.pages[0]?.total_count)
function retry() {
  if (query.isFetchNextPageError.value) void query.fetchNextPage()
  else void query.refetch()
}
</script>

<template>
  <div class="space-y-3" :aria-busy="query.isFetching.value">
    <p v-if="query.isPending.value" role="status" class="text-sm">Loading faces…</p>
    <div v-if="query.isPending.value" class="grid grid-cols-3 gap-2">
      <Skeleton v-for="i in 6" :key="i" class="aspect-square w-full" />
    </div>
    <ScrollArea v-if="faces.length" class="h-48 w-full" type="always">
      <div
        class="grid grid-cols-3 gap-2 pr-3"
        role="list"
        :aria-label="`Reference faces of ${name}`"
      >
        <IdentityReferenceFace
          v-for="(face, index) in faces"
          :key="face.detection_id"
          :face-id="face.detection_id"
          :label="`${name}, face ${index + 1}`"
        />
      </div>
    </ScrollArea>
    <p
      v-if="!query.isPending.value && !query.isError.value && !faces.length"
      role="status"
      class="text-sm"
    >
      No linked faces.
    </p>
    <p v-if="faces.length" role="status" class="text-sm text-muted-foreground">
      {{ faces.length }}{{ total != null ? ` of ${total}` : '' }} faces
    </p>
    <div v-if="query.isError.value" class="space-y-2" role="alert">
      <p class="text-sm">Could not load {{ faces.length ? 'more ' : '' }}faces.</p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        :disabled="query.isFetching.value"
        @click="retry"
        >Retry</Button
      >
    </div>
    <Button
      v-else-if="query.hasNextPage.value"
      type="button"
      variant="outline"
      size="sm"
      :disabled="query.isFetching.value"
      @click="query.fetchNextPage()"
    >
      {{ query.isFetchingNextPage.value ? 'Loading more…' : 'Load more faces' }}
    </Button>
  </div>
</template>
