<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { listPagesRouteApiV1PagesGet, type ListPagesRouteApiV1PagesGetResponse } from '@/client'
import { responseData } from '@/query/api'
import { queryKeys } from '@/query/keys'
import { Button } from '@/components/ui/button'
const props = defineProps<{ personId: string }>()
const query = useQuery({
  queryKey: computed(() => [...queryKeys.entities.detail(props.personId), 'libraries']),
  queryFn: async ({ signal }) => {
    const libraries = new Set<string>()
    let cursor: string | null = null
    do {
      const page: ListPagesRouteApiV1PagesGetResponse = await responseData(
        listPagesRouteApiV1PagesGet({
          query: { 'filter.entity_id': [props.personId], limit: 100, cursor },
          signal,
          throwOnError: true,
        }),
      )
      for (const source of page.items) libraries.add(source.library)
      cursor = page.cursor ?? null
    } while (cursor)
    return libraries.size
  },
})
</script>
<template>
  <dl>
    <dt class="text-muted-foreground">Libraries</dt>
    <dd class="font-mono">{{ query.isPending.value ? '…' : (query.data.value ?? '—') }}</dd>
  </dl>
  <p v-if="query.error.value" role="alert">
    Could not count libraries. <Button variant="link" @click="query.refetch()">Retry</Button>
  </p>
</template>
