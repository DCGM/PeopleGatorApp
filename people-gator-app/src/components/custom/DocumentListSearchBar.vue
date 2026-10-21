<script setup lang="ts">
import EvidenceFilterControls from './EvidenceFilterControls.vue'
import EvidenceFilterTags from './EvidenceFilterTags.vue'
import { computed, ref } from 'vue'
import SearchFilterPanel from './SearchFilterPanel.vue'
import type { ActiveFilter } from './ActiveFilters.vue'
import FilterDateTimePicker from './FilterDateTimePicker.vue'
import FilterMultiSelect from './FilterMultiSelect.vue'
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import { type DocumentFilters } from '@/viewmodels/document-filters'
import { linkStateVisuals } from '@/lib/entity-links'
import type { DocumentSortField } from '@/client'
import SortControl from './SortControl.vue'
import type { SortOption, SortState } from '@/lib/sorting'

defineProps<{
  resultCount: number
  filterError?: string
  sortOptions?: SortOption<DocumentSortField>[]
}>()
const sort = defineModel<SortState<DocumentSortField>>('sort')
const searchTerm = defineModel<string>('searchTerm', { required: true })
const filters = defineModel<DocumentFilters>('filters', { required: true })
function field<K extends keyof DocumentFilters>(key: K) {
  return computed({
    get: () => filters.value[key],
    set: (value: DocumentFilters[K]) => {
      filters.value = { ...filters.value, [key]: value }
    },
  })
}
const touchedFrom = field('touchedFrom'),
  touchedTo = field('touchedTo'),
  libraries = field('libraries'),
  userIds = field('userIds'),
  apiKeyIds = field('apiKeyIds'),
  linkStates = field('linkStates'),
  unassigned = field('unassigned')
const librarySearch = ref(''),
  userSearch = ref(''),
  apiKeySearch = ref('')
const libraryOptions = usePeopleFilterOptions('library', librarySearch)
const users = usePeopleFilterOptions('user', userSearch)
const apiKeys = usePeopleFilterOptions('api-key', apiKeySearch)
const active = computed<ActiveFilter[]>(() => {
  const chips: ActiveFilter[] = []
  for (const [key, label] of [
    ['touchedFrom', 'Document processing from'],
    ['touchedTo', 'Document processing to'],
  ] as const)
    if (filters.value[key])
      chips.push({
        key,
        value: filters.value[key],
        label: `${label}: ${filters.value[key].replace('T', ' ')}`,
      })
  for (const [key, label, labels] of [
    ['libraries', 'Library', libraryOptions.labels.value],
    ['userIds', 'Document processing user', users.labels.value],
    ['apiKeyIds', 'Document processing API key', apiKeys.labels.value],
  ] as const)
    for (const value of filters.value[key])
      chips.push({ key, value, label: `${label}: ${labels[value] ?? value}` })
  for (const state of filters.value.linkStates)
    chips.push({
      key: 'linkStates',
      value: state,
      label: `Link state: ${linkStateVisuals[state].label}`,
    })
  if (filters.value.unassigned !== 'all')
    chips.push({
      key: 'unassigned',
      value: filters.value.unassigned,
      label: `Unassigned faces: ${filters.value.unassigned === 'yes' ? 'Has unassigned faces' : 'No unassigned faces'}`,
    })
  return chips
})
function remove(chip: ActiveFilter) {
  const key = chip.key as keyof DocumentFilters
  if (key === 'touchedFrom' || key === 'touchedTo') filters.value = { ...filters.value, [key]: '' }
  else if (key === 'unassigned') unassigned.value = 'all'
  else
    filters.value = {
      ...filters.value,
      [key]: filters.value[key].filter((value) => value !== chip.value),
    }
}
</script>
<template>
  <SearchFilterPanel
    v-model="searchTerm"
    label="Search documents"
    placeholder="Search a document, person or archive UUID…"
    :result-count="resultCount"
  >
    <FilterMultiSelect
      v-model="libraries"
      v-model:search="librarySearch"
      label="Libraries"
      :options="libraryOptions.options.value"
      :is-loading="libraryOptions.isLoading.value"
      :error="libraryOptions.error.value"
      :has-more="libraryOptions.hasMore.value"
      :is-loading-more="libraryOptions.isLoadingMore.value"
      class="flex-none max-w-full"
      @load-more="libraryOptions.loadMore()"
      @retry="libraryOptions.retry()"
    />
    <EntityLinkStateFilter v-model="linkStates" />
    <EvidenceFilterControls hide-state />
    <FilterSingleSelect
      v-model="unassigned"
      label="Unassigned faces"
      :options="[
        { value: 'all', label: 'All documents' },
        { value: 'yes', label: 'Has unassigned faces' },
        { value: 'no', label: 'No unassigned faces' },
      ]"
    />
    <FilterDateTimePicker
      v-model="touchedFrom"
      label="Document processing from"
      :invalid="!!filterError"
      class="flex-none max-w-full"
    />
    <FilterDateTimePicker
      v-model="touchedTo"
      label="Document processing to"
      :invalid="!!filterError"
      class="flex-none max-w-full"
    />
    <FilterMultiSelect
      v-model="userIds"
      v-model:search="userSearch"
      label="Document processing users"
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
      label="Document processing API keys"
      :options="apiKeys.options.value"
      :is-loading="apiKeys.isLoading.value"
      :error="apiKeys.error.value"
      :has-more="apiKeys.hasMore.value"
      :is-loading-more="apiKeys.isLoadingMore.value"
      class="flex-none max-w-full"
      @load-more="apiKeys.loadMore()"
      @retry="apiKeys.retry()"
    />
    <SortControl v-if="sort && sortOptions" v-model="sort" :options="sortOptions" />
  </SearchFilterPanel>
  <p v-if="filterError" role="alert">{{ filterError }}</p>
  <EvidenceFilterTags hide-state :additional-filters="active" @remove-additional="remove" />
</template>
