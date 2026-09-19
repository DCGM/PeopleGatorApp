<script setup lang="ts">
import { Check, Plus, Search, UserPlus, X } from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import type { AcceptableValue } from 'reka-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import SimilarPersonItem from '@/components/custom/SimilarPersonItem.vue'
import SimilarPersonItemSkeleton from '@/components/custom/SimilarPersonItemSkeleton.vue'
import type {
  SimilarPersonCandidate,
  SimilarPersonSource,
} from '@/components/custom/similar-people.types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

const props = defineProps<{
  people: SimilarPersonCandidate[]
  assignedPersonId: string | null
  viewedPersonId: string | null
  loading?: boolean
}>()

const emit = defineEmits<{
  preview: [person: SimilarPersonCandidate]
  assign: [person: SimilarPersonCandidate]
  create: [person: SimilarPersonCandidate]
}>()

type Filter = 'all' | SimilarPersonSource

const filter = ref<Filter>('all')
const query = defineModel<string>('searchTerm', { default: '' })
const isCreateOpen = ref(false)
const newName = ref('')
const visiblePageCount = ref(1)
const resultsElement = ref<HTMLElement | null>(null)

const mobilePageSize = 3
const minimumResultHeight = 120
const resultGap = 8
const isMobile = useMediaQuery('(max-width: 1023px)')
const resultsHeight = ref(0)
let resultsResizeObserver: ResizeObserver | undefined

const filterOptions: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All signals' },
  { value: 'page', label: 'On this page' },
  { value: 'database', label: 'Database' },
]

const filteredPeople = computed(() => {
  // Text matching belongs to the server: aliases can match even when the
  // returned primary name does not contain the typed term.
  return props.people.filter((person) => filter.value === 'all' || person.source === filter.value)
})

const pageSize = computed(() => {
  if (isMobile.value || resultsHeight.value === 0) return mobilePageSize
  return Math.max(
    1,
    Math.floor((resultsHeight.value + resultGap) / (minimumResultHeight + resultGap)),
  )
})
const visiblePeople = computed(() =>
  filteredPeople.value.slice(0, visiblePageCount.value * pageSize.value),
)
const hasMorePeople = computed(() => visiblePeople.value.length < filteredPeople.value.length)

watch([filter, query], () => {
  visiblePageCount.value = 1
})

onMounted(async () => {
  await nextTick()
  if (!resultsElement.value) return

  resultsHeight.value = resultsElement.value.getBoundingClientRect().height
  if (typeof ResizeObserver === 'undefined') return
  resultsResizeObserver = new ResizeObserver(([entry]) => {
    if (entry) resultsHeight.value = entry.contentRect.height
  })
  resultsResizeObserver.observe(resultsElement.value)
})

onBeforeUnmount(() => {
  resultsResizeObserver?.disconnect()
})

function openCreateForm() {
  newName.value = query.value.trim()
  isCreateOpen.value = true
}

function isFilter(value: AcceptableValue | AcceptableValue[]): value is Filter {
  return filterOptions.some((option) => option.value === value)
}

function updateFilter(value: AcceptableValue | AcceptableValue[]): void {
  if (isFilter(value)) filter.value = value
}

function createPerson() {
  const name = newName.value.trim()
  if (!name) return

  emit('create', {
    id: name
      .toLocaleLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, ''),
    name,
    score: 100,
    nerMentions: 0,
    detections: 1,
    source: 'page',
  })
  isCreateOpen.value = false
  query.value = ''
  newName.value = ''
}
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col border-t p-5" aria-labelledby="similar-title">
    <div class="flex items-start justify-between gap-3">
      <h3 id="similar-title">Similar people</h3>
      <small class="font-semibold uppercase text-secondary">Reassign identity</small>
    </div>

    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      :model-value="filter"
      class="w-full mt-2"
      aria-label="Filter similar people"
      @update:model-value="updateFilter"
    >
      <ToggleGroupItem
        v-for="option in filterOptions"
        :key="option.value"
        :value="option.value"
        class="min-w-0 flex-1 px-2 text-xs"
        :aria-label="option.label"
      >
        <span class="block truncate">{{ option.label }}</span>
      </ToggleGroupItem>
    </ToggleGroup>

    <div class="mt-3 flex flex-row items-center gap-2">
      <InputGroup class="w-full">
        <InputGroupAddon align="inline-start">
          <Search aria-hidden="true" />
        </InputGroupAddon>
        <InputGroupInput
          v-model="query"
          class="font-mono"
          placeholder="Search by name or alias"
          aria-label="Search people"
        />
        <InputGroupAddon align="inline-end">
          <InputGroupButton
            v-if="query"
            type="button"
            size="icon-sm"
            aria-label="Clear people search"
            @click="query = ''"
          >
            <X aria-hidden="true" />
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
      <Button
        type="button"
        size="sm"
        variant="outline"
        aria-label="Add person"
        @click="openCreateForm"
      >
        <Plus aria-hidden="true" />
        Add
      </Button>
    </div>
    <form
      v-if="isCreateOpen"
      class="mt-3 space-y-3 border border-secondary p-3"
      @submit.prevent="createPerson"
    >
      <div class="flex items-center justify-between border-b pb-2">
        <strong class="flex items-center gap-2 text-sm">
          <UserPlus class="size-4 text-secondary" />Create and assign person
        </strong>
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          aria-label="Close create person form"
          @click="isCreateOpen = false"
        >
          <X aria-hidden="true" />
        </Button>
      </div>
      <label class="block space-y-1">
        <span class="font-mono text-[10px] uppercase text-muted-foreground">Full name</span>
        <Input v-model="newName" required />
      </label>
      <div class="flex justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" @click="isCreateOpen = false"
          >Cancel</Button
        >
        <Button type="submit" size="sm" :disabled="!newName.trim()">
          <Check />Create & assign
        </Button>
      </div>
    </form>

    <div
      ref="resultsElement"
      class="mt-3 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1"
      aria-live="polite"
    >
      <SimilarPersonItem
        v-for="person in visiblePeople"
        :key="person.id"
        :person="person"
        class="shrink-0"
        :assigned="assignedPersonId === person.id"
        :viewed="viewedPersonId === person.id"
        @preview="emit('preview', $event)"
        @assign="emit('assign', $event)"
      />
      <SimilarPersonItemSkeleton v-if="props.loading" class="shrink-0" />

      <p
        v-if="filteredPeople.length === 0 && !props.loading"
        class="flex flex-1 items-center justify-center py-6 text-center text-sm text-muted-foreground"
      >
        No matching people. Add a new identity instead.
      </p>
    </div>

    <div v-if="hasMorePeople" class="mt-3 flex shrink-0 justify-center border-t pt-3">
      <Button type="button" size="sm" variant="outline" @click="visiblePageCount += 1">
        Load more people
      </Button>
    </div>
  </section>
</template>
