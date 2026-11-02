<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import { useAutomaticPagination } from '@/composables/automatic-pagination'

const props = withDefaults(
  defineProps<{
    hasNextPage: boolean
    isFetching: boolean
    error?: unknown
    errorText?: string
    /** Changes when the list restarts, such as after a settings change. */
    resetKey?: unknown
    loadMore: () => Promise<unknown>
    retry: () => unknown
  }>(),
  { errorText: 'Could not load more.' },
)
const end = ref<HTMLElement | null>(null)
// Batches load as the end scrolls into view; short batches keep loading until it leaves.
useAutomaticPagination({
  target: end,
  hasNextPage: () => props.hasNextPage,
  isFetching: () => props.isFetching,
  error: () => props.error,
  enabled: true,
  resetKey: () => props.resetKey,
  loadMore: () => props.loadMore(),
})
</script>

<template>
  <div class="flex min-w-0 flex-col items-center gap-2 py-2 text-sm">
    <div v-if="hasNextPage && !error" ref="end" class="h-px w-full" aria-hidden="true" />
    <p v-if="error" role="alert" class="text-destructive">
      {{ errorText }}
      <Button type="button" variant="link" size="sm" @click="retry()">Retry</Button>
    </p>
    <p v-else-if="hasNextPage && isFetching" role="status" class="text-muted-foreground">
      Loading…
    </p>
    <!-- Automatic loading needs no click; this fallback stays keyboard reachable. -->
    <Button v-else-if="hasNextPage" type="button" variant="ghost" size="sm" @click="loadMore()"
      >Load more</Button
    >
  </div>
</template>
