<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { UserRound } from '@lucide/vue'

import PeopleCard from '@/components/custom/PeopleCard.vue'
import PeopleCardSkeleton from '@/components/custom/PeopleCardSkeleton.vue'
import PeopleSearchBar from '@/components/custom/PeopleSearchBar.vue'
import { Button } from '@/components/ui/button'
import Separator from '@/components/ui/separator/Separator.vue'
import { usePeopleSearch } from '@/query/people-search'

const route = useRoute()
const router = useRouter()

const resultsPerPage = 12
const searchTerm = ref(typeof route.query.q === 'string' ? route.query.q : '')
const filters = ref(typeof route.query.filters === 'string' ? route.query.filters : 'all')

const { error, hasNextPage, isFetchingNextPage, isLoading, loadMore, people, resultCount } =
  usePeopleSearch(searchTerm, filters, resultsPerPage)

function updateSearch() {
  void router.push({
    name: 'people-search',
    query: {
      ...(searchTerm.value && { q: searchTerm.value }),
      ...(filters.value !== 'all' && { filters: filters.value }),
    },
  })
}
</script>

<template>
  <main class="mx-auto w-full max-w-6xl px-2 md:px-4">
    <header class="pb-4 pt-6">
      <small class="font-semibold uppercase text-secondary">People index</small>
      <h1>Browse people</h1>
    </header>

    <PeopleSearchBar
      v-model:search-term="searchTerm"
      v-model:filters="filters"
      :result-count="resultCount"
      :has-more-results="hasNextPage"
      @update:search-term="updateSearch()"
      @update:filters="updateSearch()"
    />

    <section class="pt-6" aria-live="polite">
      <h2 class="mb-4">Search Results</h2>
      <Separator orientation="horizontal" />

      <div v-if="people.length || isLoading" class="grid gap-0 pt-6 sm:grid-cols-2 lg:grid-cols-3">
        <RouterLink
          v-for="person in people"
          :key="person.id"
          class="group min-w-0"
          :to="{ name: 'person-detail', params: { personId: person.id } }"
        >
          <PeopleCard :name="person.name" :faces="person.faces" :names="person.names" />
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
