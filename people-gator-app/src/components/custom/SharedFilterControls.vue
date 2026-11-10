<script setup lang="ts">
import { computed, ref } from 'vue'
import { useSharedFilters, type SharedFilters } from '@/viewmodels/shared-filters'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import FilterMultiSelect from './FilterMultiSelect.vue'
import FilterDateTimePicker from './FilterDateTimePicker.vue'
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'

// The one shared configuration (#52); each screen applies it to its own records.
type Control =
  | 'libraries'
  | 'documents'
  | 'pages'
  | 'linkStates'
  | 'actors'
  | 'dates'
  | 'creators'
  | 'creationDates'
// Screens may show a subset (Documents, #111); hidden values still apply from the URL.
const props = withDefaults(defineProps<{ controls?: readonly Control[] }>(), {
  controls: () => [
    'libraries',
    'documents',
    'pages',
    'linkStates',
    'creators',
    'creationDates',
    'actors',
    'dates',
  ],
})
const shown = (control: Control) => props.controls.includes(control)
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
  createdFrom = field('createdFrom'),
  createdTo = field('createdTo'),
  from = field('touchedFrom'),
  to = field('touchedTo')
const selections = {
  libraries: field('libraries'),
  documentIds: field('documentIds'),
  pageIds: field('pageIds'),
  creatorIds: field('creatorIds'),
  creationApiKeyIds: field('creationApiKeyIds'),
  userIds: field('userIds'),
  apiKeyIds: field('apiKeyIds'),
}
const opened = ref<Record<string, boolean>>({})
const searches = {
  libraries: ref(''),
  documentIds: ref(''),
  pageIds: ref(''),
  creatorIds: ref(''),
  creationApiKeyIds: ref(''),
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
  {
    key: 'libraries' as const,
    control: 'libraries' as const,
    label: 'Libraries',
    options: option('libraries', 'library'),
  },
  {
    key: 'documentIds' as const,
    control: 'documents' as const,
    label: 'Documents',
    options: option('documentIds', 'document'),
  },
  {
    key: 'pageIds' as const,
    control: 'pages' as const,
    label: 'Pages',
    options: option('pageIds', 'page'),
  },
].filter((lookup) => shown(lookup.control))
const actors = [
  {
    key: 'creatorIds' as const,
    control: 'creators' as const,
    label: 'Created by',
    options: option('creatorIds', 'user'),
  },
  {
    key: 'creationApiKeyIds' as const,
    control: 'creators' as const,
    label: 'Created via key',
    options: option('creationApiKeyIds', 'api-key'),
  },
  {
    key: 'userIds' as const,
    control: 'actors' as const,
    label: 'Modified by',
    options: option('userIds', 'user'),
  },
  {
    key: 'apiKeyIds' as const,
    control: 'actors' as const,
    label: 'Modified via key',
    options: option('apiKeyIds', 'api-key'),
  },
].filter((lookup) => shown(lookup.control))
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
  <EntityLinkStateFilter v-if="shown('linkStates')" v-model="linkStates" />
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
  <template v-if="shown('dates')">
    <FilterDateTimePicker v-model="from" label="Modified from" :invalid="!!error" />
    <FilterDateTimePicker v-model="to" label="Modified to" :invalid="!!error" />
  </template>
  <template v-if="shown('creationDates')">
    <FilterDateTimePicker v-model="createdFrom" label="Created from" :invalid="!!error" />
    <FilterDateTimePicker v-model="createdTo" label="Created to" :invalid="!!error" />
  </template>
</template>
