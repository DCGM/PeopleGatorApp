<script setup lang="ts">
import { Check, ChevronRight, Database, Plus, Search, UserPlus, X } from '@lucide/vue'
import { computed, nextTick, ref, watch } from 'vue'

import type { SimilarPersonCandidate, SimilarPersonSource } from '@/components/custom/similar-people.types'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Item, ItemContent, ItemMedia, ItemTitle } from '@/components/ui/item'
import {
    Pagination,
    PaginationContent,
    PaginationItem,
    PaginationNext,
    PaginationPrevious,
} from '@/components/ui/pagination'
import { ScrollArea } from '@/components/ui/scroll-area'

const props = defineProps<{
    people: SimilarPersonCandidate[]
    assignedPersonId: string | null
    viewedPersonId: string | null
}>()

const emit = defineEmits<{
    preview: [person: SimilarPersonCandidate]
    assign: [person: SimilarPersonCandidate]
    'open-person': [personId: string]
    create: [person: SimilarPersonCandidate]
}>()

type Filter = 'all' | SimilarPersonSource

const filter = ref<Filter>('all')
const query = ref('')
const isCreateOpen = ref(false)
const newName = ref('')
const page = ref(1)
const listElement = ref<InstanceType<typeof ScrollArea> | null>(null)

const pageSize = 3

const filterOptions: { value: Filter; label: string }[] = [
    { value: 'all', label: 'All signals' },
    { value: 'page', label: 'On this page' },
    { value: 'database', label: 'Database' },
]

const filteredPeople = computed(() => {
    const normalizedQuery = query.value.trim().toLocaleLowerCase()
    return props.people.filter((person) => {
        const matchesFilter = filter.value === 'all' || person.source === filter.value
        const matchesQuery = !normalizedQuery || person.name.toLocaleLowerCase().includes(normalizedQuery)
        return matchesFilter && matchesQuery
    })
})

const pageCount = computed(() => Math.max(1, Math.ceil(filteredPeople.value.length / pageSize)))
const paginatedPeople = computed(() => {
    const start = (page.value - 1) * pageSize
    return filteredPeople.value.slice(start, start + pageSize)
})

watch([filter, query], () => {
    page.value = 1
})

watch(pageCount, (count) => {
    page.value = Math.min(page.value, count)
})

watch(page, async () => {
    await nextTick()
    const root = listElement.value?.$el as HTMLElement | undefined
    const viewport = root?.querySelector<HTMLElement>('[data-slot="scroll-area-viewport"]')
    if (viewport) viewport.scrollTop = 0
})

function initials(name: string) {
    return name.split(/\s+/).map((part) => part.charAt(0)).join('').slice(0, 2)
}

function openCreateForm() {
    newName.value = query.value.trim()
    isCreateOpen.value = true
}

