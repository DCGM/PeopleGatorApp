<script setup lang="ts">
import { usePeopleMerge } from '@/viewmodels/people-merge'
import { usePeopleCounts } from '@/viewmodels/people-counts'
import { usePeopleLifeDates } from '@/viewmodels/people-life-dates'
import { useAutomaticPagination } from '@/composables/automatic-pagination'
import { computed, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { useSharedFilters } from '@/viewmodels/shared-filters'

import { useRoute } from 'vue-router'
import { Merge, UserRound } from '@lucide/vue'

import PeopleCard from '@/components/custom/PeopleCard.vue'
import PersonSelectionControl from '@/components/custom/PersonSelectionControl.vue'
import PeopleCardSkeleton from '@/components/custom/PeopleCardSkeleton.vue'
import PeopleSearchBar from '@/components/custom/PeopleSearchBar.vue'
import PeopleFilters from '@/components/custom/PeopleFilters.vue'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import SelectedEvidenceActions from '@/components/custom/SelectedEvidenceActions.vue'
import { Button } from '@/components/ui/button'
import Separator from '@/components/ui/separator/Separator.vue'
import { usePeopleSearch } from '@/viewmodels/people-search'
import { usePeopleFilters } from '@/viewmodels/people-filters'
import { DEFAULT_SORT_KEYS, useRouteSort } from '@/lib/sorting'
import {
  PEOPLE_BROWSE_DEFAULT,
  PEOPLE_SORTS,
  RELEVANCE,
  scoredOptions,
} from '@/viewmodels/sort-options'

const route = useRoute()
const shared = useSharedFilters()
const counts = usePeopleCounts()
const lifeDates = usePeopleLifeDates()
const filtersValid = computed(
  () => !shared.error.value && !counts.error.value && !lifeDates.error.value,
)

const resultsPerPage = 12
// Filters sit in a sidebar from 1024px and in a drawer below that, like Documents.
const desktop = useMediaQuery('(min-width: 1024px)')
const filtersOpen = ref(false)
const { searchTerm, assignment } = usePeopleFilters()
const searching = computed(() => Boolean(searchTerm.value.trim()))
const sortOptions = computed(() => scoredOptions(PEOPLE_SORTS, searching.value))
const sort = useRouteSort(DEFAULT_SORT_KEYS, sortOptions, () =>
  searching.value ? RELEVANCE : PEOPLE_BROWSE_DEFAULT,
)

const {
  error,
  hasNextPage,
  isFetching,
  isFetchingNextPage,
  isLoading,
  loadMore,
  people,
  resultCount,
} = usePeopleSearch(
  searchTerm,
  assignment,
  resultsPerPage,
  computed(() => ({ ...shared.params.value, ...counts.params.value, ...lifeDates.params.value })),
  filtersValid,
  sort,
)
const selectionScope = computed(() =>
  JSON.stringify(
    Object.entries(route.query)
      .filter(([key]) => !['sort', 'dir'].includes(key))
      .sort(),
  ),
)
const { allowed, selectedIds, selected, busy, message, clear, toggle, add, merge } = usePeopleMerge(
  people,
  selectionScope,
  isFetching,
)
const listEnd = ref<HTMLElement | null>(null)
useAutomaticPagination({
  target: listEnd,
  hasNextPage,
  isFetching,
  error,
  enabled: filtersValid,
  loadMore,
})
</script>

<template>
  <main class="mx-auto w-full min-w-0 px-2 md:px-4 lg:flex lg:min-h-0 lg:flex-1 lg:flex-col">
    <h1 class="sr-only">People</h1>

    <!-- From 1024px the page fills the viewport: filters and results scroll separately. -->
    <div class="pt-3 lg:flex lg:min-h-0 lg:flex-1 lg:gap-4">
      <aside v-if="desktop" class="w-60 shrink-0 overflow-y-auto pb-4" aria-label="People filters">
        <PeopleFilters />
      </aside>
      <div class="flex min-w-0 flex-col lg:min-h-0 lg:flex-1">
        <PeopleSearchBar
          v-model:search-term="searchTerm"
          v-model:filters-open="filtersOpen"
          v-model:sort="sort"
          :sort-options="sortOptions"
          :result-count="resultCount"
        />

        <SelectedEvidenceActions
          v-if="allowed && selected.length"
          :count="selected.length"
          :busy="busy"
          singular="person"
          plural="people"
          label="Selected person actions"
          clear-last
          @clear="clear"
        >
          <template #description>
            <span v-if="busy" role="status">Merging…</span>
            <span v-else-if="message" role="alert">{{ message }}</span>
          </template>
          <Button
            type="button"
            size="sm"
            class="max-w-full"
            :disabled="busy || isFetching || selected.length < 2"
            @click="merge('last')"
          >
            <Merge aria-hidden="true" /><span class="truncate"
              >Last selected ({{ selected[selected.length - 1]?.name }})</span
            >
          </Button>
          <Button
            type="button"
            size="sm"
            class="max-w-full"
            :disabled="busy || isFetching || selected.length < 2"
            @click="merge('first')"
          >
            <Merge aria-hidden="true" /><span class="truncate"
              >First selected ({{ selected[0]?.name }})</span
            >
          </Button>
        </SelectedEvidenceActions>
        <div
          class="min-w-0 lg:min-h-0 lg:flex-1 lg:overflow-y-auto"
          :class="{ 'pb-56 sm:pb-32': allowed && selected.length }"
        >
          <p
            v-if="!selected.length && message"
            :role="message === 'People merged.' ? 'status' : 'alert'"
          >
            {{ message }}
          </p>

          <section class="stable-search-results pt-6" aria-live="polite">
            <h2 class="mb-4">Search Results</h2>
            <Separator orientation="horizontal" />

            <div
              v-if="people.length || isLoading"
              class="grid gap-0 pt-6 sm:grid-cols-2 xl:grid-cols-3 min-[1800px]:grid-cols-4"
            >
              <div v-for="person in people" :key="person.id" class="group relative min-w-0">
                <RouterLink
                  v-if="!allowed || !selectedIds.size"
                  class="absolute inset-0 z-10 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                  :aria-label="`Open ${person.name}`"
                  :to="{
                    name: 'person-detail',
                    params: { personId: person.id },
                  }"
                />
                <button
                  v-else
                  type="button"
                  class="absolute inset-0 z-10 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                  :disabled="busy || isFetching"
                  :aria-label="
                    selectedIds.has(person.id)
                      ? `${person.name} is selected`
                      : `Add ${person.name} to selection`
                  "
                  @click="add(person.id, $event)"
                ></button>
                <PersonSelectionControl
                  v-if="allowed"
                  :name="person.name"
                  :selected="selectedIds.has(person.id)"
                  :disabled="busy || isFetching"
                  @toggle="toggle(person.id, $event)"
                />
                <PeopleCard
                  :selected="allowed && selectedIds.has(person.id)"
                  :thumbnail-face-id="person.thumbnailFaceId"
                  :name="person.name"
                  :faces="person.faces"
                  :names="person.names"
                  :life-span="person.lifeSpan"
                  :count-details="person.countDetails"
                />
              </div>
              <PeopleCardSkeleton
                v-for="index in isLoading || isFetchingNextPage ? 3 : 0"
                :key="`loading-${index}`"
              />
            </div>

            <div
              v-else-if="error"
              class="flex flex-col items-center py-16 text-center text-destructive"
            >
              <UserRound class="mb-3 size-8" aria-hidden="true" />
              <p class="text-sm">Could not load people.</p>
            </div>
            <div v-else class="flex flex-col items-center py-16 text-center text-muted-foreground">
              <UserRound class="mb-3 size-8" aria-hidden="true" />
              <p class="text-sm">No people match this search.</p>
            </div>
            <div ref="listEnd" class="h-px" aria-hidden="true" />
          </section>

          <div v-if="hasNextPage || isFetchingNextPage" class="flex justify-center pt-8">
            <Button type="button" variant="outline" :disabled="isFetching" @click="loadMore()">
              {{ isFetchingNextPage ? 'Loading people…' : 'Load more people' }}
            </Button>
          </div>
          <footer class="pb-4 pt-6">
            <p class="text-center text-sm text-muted-foreground">PeopleGator</p>
          </footer>
        </div>
      </div>
    </div>
    <Sheet v-if="!desktop" v-model:open="filtersOpen">
      <SheetContent side="left" class="overflow-y-auto" :aria-describedby="undefined">
        <SheetHeader><SheetTitle>Filters</SheetTitle></SheetHeader>
        <div class="px-4 pb-4"><PeopleFilters /></div>
      </SheetContent>
    </Sheet>
  </main>
</template>
