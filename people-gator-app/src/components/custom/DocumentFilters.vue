<script setup lang="ts">
import FilterGroup from './FilterGroup.vue'
import SharedFilterControls from './SharedFilterControls.vue'
import CountRangeControl from './CountRangeControl.vue'
import DocumentFilterTags from './DocumentFilterTags.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
import { useDocumentFilters, VERIFICATION_LABELS } from '@/viewmodels/document-filters'
import {
  DOCUMENT_COUNT_CATEGORIES,
  DOCUMENT_COUNT_STATES,
  LINKED_PEOPLE_FIELD,
  useDocumentCounts,
  type DocumentCountField,
} from '@/viewmodels/document-counts'

// The Documents filter set (#111), shown in the desktop sidebar or the mobile drawer.
// Applied filters are listed below the selectors; mobile also shows them under search.
const counts = useDocumentCounts()
const { verification } = useDocumentFilters()
const verificationOptions = [
  { value: 'all' as const, label: 'All' },
  { value: 'verified' as const, label: VERIFICATION_LABELS.verified },
  { value: 'not_verified' as const, label: VERIFICATION_LABELS.not_verified },
]
const apply = (field: string, lower: string, upper: string) =>
  counts.set(field as DocumentCountField, lower, upper)
</script>

<template>
  <div class="flex w-full min-w-0 flex-col gap-4" role="group" aria-label="Filters">
    <FilterGroup title="Source">
      <SharedFilterControls :controls="['libraries']" />
    </FilterGroup>
    <FilterGroup title="Review">
      <FilterSingleSelect
        v-model="verification"
        class="max-w-full flex-none"
        label="Verification"
        :options="verificationOptions"
      />
    </FilterGroup>
    <FilterGroup title="Counts">
      <CountRangeControl
        v-for="category in DOCUMENT_COUNT_CATEGORIES"
        :key="category.value"
        :label="category.label"
        :states="DOCUMENT_COUNT_STATES"
        :field-for="(state) => `${category.value}_${state}_count`"
        :params="counts.params.value"
        trigger-class="max-w-full"
        @apply="apply"
      />
      <CountRangeControl
        label="People"
        :field-for="() => LINKED_PEOPLE_FIELD"
        :params="counts.params.value"
        trigger-class="max-w-full"
        @apply="apply"
      />
    </FilterGroup>
    <FilterGroup title="Created">
      <SharedFilterControls :controls="['creators', 'creationDates']" />
    </FilterGroup>
    <FilterGroup title="Modified">
      <SharedFilterControls :controls="['actors', 'dates']" />
    </FilterGroup>
  </div>
  <!-- Applied filters always follow the selectors, in the sidebar and in the drawer. -->
  <div class="group flex min-w-0 flex-col pt-4" role="group" aria-label="Applied filters">
    <small
      class="hidden font-semibold uppercase text-secondary group-has-[.active-filters]:block"
      aria-hidden="true"
      >Applied filters</small
    >
    <DocumentFilterTags />
  </div>
</template>
