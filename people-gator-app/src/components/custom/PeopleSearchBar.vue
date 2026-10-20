<script setup lang="ts">
import EvidenceFilterControls from './EvidenceFilterControls.vue'
import EvidenceFilterTags from './EvidenceFilterTags.vue'
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'
import type { EntityLinkState } from '@/client'
import { linkStateVisuals } from '@/lib/entity-links'
const linkStates = defineModel<EntityLinkState[]>('linkStates', { default: () => [] })
import { computed, ref } from 'vue'
import FilterMultiSelect from '@/components/custom/FilterMultiSelect.vue'
import FilterDateTimePicker from '@/components/custom/FilterDateTimePicker.vue'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import { emptyPeopleFilters, type PeopleProcessingFilters } from '@/viewmodels/people-filters'

import SearchFilterPanel from './SearchFilterPanel.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
import type { AssignmentFilter } from '@/viewmodels/assignment'

defineProps<{
  resultCount: number
  hasMoreResults?: boolean
  filterError?: string
}>()

const searchTerm = defineModel<string>('searchTerm', { required: true })
const assignment = defineModel<AssignmentFilter>('assignment', { required: true })
const filters = defineModel<PeopleProcessingFilters>('processingFilters', {
  default: emptyPeopleFilters,
})
function field<K extends keyof PeopleProcessingFilters>(key: K) {
  return computed({
    get: () => filters.value[key],
    set: (value: PeopleProcessingFilters[K]) => {
      filters.value = { ...filters.value, [key]: value }
    },
  })
}
const documentIds = field('documentIds'),
  touchedFrom = field('touchedFrom'),
  touchedTo = field('touchedTo'),
  userIds = field('userIds'),
  apiKeyIds = field('apiKeyIds')
const documentSearch = ref('')
const userSearch = ref('')
const apiKeySearch = ref('')
const documents = usePeopleFilterOptions('document', documentSearch)
const users = usePeopleFilterOptions('user', userSearch)
const apiKeys = usePeopleFilterOptions('api-key', apiKeySearch)
const active = computed(() => {
  const chips: {
    key: keyof PeopleProcessingFilters | 'linkState'
    value: string
    label: string
  }[] = []
  if (assignment.value !== 'all')
    chips.push({
      key: 'documentIds',
      value: '__assignment',
      label: assignment.value === 'faces' ? 'Assigned faces' : 'Assigned mentions',
    })
  if (filters.value.touchedFrom)
    chips.push({
      key: 'touchedFrom',
      value: filters.value.touchedFrom,
      label: `Person record from ${filters.value.touchedFrom.replace('T', ' ')}`,
    })
  if (filters.value.touchedTo)
    chips.push({
      key: 'touchedTo',
      value: filters.value.touchedTo,
      label: `Person record to ${filters.value.touchedTo.replace('T', ' ')}`,
    })
  for (const [key, prefix, labels] of [
    ['documentIds', 'Document', documents.labels.value],
    ['userIds', 'Person record user', users.labels.value],
    ['apiKeyIds', 'Person record API key', apiKeys.labels.value],
  ] as const) {
    for (const id of filters.value[key])
      chips.push({ key, value: id, label: `${prefix}: ${labels[id] ?? id}` })
  }
  for (const state of linkStates.value)
    chips.push({
      key: 'linkState',
      value: state,
      label: `Link state: ${linkStateVisuals[state].label}`,
    })
  return chips
})
function removeFilter(key: keyof PeopleProcessingFilters | 'linkState', value: string) {
  if (key === 'linkState') {
    linkStates.value = linkStates.value.filter((state) => state !== value)
    return
  }
  if (value === '__assignment') {
    assignment.value = 'all'
    return
  }
  if (key === 'touchedFrom' || key === 'touchedTo') filters.value = { ...filters.value, [key]: '' }
  else filters.value = { ...filters.value, [key]: filters.value[key].filter((id) => id !== value) }
}
</script>

<template>
  <SearchFilterPanel
    v-model="searchTerm"
    label="Search people"
    placeholder="Search a person or alias…"
    :result-count="resultCount"
    :has-more-results="hasMoreResults"
  >
    <FilterSingleSelect
      v-model="assignment"
      label="Assignment"
      :options="[
        { value: 'all', label: 'All people' },
        { value: 'faces', label: 'Assigned faces' },
        { value: 'mentions', label: 'Assigned mentions' },
      ]"
    />
    <EntityLinkStateFilter v-model="linkStates" />
    <FilterMultiSelect
      v-model="documentIds"
      v-model:search="documentSearch"
      label="Documents"
      :options="documents.options.value"
      :is-loading="documents.isLoading.value"
      :error="documents.error.value"
      :has-more="documents.hasMore.value"
      :is-loading-more="documents.isLoadingMore.value"
      class="flex-none max-w-full"
      @load-more="documents.loadMore()"
      @retry="documents.retry()"
    />
    <FilterDateTimePicker
      v-model="touchedFrom"
      label="Person record from"
      :invalid="!!filterError"
      class="flex-none max-w-full"
    />
    <FilterDateTimePicker
      v-model="touchedTo"
      label="Person record to"
      :invalid="!!filterError"
      class="flex-none max-w-full"
    />
    <FilterMultiSelect
      v-model="userIds"
      v-model:search="userSearch"
      label="Person record users"
      :options="users.options.value"
      :is-loading="users.isLoading.value"
      :error="users.error.value"
      :has-more="users.hasMore.value"
      :is-loading-more="users.isLoadingMore.value"
      class="flex-none max-w-full"
      @load-more="users.loadMore()"
      @retry="users.retry()"
    />
    <FilterMultiSelect
      v-model="apiKeyIds"
      v-model:search="apiKeySearch"
      label="Person record API keys"
      :options="apiKeys.options.value"
      :is-loading="apiKeys.isLoading.value"
      :error="apiKeys.error.value"
      :has-more="apiKeys.hasMore.value"
      :is-loading-more="apiKeys.isLoadingMore.value"
      class="flex-none max-w-full"
      @load-more="apiKeys.loadMore()"
      @retry="apiKeys.retry()"
    />
    <EvidenceFilterControls hide-state hide-documents />
  </SearchFilterPanel>
  <p v-if="filterError" role="alert">{{ filterError }}</p>
  <EvidenceFilterTags
    hide-state
    hide-documents
    :additional-filters="active"
    @remove-additional="
      (chip) => removeFilter(chip.key as keyof PeopleProcessingFilters | 'linkState', chip.value)
    "
  />
</template>
