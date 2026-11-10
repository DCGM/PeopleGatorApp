<script setup lang="ts">
import SharedFilterControls from './SharedFilterControls.vue'
import CountRangeControl from './CountRangeControl.vue'
import DocumentFilterTags from './DocumentFilterTags.vue'
import {
  DOCUMENT_COUNT_CATEGORIES,
  DOCUMENT_COUNT_STATES,
  LINKED_PEOPLE_FIELD,
  useDocumentCounts,
  type DocumentCountField,
} from '@/viewmodels/document-counts'

// The Documents filter set (#111), shown in the desktop sidebar or the mobile drawer.
// The sidebar lists applied filters below the selectors; mobile shows them under search.
defineProps<{ tags?: boolean }>()
const counts = useDocumentCounts()
const apply = (field: string, lower: string, upper: string) =>
  counts.set(field as DocumentCountField, lower, upper)
</script>

<template>
  <div class="flex w-full min-w-0 flex-col items-stretch gap-2" role="group" aria-label="Filters">
    <SharedFilterControls
      :controls="['libraries', 'creators', 'creationDates', 'actors', 'dates']"
    />
    <CountRangeControl
      v-for="category in DOCUMENT_COUNT_CATEGORIES"
      :key="category.value"
      :label="category.label"
      :states="DOCUMENT_COUNT_STATES"
      :field-for="(state) => `${category.value}_${state}_count`"
      :params="counts.params.value"
      trigger-class="w-full"
      @apply="apply"
    />
    <CountRangeControl
      label="People"
      :field-for="() => LINKED_PEOPLE_FIELD"
      :params="counts.params.value"
      trigger-class="w-full"
      @apply="apply"
    />
  </div>
  <div v-if="tags" class="flex min-w-0 flex-col gap-2 pt-2">
    <DocumentFilterTags />
  </div>
</template>