function createPerson() {
    const name = newName.value.trim()
    if (!name) return

    emit('create', {
        id: name.toLocaleLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, ''),
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
        <div class="flex items-end justify-between gap-3">
            <h3 id="similar-title" class="text-lg">Similar people</h3>
            <div class="text-right font-mono text-[10px] leading-tight">
                <p class="font-semibold uppercase text-secondary">Reassign identity</p>
                <p class="text-muted-foreground">by face</p>
            </div>
        </div>

        <div class="mt-3 grid grid-cols-3 rounded-md border bg-muted/50 p-0.5" aria-label="Filter similar people">
            <button v-for="option in filterOptions" :key="option.value" type="button"
                class="min-w-0 px-2 py-1.5 text-xs transition-colors"
                :class="filter === option.value ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground hover:text-foreground'"
                :aria-pressed="filter === option.value" @click="filter = option.value">
                <span class="block truncate">{{ option.label }}</span>
            </button>
        </div>

        <div class="mt-3 flex gap-2">
            <label class="relative min-w-0 flex-1">
                <Search class="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                    aria-hidden="true" />
                <span class="sr-only">Search people</span>
                <Input v-model="query" class="pl-8 pr-8 font-mono text-xs" placeholder="Search people" />
                <button v-if="query" type="button"
                    class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    aria-label="Clear people search" @click="query = ''">
                    <X class="size-3.5" aria-hidden="true" />
                </button>
            </label>
            <Button type="button" size="sm" variant="outline" @click="openCreateForm">
                <Plus aria-hidden="true" />
                Add
            </Button>
        </div>

        <form v-if="isCreateOpen" class="mt-3 space-y-3 border border-secondary p-3" @submit.prevent="createPerson">
            <div class="flex items-center justify-between border-b pb-2">
                <strong class="flex items-center gap-2 text-sm">
                    <UserPlus class="size-4 text-secondary" />Create and assign person
                </strong>
                <Button type="button" size="icon-xs" variant="ghost" aria-label="Close create person form"
                    @click="isCreateOpen = false">
                    <X aria-hidden="true" />
                </Button>
            </div>
            <label class="block space-y-1">
                <span class="font-mono text-[10px] uppercase text-muted-foreground">Full name</span>
                <Input v-model="newName" required />
            </label>
            <div class="flex justify-end gap-2">
                <Button type="button" size="sm" variant="ghost" @click="isCreateOpen = false">Cancel</Button>
                <Button type="submit" size="sm" :disabled="!newName.trim()">
                    <Check />Create & assign
                </Button>
            </div>
        </form>

        <ScrollArea ref="listElement" class="mt-3 min-h-0 flex-1 pr-3" aria-live="polite">
            <div class="space-y-2 pb-1">
                <Item v-for="person in paginatedPeople" :key="person.id" variant="outline"
                    class="flex-nowrap gap-2 bg-card px-3 py-3 hover:border-accent"
                    :class="viewedPersonId === person.id && 'border-accent bg-accent/15 ring-1 ring-accent hover:bg-accent/15'">
                    <div class="flex min-w-0 flex-1 items-center gap-3">
                        <button type="button" class="shrink-0 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            :aria-label="`Preview ${person.name} on this page`"
                            :aria-pressed="viewedPersonId === person.id" @click="emit('preview', person)">
                            <ItemMedia>
                                <Avatar class="size-12">
                                    <AvatarImage v-if="person.portrait" :src="person.portrait" :alt="person.name"
                                        class="object-cover grayscale" />
                                    <AvatarFallback class="font-serif">{{ initials(person.name) }}</AvatarFallback>
                                </Avatar>
                            </ItemMedia>
                        </button>
                        <ItemContent class="min-w-0 gap-1">
                            <ItemTitle class="flex min-w-0 items-center gap-1.5">
                                <button type="button"
                                    class="group flex min-w-0 items-center gap-1 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                    :aria-label="`Open ${person.name}`" @click="emit('open-person', person.id)">
                                    <span class="truncate font-serif text-base">{{ person.name }}</span>
                                    <ChevronRight
                                        class="size-[1em] shrink-0 transition-transform group-hover:translate-x-1 group-focus-visible:translate-x-1"
                                        aria-hidden="true" />
                                </button>
                                <span v-if="person.source === 'database'"
                                    class="flex shrink-0 items-center gap-1 border px-1 py-0.5 font-mono text-[9px] uppercase text-muted-foreground">
                                    <Database class="size-2.5" />DB
                                </span>
                            </ItemTitle>
                            <button type="button"
                                class="space-y-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                :aria-label="`Preview ${person.name} details on this page`"
                                @click="emit('preview', person)">
                                <span class="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                                    <span><b class="text-foreground">{{ person.nerMentions }}</b> mentions</span>
                                    <span><b class="text-foreground">{{ person.detections }}</b> detections</span>
                                </span>
                                <span class="block font-mono text-[10px] text-accent">{{ person.score }}% face
                                    match</span>
                            </button>
                        </ItemContent>
                    </div>
                    <div class="flex shrink-0 items-center gap-1">
                        <Button type="button" size="xs"
                            :variant="assignedPersonId === person.id ? 'secondary' : 'outline'"
                            :aria-pressed="assignedPersonId === person.id" @click="emit('assign', person)">
                            <Check v-if="assignedPersonId === person.id" aria-hidden="true" />
                            {{ assignedPersonId === person.id ? 'Linked' : 'Assign' }}
                        </Button>
                    </div>
                </Item>

                <p v-if="filteredPeople.length === 0" class="py-6 text-center text-sm text-muted-foreground">
                    No matching people. Add a new identity instead.
                </p>
            </div>
        </ScrollArea>

        <Pagination v-if="filteredPeople.length > pageSize" v-model:page="page" :items-per-page="pageSize"
            :total="filteredPeople.length" class="mt-3 shrink-0 border-t pt-3">
            <PaginationContent v-slot="{ items }">
                <PaginationPrevious aria-label="Previous people page" />
                <template v-for="(item, index) in items" :key="item.type === 'page' ? item.value : `ellipsis-${index}`">
                    <PaginationItem v-if="item.type === 'page'" :value="item.value"
                        :aria-label="`People page ${item.value}`">
                        {{ item.value }}
                    </PaginationItem>
                </template>
                <PaginationNext aria-label="Next people page" />
            </PaginationContent>
        </Pagination>
    </section>
</template>
