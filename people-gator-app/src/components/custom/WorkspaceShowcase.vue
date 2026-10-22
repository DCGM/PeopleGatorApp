<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { Globe, SlidersHorizontal, Moon, Sun } from '@lucide/vue'
import { useDark, useToggle } from '@vueuse/core'
import { relatedQuery } from '@/viewmodels/shared-filters'
import PeopleGatorIcon from './PeopleGatorIcon'
import TopBar from './TopBar.vue'
import FilterMultiSelect from './FilterMultiSelect.vue'
import FilterSingleSelect from './FilterSingleSelect.vue'
import FilterDateTimePicker from './FilterDateTimePicker.vue'
import ActiveFilters, { type ActiveFilter } from './ActiveFilters.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarSeparator,
  SidebarTrigger,
} from '@/components/ui/sidebar'
import WorkspaceNavigation from './WorkspaceNavigation.vue'

// Deliberately disconnected from route filters, API queries and persistence (#60).
const route = useRoute()
const mode = ref('global')
const dark = useDark()
const toggleDark = useToggle(dark)
const username = import.meta.env.VITE_API_USERNAME || 'test'
const fields = reactive([
  {
    key: 'library',
    label: 'Library',
    selected: ['archive'],
    search: '',
    options: [
      { id: 'archive', label: 'City archive' },
      { id: 'collection', label: 'Family collection' },
    ],
  },
  {
    key: 'document',
    label: 'Document',
    selected: ['register'],
    search: '',
    options: [
      { id: 'register', label: 'Register 12' },
      { id: 'album', label: 'Photo album' },
    ],
  },
  {
    key: 'page',
    label: 'Page',
    selected: [] as string[],
    search: '',
    options: [
      { id: 'page-1', label: 'Register 12 · Page 1' },
      { id: 'page-2', label: 'Register 12 · Page 2' },
    ],
  },
  {
    key: 'user',
    label: 'Last user',
    selected: [] as string[],
    search: '',
    options: [
      { id: 'reviewer', label: 'Demo reviewer' },
      { id: 'editor', label: 'Demo editor' },
    ],
  },
  {
    key: 'key',
    label: 'Last API key',
    selected: ['importer'],
    search: '',
    options: [
      { id: 'importer', label: 'Archive importer' },
      { id: 'ocr', label: 'OCR worker' },
    ],
  },
])
const from = ref('')
const to = ref('')
const filters = computed<ActiveFilter[]>(() => [
  ...fields.flatMap((field) =>
    field.selected.map((value) => ({
      key: field.key,
      value,
      label: `${field.label}: ${field.options.find((option) => option.id === value)?.label ?? value}`,
    })),
  ),
  ...(from.value
    ? [{ key: 'from', value: from.value, label: `Modified from: ${from.value.replace('T', ' ')}` }]
    : []),
  ...(to.value
    ? [{ key: 'to', value: to.value, label: `Modified to: ${to.value.replace('T', ' ')}` }]
    : []),
])
function remove(filter: ActiveFilter) {
  if (filter.key === 'from') from.value = ''
  else if (filter.key === 'to') to.value = ''
  else {
    const field = fields.find((field) => field.key === filter.key)
    if (field) field.selected = field.selected.filter((value) => value !== filter.value)
  }
}
function clear() {
  fields.forEach((field) => {
    field.selected = []
  })
  from.value = ''
  to.value = ''
}
</script>

