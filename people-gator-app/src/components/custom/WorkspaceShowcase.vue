<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Globe, SlidersHorizontal, Moon, Sun, Plus, ChevronsUpDown } from '@lucide/vue'
import { useDark, useToggle } from '@vueuse/core'
import { SelectTrigger as WorkspaceModeTrigger } from 'reka-ui'
import WorkspaceSidebarBrand from './WorkspaceSidebarBrand.vue'
import TopBar from './TopBar.vue'
import FilterMultiSelect from './FilterMultiSelect.vue'
import FilterDateTimePicker from './FilterDateTimePicker.vue'
import ActiveFilters, { type ActiveFilter } from './ActiveFilters.vue'
import WorkspaceSidebarToggle from './WorkspaceSidebarToggle.vue'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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
const adding = ref(false)
const filterType = ref('library')
const draftValues = ref<string[]>([])
const draftSearch = ref('')
const draftDate = ref('')
const draftField = computed(() => fields.find((field) => field.key === filterType.value))
const canAdd = computed(() => (draftField.value ? draftValues.value.length > 0 : !!draftDate.value))
function resetDraft() {
  draftValues.value = []
  draftSearch.value = ''
  draftDate.value = ''
}
function addFilter() {
  if (!canAdd.value) return
  if (draftField.value) {
    draftField.value.selected = [...new Set([...draftField.value.selected, ...draftValues.value])]
  } else if (filterType.value === 'from') from.value = draftDate.value
  else to.value = draftDate.value
  adding.value = false
  resetDraft()
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
        <div class="flex items-center gap-2 group-data-[collapsible=icon]:flex-col">
          <WorkspaceSidebarBrand />
          <WorkspaceSidebarToggle location="sidebar" />
        </div>
      </SidebarHeader>
      <SidebarContent class="overflow-hidden">
        <ScrollArea class="min-h-0 w-full flex-1 [&_[data-slot=scroll-area-viewport]>div]:!block">
          <WorkspaceNavigation />
          <SidebarSeparator class="mx-0 w-full" />
          <SidebarGroup>
            <SidebarMenu>
              <SidebarMenuItem>
                <Select v-model="mode" @update:model-value="adding = false">
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
              <p class="px-2 py-2 text-xs text-muted-foreground">
                Visual demo · settings do not filter results.
              </p>
              <template v-if="mode === 'local'">
                <div
                  class="flex w-full min-w-0 flex-row flex-wrap gap-2 p-2"
                  aria-label="Workspace sample filters"
                >
                  <Popover v-model:open="adding" @update:open="resetDraft">
                    <PopoverTrigger as-child>
                      <Button variant="outline" size="icon" aria-label="Add filter"
                        ><Plus aria-hidden="true"
                      /></Button>
                    </PopoverTrigger>
                    <PopoverContent
                      align="start"
                      :collision-padding="12"
                      class="w-72 max-w-(--reka-popover-content-available-width)"
                    >
                      <div class="flex min-w-0 flex-row flex-wrap items-center gap-2">
                        <Select v-model="filterType" @update:model-value="resetDraft">
                          <SelectTrigger aria-label="Filter type" class="max-w-full"
                            >Filter: <SelectValue placeholder="Filter type"
                          /></SelectTrigger>
                          <SelectContent>
                            <SelectItem
                              v-for="field in fields"
                              :key="field.key"
                              :value="field.key"
                              >{{ field.label }}</SelectItem
                            >
                            <SelectItem value="from">Modified from</SelectItem>
                            <SelectItem value="to">Modified to</SelectItem>
                          </SelectContent>
                        </Select>
                        <FilterMultiSelect
                          v-if="draftField"
                          v-model="draftValues"
                          v-model:search="draftSearch"
                          :label="draftField.label"
                          :options="
                            draftField.options.filter((option) =>
                              option.label.toLowerCase().includes(draftSearch.toLowerCase()),
                            )
                          "
                          class="max-w-full flex-none"
                        />
                        <FilterDateTimePicker
                          v-else
                          v-model="draftDate"
                          :label="filterType === 'from' ? 'Modified from' : 'Modified to'"
                        />
                        <div class="flex w-full justify-end gap-2">
                          <Button variant="ghost" @click="adding = false">Cancel</Button>
                          <Button :disabled="!canAdd" @click="addFilter">Add</Button>
                        </div>
                      </div>
                    </PopoverContent>
                  </Popover>
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
        <template #toggle><WorkspaceSidebarToggle location="topbar" /></template>
      </TopBar>
      <slot />
    </SidebarInset>
  </SidebarProvider>
</template>
