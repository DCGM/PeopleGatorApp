<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { Button } from '@/components/ui/button'

const route = useRoute()
const router = useRouter()

type OccurrenceType = 'names' | 'faces' | 'both'

const personId = computed(() => String(route.params.personId))
const page = ref(Math.max(1, Number(route.query.page) || 1))
const occurrences = ref<OccurrenceType>(
  route.query.occurrences === 'names' || route.query.occurrences === 'faces'
    ? route.query.occurrences
    : 'both',
)

function updateOccurrences() {
  page.value = 1
  updateRoute()
}

function updatePage(nextPage: number) {
  page.value = Math.max(1, nextPage)
  updateRoute()
}

function updateRoute() {
  void router.push({
    name: 'person-detail',
    params: { personId: personId.value },
    query: {
      ...(occurrences.value !== 'both' && { occurrences: occurrences.value }),
      ...(page.value > 1 && { page: String(page.value) }),
    },
  })
}
</script>

<template>
  <main class="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
    <header class="flex flex-col gap-5 border-b pb-7 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-xs font-semibold uppercase text-secondary">Person {{ personId }}</p>
        <h1 class="mt-2 font-semibold">Person detail</h1>
        <p class="mt-2 text-sm text-muted-foreground">Identity metadata and appearances across the library.</p>
      </div>
      <label class="grid gap-2 text-sm font-medium" for="occurrence-type">
        Show occurrences
        <select id="occurrence-type" v-model="occurrences" class="h-9 rounded-md border bg-background px-3 text-sm"
          @change="updateOccurrences">
          <option value="both">Names and faces</option>
          <option value="names">Names only</option>
          <option value="faces">Faces only</option>
        </select>
      </label>
    </header>

    <section class="py-7" aria-live="polite">
      <div class="flex items-center justify-between gap-4">
        <h2 class="text-xl font-semibold">Occurrences</h2>
        <span class="text-sm text-muted-foreground">Page {{ page }}</span>
      </div>
      <p class="mt-12 text-center text-sm text-muted-foreground">{{ occurrences === 'both' ? 'Name and face' :
        occurrences === 'names' ? 'Name' : 'Face' }} occurrences will appear here.</p>
      <div class="mt-10 flex justify-end gap-2">
        <Button variant="outline" :disabled="page <= 1" @click="updatePage(page - 1)">Previous</Button>
        <Button variant="outline" @click="updatePage(page + 1)">Next</Button>
      </div>
    </section>
  </main>
</template>
