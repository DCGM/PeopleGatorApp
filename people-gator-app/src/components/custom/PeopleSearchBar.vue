<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search, X } from '@lucide/vue'
import FilterMultiSelect from '@/components/custom/FilterMultiSelect.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import { emptyPeopleFilters, type PeopleProcessingFilters } from '@/viewmodels/people-filters'

import { Card, CardContent } from '@/components/ui/card'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
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

const searchTerm = defineModel<string>('searchTerm', { required: true })
const assignment = defineModel<AssignmentFilter>('assignment', { required: true })
const filters = defineModel<PeopleProcessingFilters>('processingFilters', {
  default: emptyPeopleFilters,
})
const documentSearch = ref('')
const userSearch = ref('')
const apiKeySearch = ref('')
const documents = usePeopleFilterOptions('document', documentSearch)
const users = usePeopleFilterOptions('user', userSearch)
const apiKeys = usePeopleFilterOptions('api-key', apiKeySearch)
const active = computed(() => {
  const chips: { key: keyof PeopleProcessingFilters; value: string; label: string }[] = []
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
  return chips
})
function removeFilter(key: keyof PeopleProcessingFilters, value: string) {
  if (value === '__assignment') {
    assignment.value = 'all'
    return
  }
  if (key === 'touchedFrom' || key === 'touchedTo') filters.value = { ...filters.value, [key]: '' }
  else filters.value = { ...filters.value, [key]: filters.value[key].filter((id) => id !== value) }
}
function clearFilters() {
  assignment.value = 'all'
  filters.value = emptyPeopleFilters()
}
</script>

<template>
  <div class="sticky top-13 z-20">
    <Card class="gap-3 rounded-none py-3">
      <CardContent
        class="grid w-full grid-cols-2 gap-2 px-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,9rem)]"
      >
        <InputGroup class="col-span-2 w-full rounded-none lg:col-span-1">
          <InputGroupInput v-model="searchTerm" placeholder="Search a person or alias…" />
          <InputGroupAddon>
            <Search />
          </InputGroupAddon>
          <InputGroupAddon align="inline-end" class="min-w-20 justify-end tabular-nums">
            {{ resultCount }}{{ hasMoreResults ? '+' : '' }} results
          </InputGroupAddon>
        </InputGroup>
        <Select v-model="assignment">
          <SelectTrigger class="w-full rounded-none">
            <SelectValue placeholder="Assignment" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel>Assignment</SelectLabel>
              <SelectItem value="all">All people</SelectItem>
              <SelectItem value="faces">Assigned faces</SelectItem>
              <SelectItem value="mentions">Assigned mentions</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <div class="col-span-2 grid gap-3 border-t pt-3 sm:grid-cols-2 lg:grid-cols-5">
          <label class="space-y-1 text-sm">
            <span>Last processed from</span>
            <Input
              v-model="filters.touchedFrom"
              type="datetime-local"
              step="0.001"
              class="rounded-none"
              :aria-invalid="!!filterError"
            />
          </label>
          <label class="space-y-1 text-sm">
            <span>Last processed to</span>
            <Input
              v-model="filters.touchedTo"
              type="datetime-local"
              step="0.001"
              class="rounded-none"
              :aria-invalid="!!filterError"
            />
          </label>
          <div class="space-y-1 text-sm">
            <span>Document</span>
            <FilterMultiSelect
              v-model="filters.documentIds"
              v-model:search="documentSearch"
              label="Documents"
              :options="documents.options.value"
              :is-loading="documents.isLoading.value"
              :error="documents.error.value"
              :has-more="documents.hasMore.value"
              :is-loading-more="documents.isLoadingMore.value"
              @load-more="documents.loadMore()"
              @retry="documents.retry()"
            />
          </div>
          <div class="space-y-1 text-sm">
            <span>Last processed by</span>
            <FilterMultiSelect
              v-model="filters.userIds"
              v-model:search="userSearch"
              label="Users"
              :options="users.options.value"
              :is-loading="users.isLoading.value"
              :error="users.error.value"
              :has-more="users.hasMore.value"
              :is-loading-more="users.isLoadingMore.value"
              @load-more="users.loadMore()"
              @retry="users.retry()"
            />
          </div>
          <div class="space-y-1 text-sm">
            <span>API key used</span>
            <FilterMultiSelect
              v-model="filters.apiKeyIds"
              v-model:search="apiKeySearch"
              label="API keys"
              :options="apiKeys.options.value"
              :is-loading="apiKeys.isLoading.value"
              :error="apiKeys.error.value"
              :has-more="apiKeys.hasMore.value"
              :is-loading-more="apiKeys.isLoadingMore.value"
              @load-more="apiKeys.loadMore()"
              @retry="apiKeys.retry()"
            />
          </div>
        </div>
        <p class="col-span-2 text-xs text-muted-foreground">
          Times use your local timezone. Documents match faces and text mentions on any page; user
          and API key refer to the last change.
        </p>
        <p v-if="filterError" class="col-span-2 text-sm text-destructive" role="alert">
          {{ filterError }}
        </p>
        <div
          v-if="active.length"
          class="col-span-2 flex flex-wrap items-center gap-2"
          aria-label="Active filters"
        >
          <Button
            v-for="chip in active"
            :key="`${chip.key}:${chip.value}`"
            type="button"
            variant="secondary"
            size="sm"
            class="h-auto max-w-full whitespace-normal break-all rounded-none py-1 text-left"
            :aria-label="`Remove ${chip.label}`"
            @click="removeFilter(chip.key, chip.value)"
          >
            {{ chip.label }} <X class="size-3 shrink-0" aria-hidden="true" />
          </Button>
          <Button type="button" variant="ghost" size="sm" @click="clearFilters()"
            >Clear all filters</Button
          >
        </div>
      </CardContent>
    </Card>
  </div>
</template>
