<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useEvidenceFilters, relatedEvidenceQuery } from '@/viewmodels/evidence-filters'
import { useLinkStateFilter } from '@/composables/link-state-filter'

import { useRoute, useRouter } from 'vue-router'
import { UserRound } from '@lucide/vue'

import PeopleCard from '@/components/custom/PeopleCard.vue'
import PeopleCardSkeleton from '@/components/custom/PeopleCardSkeleton.vue'
import PeopleSearchBar from '@/components/custom/PeopleSearchBar.vue'
import { Button } from '@/components/ui/button'
import Separator from '@/components/ui/separator/Separator.vue'
import { usePeopleSearch } from '@/viewmodels/people-search'
import { readPeopleFilters, peopleFiltersUrl } from '@/viewmodels/people-filters'
import { normalizeAssignmentFilter } from '@/viewmodels/assignment'
import { DEFAULT_SORT_KEYS, useRouteSort } from '@/lib/sorting'
import {
  PEOPLE_BROWSE_DEFAULT,
  PEOPLE_SORTS,
  RELEVANCE,
  scoredOptions,
} from '@/viewmodels/sort-options'

const linkStates = useLinkStateFilter()
const route = useRoute()
const router = useRouter()
const evidence = useEvidenceFilters()

const resultsPerPage = 12
function updateQuery(changes: import('vue-router').LocationQueryRaw) {
  void router.push({ query: { ...route.query, ...changes, page: undefined, cursor: undefined } })
}
const searchTerm = computed({
  get: () => (typeof route.query.q === 'string' ? route.query.q : ''),
  set: (q: string) => updateQuery({ q: q || undefined }),
})
const assignment = computed({
  get: () => normalizeAssignmentFilter(route.query.assignment ?? route.query.filters),
  set: (value) =>
    updateQuery({ assignment: value === 'all' ? undefined : value, filters: undefined }),
})
const processingState = ref(readPeopleFilters(route.query))
watch(
  () => route.query,
  (query) => {
    processingState.value = readPeopleFilters(query)
  },
)
const processingFilters = computed({
  get: () => processingState.value,
  set: (value) => {
    processingState.value = value
    updateQuery({
      touched_from: undefined,
      touched_to: undefined,
      touched_by: undefined,
      api_key: undefined,
      document: undefined,
      evidence_document: undefined,
      ...peopleFiltersUrl(value),
    })
  },
})

const searching = computed(() => Boolean(searchTerm.value.trim()))
const sortOptions = computed(() => scoredOptions(PEOPLE_SORTS, searching.value))
const sort = useRouteSort(DEFAULT_SORT_KEYS, sortOptions, () =>
  searching.value ? RELEVANCE : PEOPLE_BROWSE_DEFAULT,
)

const {
  error,
  filterError,
  hasNextPage,
  isFetchingNextPage,
  isLoading,
  loadMore,
  people,
  resultCount,
} = usePeopleSearch(
  searchTerm,
  assignment,
  resultsPerPage,
  processingFilters,
  linkStates,
  evidence.params,
  computed(() => !evidence.error.value),
  sort,
)
</script>

<template>
  <main class="mx-auto w-full max-w-6xl px-2 md:px-4">
    <header class="pb-4 pt-6">
      <small class="font-semibold uppercase text-secondary">People index</small>
      <h1>Browse people</h1>
    </header>

    <PeopleSearchBar
      v-model:link-states="linkStates"
      v-model:search-term="searchTerm"
      v-model:assignment="assignment"
      v-model:processing-filters="processingFilters"
      v-model:sort="sort"
      :sort-options="sortOptions"
      :filter-error="filterError"
      :result-count="resultCount"
    />

    <section class="stable-search-results pt-6" aria-live="polite">
      <h2 class="mb-4">Search Results</h2>
      <Separator orientation="horizontal" />

      <div v-if="people.length || isLoading" class="grid gap-0 pt-6 sm:grid-cols-2 lg:grid-cols-3">
        <RouterLink
          v-for="person in people"
          :key="person.id"
          class="group min-w-0"
          :to="{
            name: 'person-detail',
            params: { personId: person.id },
            query: relatedEvidenceQuery(route, {
              origin_matched_face: undefined,
              origin_reference_face: undefined,
            }),
          }"
        >
          <PeopleCard
            :thumbnail-face-id="person.thumbnailFaceId"
            :name="person.name"
            :faces="person.faces"
            :names="person.names"
          />
        </RouterLink>
        <PeopleCardSkeleton
          v-for="index in isLoading || isFetchingNextPage ? 3 : 0"
          :key="`loading-${index}`"
        />
      </div>

      <div v-else-if="error" class="flex flex-col items-center py-16 text-center text-destructive">
        <UserRound class="mb-3 size-8" aria-hidden="true" />
        <p class="text-sm">Could not load people.</p>
      </div>
      <div v-else class="flex flex-col items-center py-16 text-center text-muted-foreground">
        <UserRound class="mb-3 size-8" aria-hidden="true" />
        <p class="text-sm">No people match this search.</p>
      </div>
    </section>

    <div v-if="hasNextPage || isFetchingNextPage" class="flex justify-center pt-8">
      <Button type="button" variant="outline" :disabled="isFetchingNextPage" @click="loadMore()">
        {{ isFetchingNextPage ? 'Loading people…' : 'Load more people' }}
      </Button>
    </div>

    <footer class="pb-4 pt-6">
      <p class="text-center text-sm text-muted-foreground">PeopleGator</p>
    </footer>
  </main>
</template>
