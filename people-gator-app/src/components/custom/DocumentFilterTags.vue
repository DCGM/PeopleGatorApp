<script setup lang="ts">
import { computed } from 'vue'
import { DOCUMENT_COUNT_KEYS, useDocumentCounts } from '@/viewmodels/document-counts'
import { useDocumentFilters } from '@/viewmodels/document-filters'
import SharedFilterTags from './SharedFilterTags.vue'
import type { ActiveFilter } from './ActiveFilters.vue'

// Applied Documents filters: below the sidebar selectors on desktop, below search on mobile.
const counts = useDocumentCounts()
// Unassigned faces has no control here, but links can still carry it.
const { unassigned } = useDocumentFilters()
const labels = { yes: 'Has unassigned faces', no: 'No unassigned faces' }
const specific = computed<ActiveFilter[]>(() =>
  unassigned.value === 'all'
    ? []
    : [
        {
          key: 'unassigned',
          value: unassigned.value,
          label: `Unassigned faces: ${labels[unassigned.value]}`,
        },
      ],
)
</script>

<template>
  <p v-if="counts.error.value" role="alert">{{ counts.error.value }}</p>
  <SharedFilterTags
    :specific-filters="[...specific, ...counts.tags.value]"
    :specific-keys="['unassigned', ...DOCUMENT_COUNT_KEYS]"
    @remove-specific="$event.key === 'unassigned' ? (unassigned = 'all') : counts.remove($event)"
  />
</template>
