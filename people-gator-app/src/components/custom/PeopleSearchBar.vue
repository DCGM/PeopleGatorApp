<script setup lang="ts">
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'
import type { EntityLinkState } from '@/client'
import { linkStateVisuals } from '@/lib/entity-links'
const linkStates = defineModel<EntityLinkState[]>('linkStates', { default: () => [] })
import { computed, ref, useId } from 'vue'
import FilterMultiSelect from '@/components/custom/FilterMultiSelect.vue'
import FilterDateTimePicker from '@/components/custom/FilterDateTimePicker.vue'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import { emptyPeopleFilters, type PeopleProcessingFilters } from '@/viewmodels/people-filters'

import SearchFilterPanel from './SearchFilterPanel.vue'
import ActiveFilters from './ActiveFilters.vue'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { AssignmentFilter } from '@/viewmodels/assignment'

defineProps<{
  resultCount: number
  hasMoreResults?: boolean
  filterError?: string
}>()

const emit = defineEmits<{ clearFilters: [] }>()
const searchTerm = defineModel<string>('searchTerm', { required: true })
const assignment = defineModel<AssignmentFilter>('assignment', { required: true })
const filters = defineModel<PeopleProcessingFilters>('processingFilters', {
  default: emptyPeopleFilters,
})
const assignmentId = useId()
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
      label: `From ${filters.value.touchedFrom.replace('T', ' ')}`,
    })
  if (filters.value.touchedTo)
    chips.push({
      key: 'touchedTo',
      value: filters.value.touchedTo,
      label: `To ${filters.value.touchedTo.replace('T', ' ')}`,
    })
  for (const [key, prefix, labels] of [
    ['documentIds', 'Document', documents.labels.value],
    ['userIds', 'User', users.labels.value],
    ['apiKeyIds', 'API key', apiKeys.labels.value],
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
function clearFilters() {
  emit('clearFilters')
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
    <div class="min-w-0 flex-1 basis-40">
      <Select v-model="assignment">
        <SelectTrigger :id="assignmentId" aria-label="Assignment" class="w-full"
          ><SelectValue placeholder="Assignment"
        /></SelectTrigger>
        <SelectContent
          ><SelectGroup
            ><SelectLabel>Assignment</SelectLabel><SelectItem value="all">All people</SelectItem
            ><SelectItem value="faces">Assigned faces</SelectItem
            ><SelectItem value="mentions">Assigned mentions</SelectItem></SelectGroup
          ></SelectContent
        >
      </Select>
    </div>
    <EntityLinkStateFilter v-model="linkStates" />
    <FilterMultiSelect
      v-model="filters.documentIds"
      v-model:search="documentSearch"
      label="Documents"
      :options="documents.options.value"
      :is-loading="documents.isLoading.value"
      :error="documents.error.value"
      :has-more="documents.hasMore.value"
      :is-loading-more="documents.isLoadingMore.value"
      class="flex-1 basis-40"
      @load-more="documents.loadMore()"
      @retry="documents.retry()"
    />
    <FilterDateTimePicker
      v-model="filters.touchedFrom"
      label="Last processed from"
      :invalid="!!filterError"
      class="flex-1 basis-40"
    />
    <FilterDateTimePicker
      v-model="filters.touchedTo"
      label="Last processed to"
      :invalid="!!filterError"
      class="flex-1 basis-40"
    />
    <FilterMultiSelect
      v-model="filters.userIds"
      v-model:search="userSearch"
      label="Users"
      :options="users.options.value"
      :is-loading="users.isLoading.value"
      :error="users.error.value"
      :has-more="users.hasMore.value"
      :is-loading-more="users.isLoadingMore.value"
      class="flex-1 basis-40"
      @load-more="users.loadMore()"
      @retry="users.retry()"
    />
    <FilterMultiSelect
      v-model="filters.apiKeyIds"
      v-model:search="apiKeySearch"
      label="API keys"
      :options="apiKeys.options.value"
      :is-loading="apiKeys.isLoading.value"
      :error="apiKeys.error.value"
      :has-more="apiKeys.hasMore.value"
      :is-loading-more="apiKeys.isLoadingMore.value"
      class="flex-1 basis-40"
      @load-more="apiKeys.loadMore()"
      @retry="apiKeys.retry()"
    />
  </SearchFilterPanel>
  <p v-if="filterError" role="alert">{{ filterError }}</p>
  <ActiveFilters
    :filters="active"
    @remove="
      (chip) => removeFilter(chip.key as keyof PeopleProcessingFilters | 'linkState', chip.value)
    "
    @clear="clearFilters"
  />
</template>
