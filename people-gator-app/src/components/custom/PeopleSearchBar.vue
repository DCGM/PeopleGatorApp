<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { Search, SlidersHorizontal, X } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import FilterMultiSelect from '@/components/custom/FilterMultiSelect.vue'
import { Button } from '@/components/ui/button'
import FilterDateTimePicker from '@/components/custom/FilterDateTimePicker.vue'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import { emptyPeopleFilters, type PeopleProcessingFilters } from '@/viewmodels/people-filters'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
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

const props = defineProps<{
  resultCount: number
  hasMoreResults?: boolean
  filterError?: string
}>()

const searchTerm = defineModel<string>('searchTerm', { required: true })
const assignment = defineModel<AssignmentFilter>('assignment', { required: true })
const filters = defineModel<PeopleProcessingFilters>('processingFilters', {
  default: emptyPeopleFilters,
})
const expanded = ref(false)
const isDesktop = useMediaQuery('(min-width: 640px)')
const mobileExpanded = ref(false)
const filtersVisible = computed({
  get: () => isDesktop.value || mobileExpanded.value,
  set: (open: boolean) => {
    mobileExpanded.value = open
  },
})
const mobileToggleLabel = computed(() => {
  const label = mobileExpanded.value ? 'Hide filters' : 'Show filters'
  const count = active.value.length ? ` (${active.value.length} active)` : ''
  return `${label}${count}${props.filterError ? ' — invalid date range' : ''}`
})
const assignmentId = useId()
const advancedFilterCount = computed(
  () =>
    Number(Boolean(filters.value.touchedFrom)) +
    Number(Boolean(filters.value.touchedTo)) +
    Number(filters.value.userIds.length > 0) +
    Number(filters.value.apiKeyIds.length > 0),
)
const filterToggleLabel = computed(() => {
  const label = expanded.value ? 'Hide additional filters' : 'More filters'
  return advancedFilterCount.value ? `${label} (${advancedFilterCount.value} active)` : label
})
watch(
  () => props.filterError,
  (error) => {
    if (error) expanded.value = true
  },
  { immediate: true },
)
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
  <Card class="sticky top-13 z-20 gap-3 bg-background py-3">
    <CardContent class="px-3">
      <Collapsible v-model:open="filtersVisible" class="space-y-3">
        <InputGroup class="bg-muted/50">
          <InputGroupInput
            v-model="searchTerm"
            aria-label="Search people"
            placeholder="Search a person or alias…"
          />
          <InputGroupAddon><Search /></InputGroupAddon>
          <InputGroupAddon
            align="inline-end"
            class="hidden min-w-20 justify-end tabular-nums sm:flex"
          >
            {{ resultCount }}{{ hasMoreResults ? '+' : '' }} results
          </InputGroupAddon>
          <InputGroupAddon v-if="!isDesktop" align="inline-end">
            <CollapsibleTrigger as-child>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                class="bg-transparent hover:bg-transparent dark:hover:bg-transparent"
                :class="
                  filterError
                    ? 'text-destructive'
                    : active.length
                      ? 'text-primary'
                      : 'text-muted-foreground'
                "
                :aria-label="mobileToggleLabel"
                :title="mobileToggleLabel"
              >
                <X v-if="mobileExpanded" class="size-4" aria-hidden="true" />
                <SlidersHorizontal v-else class="size-4" aria-hidden="true" />
              </Button>
            </CollapsibleTrigger>
          </InputGroupAddon>
        </InputGroup>
        <CollapsibleContent class="space-y-3" aria-label="People filter controls">
          <Collapsible :open="isDesktop ? expanded : true" @update:open="expanded = $event">
            <div
              class="grid grid-cols-2 items-end gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
              aria-label="People filters"
            >
              <div class="min-w-0 space-y-1 text-sm">
                <label :for="assignmentId" class="font-medium">Assignment</label>
                <Select v-model="assignment">
                  <SelectTrigger
                    :id="assignmentId"
                    aria-label="Assignment"
                    class="w-full bg-muted/50 font-normal hover:bg-muted"
                  >
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
              </div>
              <div class="min-w-0 space-y-1 text-sm">
                <span class="font-medium">Document</span>
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
              <CollapsibleTrigger v-if="isDesktop" as-child>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  class="bg-transparent text-muted-foreground hover:bg-transparent hover:text-foreground dark:hover:bg-transparent"
                  :aria-label="filterToggleLabel"
                  :title="filterToggleLabel"
                >
                  <X v-if="expanded" class="size-4" aria-hidden="true" />
                  <SlidersHorizontal v-else class="size-4" aria-hidden="true" />
                </Button>
              </CollapsibleTrigger>
            </div>
            <CollapsibleContent
              class="mt-3 space-y-3 border-t pt-3"
              aria-label="Additional people filters"
            >
              <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <FilterDateTimePicker
                  v-model="filters.touchedFrom"
                  label="Last processed from"
                  :invalid="!!filterError"
                />
                <FilterDateTimePicker
                  v-model="filters.touchedTo"
                  label="Last processed to"
                  :invalid="!!filterError"
                />
                <div class="min-w-0 space-y-1 text-sm">
                  <span class="font-medium">Last processed by</span>
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
                <div class="min-w-0 space-y-1 text-sm">
                  <span class="font-medium">API key used</span>
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
              <p class="text-xs text-muted-foreground">
                Times use your local timezone. Documents match faces and text mentions on any page;
                user and API key refer to the last change.
              </p>
            </CollapsibleContent>
          </Collapsible>
          <p v-if="filterError" class="text-sm text-destructive" role="alert">{{ filterError }}</p>
          <div
            v-if="active.length"
            class="flex flex-wrap items-center gap-2"
            aria-label="Active filters"
          >
            <Button
              v-for="chip in active"
              :key="`${chip.key}:${chip.value}`"
              type="button"
              variant="secondary"
              size="sm"
              class="h-auto max-w-full whitespace-normal break-all py-1 text-left"
              :aria-label="`Remove ${chip.label}`"
              @click="removeFilter(chip.key, chip.value)"
            >
              {{ chip.label }} <X class="size-3 shrink-0" aria-hidden="true" />
            </Button>
            <Button type="button" variant="ghost" size="sm" @click="clearFilters()"
              >Clear all filters</Button
            >
          </div>
        </CollapsibleContent>
      </Collapsible>
    </CardContent>
  </Card>
</template>
