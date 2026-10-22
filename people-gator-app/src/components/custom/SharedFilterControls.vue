<script setup lang="ts">
import { computed, ref } from 'vue'
import { useSharedFilters, type SharedFilters } from '@/viewmodels/shared-filters'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import FilterMultiSelect from './FilterMultiSelect.vue'
import FilterDateTimePicker from './FilterDateTimePicker.vue'
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'

// The one shared configuration (#52); each screen applies it to its own records.
const { filters, error } = useSharedFilters()
function field<K extends keyof SharedFilters>(key: K) {
  return computed({
    get: () => filters.value[key],
    set: (value: SharedFilters[K]) => {
      filters.value = { ...filters.value, [key]: value }
    },
  })
}
const linkStates = field('linkStates'),
  from = field('touchedFrom'),
  to = field('touchedTo')
const selections = {
  libraries: field('libraries'),
  documentIds: field('documentIds'),
  pageIds: field('pageIds'),
  userIds: field('userIds'),
  apiKeyIds: field('apiKeyIds'),
}
const opened = ref<Record<string, boolean>>({})
const searches = {
  libraries: ref(''),
  documentIds: ref(''),
  pageIds: ref(''),
  userIds: ref(''),
  apiKeyIds: ref(''),
}
const option = (key: keyof typeof searches, kind: Parameters<typeof usePeopleFilterOptions>[0]) =>
  usePeopleFilterOptions(
    kind,
    searches[key],
    () => !!opened.value[key],
    () => ({
      libraries: filters.value.libraries,
      documentIds: filters.value.documentIds,
    }),
  )
const lookups = [
  { key: 'libraries' as const, label: 'Libraries', options: option('libraries', 'library') },
  { key: 'documentIds' as const, label: 'Documents', options: option('documentIds', 'document') },
  { key: 'pageIds' as const, label: 'Pages', options: option('pageIds', 'page') },
]
const actors = [
  { key: 'userIds' as const, label: 'Modified by', options: option('userIds', 'user') },
  { key: 'apiKeyIds' as const, label: 'Modified via key', options: option('apiKeyIds', 'api-key') },
]
</script>
<template>
  <FilterMultiSelect
    v-for="lookup in lookups"
    :key="lookup.key"
    v-model="selections[lookup.key].value"
    v-model:search="searches[lookup.key].value"
    :label="lookup.label"
    :options="lookup.options.options.value"
    :is-loading="lookup.options.isLoading.value"
    :error="lookup.options.error.value"
    :has-more="lookup.options.hasMore.value"
    :is-loading-more="lookup.options.isLoadingMore.value"
    class="max-w-full flex-none"
    @open-change="opened[lookup.key] = $event"
    @load-more="lookup.options.loadMore()"
    @retry="lookup.options.retry()"
  />
  <EntityLinkStateFilter v-model="linkStates" />
  <FilterMultiSelect
    v-for="lookup in actors"
    :key="lookup.key"
    v-model="selections[lookup.key].value"
    v-model:search="searches[lookup.key].value"
    :label="lookup.label"
    :options="lookup.options.options.value"
    :is-loading="lookup.options.isLoading.value"
    :error="lookup.options.error.value"
    :has-more="lookup.options.hasMore.value"
    :is-loading-more="lookup.options.isLoadingMore.value"
    class="max-w-full flex-none"
    @open-change="opened[lookup.key] = $event"
    @load-more="lookup.options.loadMore()"
    @retry="lookup.options.retry()"
  />
  <FilterDateTimePicker v-model="from" label="Modified from" :invalid="!!error" />
  <FilterDateTimePicker v-model="to" label="Modified to" :invalid="!!error" />
</template>
