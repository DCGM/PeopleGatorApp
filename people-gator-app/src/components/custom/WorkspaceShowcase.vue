<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Globe, SlidersHorizontal, Moon, Sun, ChevronsUpDown } from '@lucide/vue'
import { useDark, useToggle } from '@vueuse/core'
import { SelectTrigger as WorkspaceModeTrigger } from 'reka-ui'
import WorkspaceSidebarBrand from './WorkspaceSidebarBrand.vue'
import TopBar from './TopBar.vue'
import WorkspaceFilterBuilder, { type WorkspaceFilterSelection } from './WorkspaceFilterBuilder.vue'
import ActiveFilters, { type ActiveFilter } from './ActiveFilters.vue'
import WorkspaceSidebarToggle from './WorkspaceSidebarToggle.vue'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarSeparator,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from '@/components/ui/sidebar'
import WorkspaceNavigation from './WorkspaceNavigation.vue'

// Deliberately disconnected from route filters, API queries and persistence (#60).
const mode = ref('global')
const dark = useDark()
const toggleDark = useToggle(dark)
const username = import.meta.env.VITE_API_USERNAME || 'test'
const fields = reactive([
  {
    key: 'library',
    label: 'Library',
    selected: [] as string[],
    options: [
      { id: 'archive', label: 'City archive' },
      { id: 'collection', label: 'Family collection' },
    ],
  },
  {
    key: 'document',
    label: 'Document',
    selected: [] as string[],
    options: [
      { id: 'register', label: 'Register 12' },
      { id: 'album', label: 'Photo album' },
    ],
  },
  {
    key: 'page',
    label: 'Page',
    selected: [] as string[],
    options: [
      { id: 'page-1', label: 'Register 12 · Page 1' },
      { id: 'page-2', label: 'Register 12 · Page 2' },
    ],
  },
  {
    key: 'user',
    label: 'Last user',
    selected: [] as string[],
    options: [
      { id: 'reviewer', label: 'Demo reviewer' },
      { id: 'editor', label: 'Demo editor' },
    ],
  },
  {
    key: 'key',
    label: 'Last API key',
    selected: [] as string[],
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
function updateFilter(filter: WorkspaceFilterSelection) {
  const field = fields.find((field) => field.key === filter.key)
  if (field) field.selected = [...filter.values]
  else if (filter.key === 'from') from.value = filter.date
  else if (filter.key === 'to') to.value = filter.date
}
</script>

<template>
  <SidebarProvider
    :default-open="true"
    style="--sidebar-width: 19rem"
    class="bg-background text-foreground"
  >
    <Sidebar collapsible="icon" class="overflow-hidden">
      <SidebarHeader>
        <WorkspaceSidebarBrand />
      </SidebarHeader>
      <SidebarContent class="overflow-hidden">
        <ScrollArea class="min-h-0 w-full flex-1 [&_[data-slot=scroll-area-viewport]>div]:!block">
          <WorkspaceNavigation />
          <SidebarSeparator class="mx-0 w-full" />
          <SidebarGroup>
            <SidebarMenu>
              <SidebarMenuItem>
                <Select v-model="mode">
                  <WorkspaceModeTrigger as-child aria-label="Workspace mode">
                    <SidebarMenuButton :tooltip="mode === 'global' ? 'Global' : 'Local'">
                      <Globe v-if="mode === 'global'" aria-hidden="true" />
                      <SlidersHorizontal v-else aria-hidden="true" />
                      <span class="group-data-[collapsible=icon]:hidden">{{
                        mode === 'global' ? 'Global' : 'Local'
                      }}</span>
                      <ChevronsUpDown
                        class="ml-auto group-data-[collapsible=icon]:hidden"
                        aria-hidden="true"
                      />
                    </SidebarMenuButton>
                  </WorkspaceModeTrigger>
                  <SelectContent>
                    <SelectItem value="global">Global</SelectItem>
                    <SelectItem value="local">Local</SelectItem>
                  </SelectContent>
                </Select>
              </SidebarMenuItem>
            </SidebarMenu>
            <div class="min-w-0 group-data-[collapsible=icon]:hidden">
              <template v-if="mode === 'local'">
                <div class="min-w-0 py-2">
                  <WorkspaceFilterBuilder
                    :fields="fields"
                    :from="from"
                    :to="to"
                    @change="updateFilter"
                  />
                </div>
                <div v-if="filters.length" class="min-w-0 px-2 pb-2">
                  <ActiveFilters
                    :filters="filters"
                    clear-label="Clear filters"
                    @remove="remove"
                    @clear="clear"
                  />
                </div>
              </template>
            </div>
          </SidebarGroup>
        </ScrollArea>
      </SidebarContent>
      <SidebarSeparator class="mx-0 w-full" />
      <SidebarFooter>
        <div
          class="flex items-center gap-3 p-2 group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:px-0"
        >
          <Avatar
            ><AvatarFallback>{{ username.slice(0, 2).toUpperCase() }}</AvatarFallback></Avatar
          >
          <div class="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
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
        <template #toggle><WorkspaceSidebarToggle /></template>
      </TopBar>
      <slot />
    </SidebarInset>
  </SidebarProvider>
</template>
