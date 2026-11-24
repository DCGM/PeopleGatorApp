<script setup lang="ts">
import { computed } from 'vue'
import { DOCUMENT_COUNT_KEYS, useDocumentCounts } from '@/viewmodels/document-counts'
import { useDocumentFilters, VERIFICATION_LABELS } from '@/viewmodels/document-filters'
import SharedFilterTags from './SharedFilterTags.vue'
import type { ActiveFilter } from './ActiveFilters.vue'

// Applied Documents filters: below the sidebar selectors on desktop, below search on mobile.
const counts = useDocumentCounts()
// Unassigned faces has no control here, but links can still carry it.
const { unassigned, verification } = useDocumentFilters()
const labels = { yes: 'Has unassigned faces', no: 'No unassigned faces' }
const specific = computed<ActiveFilter[]>(() => [
  ...(verification.value === 'all'
    ? []
    : [
        {
          key: 'verification',
          value: verification.value,
          label: `Verification: ${VERIFICATION_LABELS[verification.value]}`,
        },
      ]),
  ...(unassigned.value === 'all'
    ? []
    : [
        {
          key: 'unassigned',
          value: unassigned.value,
          label: `Unassigned faces: ${labels[unassigned.value]}`,
        },
      ]),
])
function remove(filter: ActiveFilter) {
  if (filter.key === 'unassigned') unassigned.value = 'all'
  else if (filter.key === 'verification') verification.value = 'all'
  else counts.remove(filter)
}
</script>

<template>
  <p v-if="counts.error.value" role="alert">{{ counts.error.value }}</p>
  <SharedFilterTags
    :specific-filters="[...specific, ...counts.tags.value]"
    :specific-keys="['verification', 'unassigned', ...DOCUMENT_COUNT_KEYS]"
    @remove-specific="remove"
  />
</template>
