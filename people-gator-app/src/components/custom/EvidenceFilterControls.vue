<script setup lang="ts">
import { computed, ref } from 'vue'
import { useEvidenceFilters, originOptions } from '@/viewmodels/evidence-filters'
import type { EvidenceFilters } from '@/viewmodels/evidence-filters'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import FilterMultiSelect from './FilterMultiSelect.vue'
import FilterDateTimePicker from './FilterDateTimePicker.vue'
import EntityLinkStateFilter from './EntityLinkStateFilter.vue'
defineProps<{ hideState?: boolean; hideDocuments?: boolean }>()
const { filters, error } = useEvidenceFilters()
function field<K extends keyof EvidenceFilters>(key: K) {
  return computed({
    get: () => filters.value[key],
    set: (value: EvidenceFilters[K]) => {
      filters.value = { ...filters.value, [key]: value }
    },
  })
}
const states = field('states'),
  origins = field('origins'),
  from = field('touchedFrom'),
  to = field('touchedTo')
const selections = {
  libraries: field('libraries'),
  documentIds: field('documentIds'),
  userIds: field('userIds'),
  apiKeyIds: field('apiKeyIds'),
}
const opened = ref<Record<string, boolean>>({})
const librarySearch = ref(''),
  documentSearch = ref(''),
  userSearch = ref(''),
  apiKeySearch = ref(''),
  originSearch = ref('')
const lookups = [
  {
    key: 'libraries' as const,
    label: 'Evidence libraries',
    search: librarySearch,
    options: usePeopleFilterOptions('library', librarySearch, () => !!opened.value.libraries),
  },
  {
    key: 'documentIds' as const,
    label: 'Evidence documents',
    search: documentSearch,
    options: usePeopleFilterOptions('document', documentSearch, () => !!opened.value.documentIds),
  },
  {
    key: 'userIds' as const,
    label: 'Annotation last users',
    search: userSearch,
    options: usePeopleFilterOptions('user', userSearch, () => !!opened.value.userIds),
  },
  {
    key: 'apiKeyIds' as const,
    label: 'Annotation last API keys',
    search: apiKeySearch,
    options: usePeopleFilterOptions('api-key', apiKeySearch, () => !!opened.value.apiKeyIds),
  },
]
const filteredOrigins = computed(() =>
  originOptions.filter((o) => o.label.toLowerCase().includes(originSearch.value.toLowerCase())),
)
</script>
<template>
  <EntityLinkStateFilter v-if="!hideState" v-model="states" />
  <FilterMultiSelect
    :model-value="origins"
    @update:model-value="origins = $event as EvidenceFilters['origins']"
    v-model:search="originSearch"
    label="Evidence origin"
    :options="filteredOrigins"
    class="max-w-full flex-none"
  />
  <template v-for="lookup in lookups" :key="lookup.key">
    <FilterMultiSelect
      v-if="!hideDocuments || lookup.key !== 'documentIds'"
      v-model="selections[lookup.key].value"
      v-model:search="lookup.search.value"
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
  </template>
  <FilterDateTimePicker v-model="from" label="Annotation touched from" :invalid="!!error" />
  <FilterDateTimePicker v-model="to" label="Annotation touched to" :invalid="!!error" />
</template>
