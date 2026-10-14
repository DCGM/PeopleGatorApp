<script setup lang="ts">
import { computed, ref } from 'vue'
import SearchFilterPanel from './SearchFilterPanel.vue'
import ActiveFilters, { type ActiveFilter } from './ActiveFilters.vue'
import FilterDateTimePicker from './FilterDateTimePicker.vue'
import FilterMultiSelect from './FilterMultiSelect.vue'
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import { emptyDocumentFilters, type DocumentFilters } from '@/viewmodels/document-filters'
import { linkStateVisuals } from '@/lib/entity-links'

defineProps<{ resultCount: number; filterError?: string }>()
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
    ['touchedFrom', 'From'],
    ['touchedTo', 'To'],
  ] as const)
    if (filters.value[key])
      chips.push({
        key,
        value: filters.value[key],
        label: `${label}: ${filters.value[key].replace('T', ' ')}`,
      })
  for (const [key, label, labels] of [
    ['libraries', 'Library', libraryOptions.labels.value],
    ['userIds', 'User', users.labels.value],
    ['apiKeyIds', 'API key', apiKeys.labels.value],
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
    <div class="min-w-0 flex-none max-w-full">
      <Select v-model="unassigned"
        ><SelectTrigger aria-label="Unassigned faces"
          ><SelectValue
            >Unassigned faces:
            {{
              { all: 'All documents', yes: 'Has unassigned faces', no: 'No unassigned faces' }[
                unassigned
              ]
            }}</SelectValue
          ></SelectTrigger
        ><SelectContent
          ><SelectItem value="all">All documents</SelectItem
          ><SelectItem value="yes">Has unassigned faces</SelectItem
          ><SelectItem value="no">No unassigned faces</SelectItem></SelectContent
        ></Select
      >
    </div>
    <FilterDateTimePicker
      v-model="touchedFrom"
      label="Last processed from"
      :invalid="!!filterError"
      class="flex-none max-w-full"
    />
    <FilterDateTimePicker
      v-model="touchedTo"
      label="Last processed to"
      :invalid="!!filterError"
      class="flex-none max-w-full"
    />
    <FilterMultiSelect
      v-model="userIds"
      v-model:search="userSearch"
      label="Users"
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
      label="API keys"
      :options="apiKeys.options.value"
      :is-loading="apiKeys.isLoading.value"
      :error="apiKeys.error.value"
      :has-more="apiKeys.hasMore.value"
      :is-loading-more="apiKeys.isLoadingMore.value"
      class="flex-none max-w-full"
      @load-more="apiKeys.loadMore()"
      @retry="apiKeys.retry()"
    />
  </SearchFilterPanel>
  <p v-if="filterError" role="alert">{{ filterError }}</p>
  <ActiveFilters :filters="active" @remove="remove" @clear="filters = emptyDocumentFilters()" />
</template>
