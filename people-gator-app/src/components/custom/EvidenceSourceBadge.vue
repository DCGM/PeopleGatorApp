<script setup lang="ts">
import { CircleHelp, Database, File, FileText } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import type { SimilarPersonSource } from '@/viewmodels/similar-people.types'

defineProps<{ source: SimilarPersonSource }>()
const contexts = {
  page: { label: 'Page', description: 'Evidence on this page', icon: File },
  document: {
    label: 'Document',
    description: 'Evidence elsewhere in this document',
    icon: FileText,
  },
  database: { label: 'DB', description: 'Person outside this document', icon: Database },
  unknown: {
    label: 'Unknown',
    description: 'Source context is not available yet',
    icon: CircleHelp,
  },
}
</script>

<template>
  <Badge
    as="small"
    variant="outline"
    :data-source="source"
    :aria-label="contexts[source].description"
    :title="contexts[source].description"
    class="max-w-full gap-1"
    :class="
      source === 'page'
        ? 'border-secondary text-secondary ring-2 ring-secondary ring-offset-2 ring-offset-background'
        : source === 'document'
          ? 'border-secondary text-secondary'
          : 'bg-muted text-muted-foreground'
    "
  >
    <component :is="contexts[source].icon" aria-hidden="true" />
    {{ contexts[source].label }}
  </Badge>
</template>
