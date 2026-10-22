<script setup lang="ts">
import { useAutomaticPagination } from '@/composables/automatic-pagination'
import { computed, ref } from 'vue'
import { relatedQuery, useSharedFilters } from '@/viewmodels/shared-filters'

import { useRoute, useRouter } from 'vue-router'
import { UserRound } from '@lucide/vue'

import PeopleCard from '@/components/custom/PeopleCard.vue'
import PeopleCardSkeleton from '@/components/custom/PeopleCardSkeleton.vue'
import PeopleSearchBar from '@/components/custom/PeopleSearchBar.vue'
import { Button } from '@/components/ui/button'
import Separator from '@/components/ui/separator/Separator.vue'
import { usePeopleSearch } from '@/viewmodels/people-search'
import { normalizeAssignmentFilter } from '@/viewmodels/assignment'
import { DEFAULT_SORT_KEYS, useRouteSort } from '@/lib/sorting'
import {
  PEOPLE_BROWSE_DEFAULT,
  PEOPLE_SORTS,
  RELEVANCE,
  scoredOptions,
} from '@/viewmodels/sort-options'

const route = useRoute()
const router = useRouter()
const shared = useSharedFilters()

const resultsPerPage = 12
function updateQuery(changes: import('vue-router').LocationQueryRaw) {
  void router.push({ query: { ...route.query, ...changes, cursor: undefined } })
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
  shared.params,
  computed(() => !shared.error.value),
  sort,
)
const listEnd = ref<HTMLElement | null>(null)
useAutomaticPagination({
  target: listEnd,
  hasNextPage,
  isFetching,
  error,
  enabled: computed(() => !shared.error.value),
  loadMore,
})
</script>

<template>
  <main class="mx-auto w-full max-w-6xl px-2 md:px-4">
    <header class="pb-4 pt-6">
      <small class="font-semibold uppercase text-secondary">People index</small>
      <h1>Browse people</h1>
    </header>

    <PeopleSearchBar
      v-model:search-term="searchTerm"
      v-model:assignment="assignment"
      v-model:sort="sort"
      :sort-options="sortOptions"
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
            query: relatedQuery(route),
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

    <div ref="listEnd" class="h-px" aria-hidden="true" />

    <div v-if="hasNextPage || isFetchingNextPage" class="flex justify-center pt-8">
      <Button type="button" variant="outline" :disabled="isFetching" @click="loadMore()">
        {{ isFetchingNextPage ? 'Loading people…' : 'Load more people' }}
      </Button>
    </div>

    <footer class="pb-4 pt-6">
      <p class="text-center text-sm text-muted-foreground">PeopleGator</p>
    </footer>
  </main>
</template>
