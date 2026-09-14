<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { ref } from 'vue'
import DocumentCard from '@/components/custom/DocumentCard.vue'
import DocumentCardSkeleton from '@/components/custom/DocumentCardSkeleton.vue'
import DocumentSearchBar from '@/components/custom/DocumentSearchBar.vue'
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

const exampleResults = [
  { library: 'MZK', documentUuid: '3a4776ba-f7d2-4d7d-8822-bc192f2d650e', pageUuid: 'c585ee57-5d65-48b9-91e9-d2bb98b85f94', names: ['Anna Nováková', 'Jan Novák', 'Marie Dvořáková', 'Josef Svoboda', 'Karel Černý', 'Božena Veselá'] },
  { library: 'NKP', documentUuid: '226f94fd-5325-45ff-a009-b8db13898999', pageUuid: 'bd24b3d1-f185-4968-8c5d-9337e7b7367a', names: ['František Procházka', 'Alena Horáková', 'Václav Kučera', 'Emilie Němcová'] },
  { library: 'MU', documentUuid: 'c0fa0a77-0dbe-40db-986d-9e6fe3a243c2', pageUuid: '73cbe928-dbe9-47c4-9065-c732aa396b83', names: ['Ludvík Pokorný', 'Růžena Marková', 'Antonín Jelínek', 'Olga Králová', 'Jiří Růžička'] },
  { library: 'KVKLI', documentUuid: '90782736-a944-4b68-ad64-34914b6d27ab', pageUuid: 'f882369c-7a70-4e66-8350-eb4aa310489d', names: ['Josef Beneš', 'Marie Fialová', 'Jaroslav Sedláček'] },
  { library: 'MZK', documentUuid: '899dff56-72f4-448d-acba-388ba4b86fd8', pageUuid: '9f1e5643-1d69-4363-a128-da1449acbaa3', names: ['Kateřina Doležalová', 'Tomáš Zeman', 'Františka Kolářová', 'Alois Navrátil', 'Vlasta Čermáková', 'Petr Vaněk', 'Jana Blažková'] },
  { library: 'NKP', documentUuid: 'c562c0f2-8447-445e-aefd-e7539aec83d9', pageUuid: '3136431d-174c-45d0-ac87-03e7f8a37a88', names: ['Matěj Kříž', 'Ondřej Tichý', 'Šimon Bartoš', 'Marta Konečná'] },
  ...Array.from({ length: 20 }, (_, index) => {
    const sequence = index + 7
    const prefix = sequence.toString(16).padStart(8, '0')
    const libraries = ['MZK', 'NKP', 'MU', 'KVKLI']
    const nameGroups = [
      ['Eliška Urbanová', 'David Hájek', 'Tereza Šťastná'],
      ['Miroslav Čermák', 'Hana Krejčová', 'Radek Bureš', 'Irena Konečná'],
      ['Pavel Mareš', 'Zuzana Holubová', 'Daniel Janda', 'Ivana Beranová', 'Adam Vacek'],
      ['Veronika Křížová', 'Roman Blažek', 'Lenka Fojtíková'],
    ]

    return {
      library: libraries[index % libraries.length]!,
      documentUuid: `${prefix}-1000-4000-8000-${sequence.toString(16).padStart(12, '0')}`,
      pageUuid: `${prefix}-2000-4000-8000-${(sequence * 17).toString(16).padStart(12, '0')}`,
      names: nameGroups[index % nameGroups.length]!,
    }
  }),
]

const resultCount = exampleResults.length
const resultsPerPage = 10
const searchTerm = ref(typeof route.query.q === 'string' ? route.query.q : '')
const filters = ref(typeof route.query.filters === 'string' ? route.query.filters : '')
const page = ref(Math.max(1, Number(route.query.page) || 1))

function updateSearch(nextPage = 1) {
  page.value = nextPage
  void router.push({
    name: 'document-search',
    query: {
      ...(searchTerm.value && { q: searchTerm.value }),
      ...(filters.value && { filters: filters.value }),
      ...(page.value > 1 && { page: String(page.value) }),
    },
  })
}

</script>

<template>
  <main class="mx-auto w-full max-w-6xl md:px-4 px-2">
    <header class="pt-6 pb-4">
      <small class="font-semibold uppercase text-secondary">Scans index</small>
      <h1>Browse scans</h1>
    </header>

    <DocumentSearchBar v-model:search-term="searchTerm" :result-count="resultCount" />
    <section class="pt-6" aria-live="polite">
      <h2 class="mb-4">Search Results</h2>
      <Separator orientation="horizontal" />
      <div class="pt-6 grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        <RouterLink v-for="result in exampleResults" :key="result.pageUuid" class="group" :to="{
          name: 'document-page',
          params: {
            libraryId: result.library,
            documentId: result.documentUuid,
            pageId: result.pageUuid,
          },
        }">
          <DocumentCard :library="result.library" :document-uuid="result.documentUuid" :page-uuid="result.pageUuid"
            :names="result.names" />
        </RouterLink>
        <DocumentCardSkeleton />
      </div>
    </section>

    <Pagination class="pt-6" :page="page" :items-per-page="resultsPerPage" :total="resultCount"
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

    <footer class="pt-6 pb-4">
      <p class="text-center text-sm text-muted-foreground">
        PeopleGator
      </p>
    </footer>
  </main>
</template>
