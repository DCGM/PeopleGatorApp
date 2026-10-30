<script setup lang="ts">
import AnnotationCountControl from './AnnotationCountControl.vue'
import { COUNT_KEYS, useAnnotationCounts } from '@/viewmodels/annotation-counts'
import { useRoute, useRouter } from 'vue-router'
import { queryValues } from '@/viewmodels/shared-filters'
import { computed } from 'vue'
import SharedFilterControls from './SharedFilterControls.vue'
import SharedFilterTags from './SharedFilterTags.vue'
import SearchFilterPanel from './SearchFilterPanel.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
import SortControl from './SortControl.vue'
import type { ActiveFilter } from './ActiveFilters.vue'
import type { PageSortField } from '@/client'
import type { SortOption, SortState } from '@/lib/sorting'
import type { PageContentFilter } from '@/viewmodels/assignment'

const counts = useAnnotationCounts()

defineProps<{
  resultCount: number
  hasMoreResults?: boolean
  sortOptions?: SortOption<PageSortField>[]
  documentLabels?: Record<string, string>
}>()
const sort = defineModel<SortState<PageSortField>>('sort')
const searchTerm = defineModel<string>('searchTerm', { required: true })
const assignment = defineModel<PageContentFilter>('assignment', { required: true })
const contentLabels: Record<PageContentFilter, string> = {
  all: 'All pages',
  entities: 'Contains assigned entities',
  faces: 'Contains faces',
  mentions: 'Contains mentions',
}
const route = useRoute(),
  router = useRouter()
function removeSpecific(tag: ActiveFilter) {
  if (tag.key.startsWith('min_')) counts.remove(tag)
  else if (tag.key === 'assignment') assignment.value = 'all'
  else
    void router.push({
      query: {
        ...route.query,
        archive_document: queryValues(route.query.archive_document).filter(
          (id) => id !== tag.value,
        ),
        cursor: undefined,
      },
    })
}
const specific = computed<ActiveFilter[]>(() => [
  ...queryValues(route.query.archive_document).map((id) => ({
    key: 'archive_document',
    value: id,
    label: `Archive document: ${id}`,
  })),
  ...(assignment.value === 'all'
    ? []
    : [
        {
          key: 'assignment',
          value: assignment.value,
          label: `Page content: ${contentLabels[assignment.value]}`,
        },
      ]),
])
</script>

<template>
  <SearchFilterPanel
    v-model="searchTerm"
    label="Search scans"
    placeholder="Search a person, page or document…"
    :result-count="resultCount"
    :has-more-results="hasMoreResults"
  >
    <SharedFilterControls />
    <AnnotationCountControl />
    <FilterSingleSelect
      v-model="assignment"
      label="Page content"
      :options="Object.entries(contentLabels).map(([value, label]) => ({ value, label }))"
    />
    <SortControl v-if="sort && sortOptions" v-model="sort" :options="sortOptions" />
  </SearchFilterPanel>
  <p v-if="counts.error.value" role="alert">{{ counts.error.value }}</p>
  <SharedFilterTags
    :specific-filters="[...specific, ...counts.tags.value]"
    :specific-keys="['assignment', 'archive_document', ...COUNT_KEYS]"
    :document-labels="documentLabels"
    @remove-specific="removeSpecific"
  />
</template>
