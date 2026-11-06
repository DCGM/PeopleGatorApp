<script setup lang="ts">
import { watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { usePageQuery } from '@/query/media'
import { Button } from '@/components/ui/button'

const route = useRoute()
const router = useRouter()
const page = usePageQuery(() => String(route.params.pageSourceId))
watch(
  page.data,
  (value) => {
    if (!value || value.source_id !== route.params.pageSourceId) return
    void router.replace({
      name: 'document-page',
      params: { libraryId: value.library, documentId: value.document_id, pageId: value.page_id },
    })
  },
  { immediate: true },
)
</script>

<template>
  <main class="p-4">
    <div v-if="page.error.value" role="alert" class="space-y-3">
      <p>Could not open this page.</p>
      <div class="flex flex-wrap gap-2">
        <Button variant="outline" :disabled="page.isFetching.value" @click="page.refetch()"
          >Retry page</Button
        >
        <Button variant="outline" as-child
          ><RouterLink :to="{ name: 'document-list' }">Documents</RouterLink></Button
        >
      </div>
    </div>
    <p v-else role="status">Opening page…</p>
  </main>
</template>