<template>
  <SidebarProvider
    :default-open="true"
    style="--sidebar-width: 19rem"
    class="bg-background text-foreground"
  >
    <Sidebar>
      <SidebarHeader>
        <div class="flex items-center gap-2">
          <RouterLink
            :to="{ name: 'document-list', query: relatedQuery(route) }"
            class="flex min-w-0 flex-1 items-center gap-2 p-2"
            aria-label="PeopleGator"
          >
            <PeopleGatorIcon class="size-9 shrink-0" aria-hidden="true" stroke-width="1" />
            <span class="font-heading text-xl">PeopleGator</span>
          </RouterLink>
          <SidebarTrigger />
        </div>
      </SidebarHeader>
      <SidebarContent>
        <WorkspaceNavigation />
        <SidebarSeparator />
        <SidebarGroup>
          <SidebarGroupLabel class="flex justify-between"
            >Workspace <Badge variant="outline">Preview</Badge></SidebarGroupLabel
          >
          <div class="flex w-full flex-row flex-wrap gap-2 p-2">
            <FilterSingleSelect
              v-model="mode"
              label="Workspace"
              :options="[
                { value: 'global', label: 'Global' },
                { value: 'local', label: 'Local' },
              ]"
            />
          </div>
          <p class="px-2 pb-2 text-xs text-muted-foreground">
            Visual demo · settings do not filter results.
          </p>
          <template v-if="mode === 'global'">
            <div class="flex items-start gap-2 px-2 py-3 text-sm text-muted-foreground">
              <Globe class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <span>Explore all accessible data.</span>
            </div>
            <Button variant="outline" class="mx-2" @click="mode = 'local'"
              ><SlidersHorizontal aria-hidden="true" />Configure Local Workspace</Button
            >
          </template>
          <template v-else>
            <SidebarGroupLabel>Local Workspace</SidebarGroupLabel>
            <div
              class="flex w-full min-w-0 flex-row flex-wrap gap-2 p-2"
              aria-label="Workspace sample filters"
            >
              <FilterMultiSelect
                v-for="field in fields"
                :key="field.key"
                v-model="field.selected"
                v-model:search="field.search"
                :label="field.label"
                :options="
                  field.options.filter((option) =>
                    option.label.toLowerCase().includes(field.search.toLowerCase()),
                  )
                "
                class="max-w-full flex-none"
              />
              <FilterDateTimePicker v-model="from" label="Modified from" />
              <FilterDateTimePicker v-model="to" label="Modified to" />
            </div>
            <div v-if="filters.length" class="min-w-0 px-2 pb-2">
              <SidebarGroupLabel>Sample filters</SidebarGroupLabel>
              <ActiveFilters
                :filters="filters"
                clear-label="Clear filters"
                @remove="remove"
                @clear="clear"
              />
            </div>
          </template>
        </SidebarGroup>
      </SidebarContent>
      <SidebarSeparator />
      <SidebarFooter>
        <div class="flex items-center gap-3 p-2">
          <Avatar
            ><AvatarFallback>{{ username.slice(0, 2).toUpperCase() }}</AvatarFallback></Avatar
          >
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-medium">{{ username }}</p>
            <p class="text-xs text-muted-foreground">Configured account</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            :aria-label="dark ? 'Use light theme' : 'Use dark theme'"
            @click="toggleDark()"
            ><Sun v-if="dark" aria-hidden="true" /><Moon v-else aria-hidden="true"
          /></Button>
        </div>
      </SidebarFooter>
    </Sidebar>
    <SidebarInset class="min-w-0">
      <TopBar>
        <template #toggle><SidebarTrigger /></template>
        <template #workspace>
          <Badge variant="outline" class="shrink-0">Sidebar demo</Badge>
          <Button
            variant="outline"
            size="sm"
            @click="mode = mode === 'global' ? 'local' : 'global'"
          >
            <Globe v-if="mode === 'global'" aria-hidden="true" /><SlidersHorizontal
              v-else
              aria-hidden="true"
            />
            {{ mode === 'global' ? 'Global' : `Local · ${filters.length}` }}
          </Button>
        </template>
      </TopBar>
      <div
        v-if="mode === 'local' && filters.length"
        class="px-4 pb-2"
        aria-label="Workspace sample summary"
      >
        <ActiveFilters
          :filters="filters"
          clear-label="Clear filters"
          @remove="remove"
          @clear="clear"
        />
      </div>
      <slot />
    </SidebarInset>
  </SidebarProvider>
</template>
