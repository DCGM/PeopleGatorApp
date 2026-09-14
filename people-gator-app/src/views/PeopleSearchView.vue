<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { UserRound } from '@lucide/vue'

import PeopleCard from '@/components/custom/PeopleCard.vue'
import PeopleCardSkeleton from '@/components/custom/PeopleCardSkeleton.vue'
import PeopleSearchBar from '@/components/custom/PeopleSearchBar.vue'
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'
import Separator from '@/components/ui/separator/Separator.vue'

const route = useRoute()
const router = useRouter()

const basePeople = [
  ['anna-novakova', 'Anna Nováková', 'Anna Novák', 8, 14, ['MZK', 'NKP']],
  ['jan-novak', 'Jan Novák', 'Johann Nowak', 5, 11, ['MZK', 'MU']],
  ['marie-dvorakova', 'Marie Dvořáková', 'M. Dvořáková', 3, 9, ['NKP']],
  ['josef-svoboda', 'Josef Svoboda', 'J. Svoboda', 7, 6, ['KVKLI', 'MZK']],
  ['karel-cerny', 'Karel Černý', 'Karl Czerny', 4, 12, ['MU', 'NKP']],
  ['bozena-vesela', 'Božena Veselá', 'B. Veselá', 6, 8, ['MZK']],
] as const

const generatedNames = [
  'František Procházka',
  'Alena Horáková',
  'Václav Kučera',
  'Emilie Němcová',
  'Ludvík Pokorný',
  'Růžena Marková',
  'Antonín Jelínek',
  'Olga Králová',
  'Jiří Růžička',
  'Josef Beneš',
]

const examplePeople = [
  ...basePeople.map(([id, name, alias, faces, names, libraries]) => ({
    id,
    name,
    aliases: [alias],
    faces,
    names,
    libraries: [...libraries],
  })),
  ...Array.from({ length: 20 }, (_, index) => {
    const name = generatedNames[index % generatedNames.length]!
    const surname = name.split(' ').pop()
    return {
      id: `${name.toLocaleLowerCase('cs').replace(/\s+/g, '-')}-${index + 1}`,
      name,
      aliases: [`${name.charAt(0)}. ${surname}`],
      faces: (index * 3) % 9,
      names: 3 + ((index * 5) % 14),
      libraries: [['MZK'], ['NKP', 'MZK'], ['MU'], ['KVKLI', 'NKP']][index % 4]!,
    }
  }),
]

const resultsPerPage = 12
const searchTerm = ref(typeof route.query.q === 'string' ? route.query.q : '')
const filters = ref(typeof route.query.filters === 'string' ? route.query.filters : 'all')
const page = ref(Math.max(1, Number(route.query.page) || 1))

const filteredPeople = computed(() => {
  const query = searchTerm.value.trim().toLocaleLowerCase('cs')

  return examplePeople.filter((person) => {
    const matchesQuery =
      !query ||
      [person.name, ...person.aliases].some((name) =>
        name.toLocaleLowerCase('cs').includes(query),
      )
    const matchesFilter =
      filters.value === 'all' ||
      (filters.value === 'faces' ? person.faces > 0 : person.names > 0)

    return matchesQuery && matchesFilter
  })
})

const pagedPeople = computed(() => {
  const start = (page.value - 1) * resultsPerPage
  return filteredPeople.value.slice(start, start + resultsPerPage)
})

function updateSearch(nextPage = 1) {
  page.value = nextPage
  void router.push({
    name: 'people-search',
    query: {
      ...(searchTerm.value && { q: searchTerm.value }),
      ...(filters.value !== 'all' && { filters: filters.value }),
      ...(page.value > 1 && { page: String(page.value) }),
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

    <PeopleSearchBar v-model:search-term="searchTerm" v-model:filters="filters" :result-count="filteredPeople.length"
      @update:search-term="updateSearch()" @update:filters="updateSearch()" />

    <section class="pt-6" aria-live="polite">
      <h2 class="mb-4">Search Results</h2>
      <Separator orientation="horizontal" />

      <div v-if="pagedPeople.length" class="grid gap-0 pt-6 sm:grid-cols-2 lg:grid-cols-3">
        <RouterLink v-for="person in pagedPeople" :key="person.id" class="group"
          :to="{ name: 'person-detail', params: { personId: person.id } }">
          <PeopleCard :name="person.name" :faces="person.faces" :names="person.names" />
        </RouterLink>
        <PeopleCardSkeleton />
      </div>

      <div v-else class="flex flex-col items-center py-16 text-center text-muted-foreground">
        <UserRound class="mb-3 size-8" aria-hidden="true" />
        <p class="text-sm">No people match this search.</p>
      </div>
    </section>

    <Pagination class="pt-8" :page="page" :items-per-page="resultsPerPage" :total="filteredPeople.length"
      @update:page="updateSearch">
      <PaginationContent v-slot="{ items }">
        <PaginationPrevious />
        <template v-for="(item, index) in items" :key="item.type === 'page' ? item.value : `ellipsis-${index}`">
          <PaginationItem v-if="item.type === 'page'" :value="item.value" :is-active="item.value === page">
            {{ item.value }}
          </PaginationItem>
          <PaginationEllipsis v-else :index="index" />
        </template>
        <PaginationNext />
      </PaginationContent>
    </Pagination>

    <footer class="pb-4 pt-6">
      <p class="text-center text-sm text-muted-foreground">PeopleGator</p>
    </footer>
  </main>
</template>
