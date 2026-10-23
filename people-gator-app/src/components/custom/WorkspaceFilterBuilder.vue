<script setup lang="ts">
import {
  computed,
  nextTick,
  ref,
  useTemplateRef,
  type Component,
  type ComponentPublicInstance,
} from 'vue'
import {
  CalendarArrowDown,
  CalendarArrowUp,
  ChevronDown,
  FileImage,
  Files,
  KeyRound,
  LibraryBig,
  ListFilter,
  UserRoundPen,
} from '@lucide/vue'
import type { FilterOption } from '@/query/people-filter-options'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import FilterMultiSelect from './FilterMultiSelect.vue'
import FilterDateTimePicker from './FilterDateTimePicker.vue'

export type WorkspaceFilterSelection = { key: string; values: string[]; date: string }
const props = defineProps<{
  fields: { key: string; label: string; options: FilterOption[]; selected: string[] }[]
  from: string
  to: string
}>()
const emit = defineEmits<{ change: [filter: WorkspaceFilterSelection] }>()
const typeIcons: Record<string, Component> = {
  library: LibraryBig,
  document: Files,
  page: FileImage,
  user: UserRoundPen,
  key: KeyRound,
}
const filterTypes = computed(() => [
  ...props.fields.map((field) => ({
    key: field.key,
    label: field.label,
    icon: typeIcons[field.key] ?? ListFilter,
  })),
  { key: 'from', label: 'Modified from', icon: CalendarArrowUp },
  { key: 'to', label: 'Modified to', icon: CalendarArrowDown },
])
const typeOpen = ref(false)
const pickerOpen = ref(false)
const openValueOnTypeClose = ref(false)
const filterType = ref<string>()
const values = ref<string[]>([])
const search = ref('')
const date = ref('')
const typeTrigger = useTemplateRef<ComponentPublicInstance>('typeTrigger')
const row = useTemplateRef<HTMLElement>('row')
let valueOpen = false
let restoreFocus = true
const field = computed(() => props.fields.find((field) => field.key === filterType.value))
const selectedType = computed(() => filterTypes.value.find((type) => type.key === filterType.value))

function resetValue() {
  valueOpen = false
  pickerOpen.value = false
  values.value = []
  search.value = ''
  date.value = ''
}
async function close(focus = true) {
  openValueOnTypeClose.value = false
  filterType.value = undefined
  typeOpen.value = false
  resetValue()
  await nextTick()
  if (focus) typeTrigger.value?.$el.focus()
}
function selectType() {
  resetValue()
  values.value = [...(field.value?.selected ?? [])]
  date.value = filterType.value === 'from' ? props.from : filterType.value === 'to' ? props.to : ''
}
function apply() {
  if (!filterType.value) return
  emit('change', { key: filterType.value, values: [...values.value], date: date.value })
}
function valueOpenChange(open: boolean) {
  if (open) {
    valueOpen = true
    restoreFocus = true
  } else if (valueOpen) {
    valueOpen = false
    if (!typeOpen.value && !openValueOnTypeClose.value) void close(restoreFocus)
  }
}
function outsideValue(event: Event) {
  if (event.defaultPrevented) return
  const target = (event as CustomEvent<{ originalEvent: Event }>).detail.originalEvent.target
  restoreFocus = target instanceof Node && !!row.value?.contains(target)
}
async function afterTypeClose(event: Event) {
  if (!openValueOnTypeClose.value || !filterType.value) return
  event.preventDefault()
  openValueOnTypeClose.value = false
  // Let the type dropdown release focus before opening the value picker.
  await nextTick()
  pickerOpen.value = true
}
</script>

<template>
  <div class="flex w-full min-w-0 flex-row flex-wrap gap-2" aria-label="Workspace sample filters">
    <div
      ref="row"
      class="flex w-full min-w-0 items-center gap-1"
      role="group"
      aria-label="Workspace filter"
      @keydown.esc.stop.prevent="close()"
    >
      <Select v-model="filterType" v-model:open="typeOpen" @update:model-value="selectType">
        <SelectTrigger
          ref="typeTrigger"
          :title="selectedType?.label ?? 'Filter type'"
          :aria-label="selectedType ? `Filter type: ${selectedType.label}` : 'Filter type'"
          :class="
            selectedType
              ? 'size-9 shrink-0 justify-center p-0 [&>svg:last-child]:hidden'
              : 'min-w-0 max-w-full shrink px-2'
          "
        >
          <SelectValue placeholder="Filter">
            <component
              v-if="selectedType"
              :is="selectedType.icon"
              class="size-4"
              aria-hidden="true"
            />
          </SelectValue>
        </SelectTrigger>
        <SelectContent @close-auto-focus="afterTypeClose" @escape-key-down.prevent="close()">
          <SelectItem
            v-for="type in filterTypes"
            :key="type.key"
            :value="type.key"
            @select="openValueOnTypeClose = true"
          >
            <component :is="type.icon" class="size-4" aria-hidden="true" />
            <span>{{ type.label }}</span>
          </SelectItem>
        </SelectContent>
      </Select>
      <Button
        v-if="!filterType"
        variant="outline"
        disabled
        aria-label="Filter value"
        class="min-w-0 shrink"
      >
        <span class="truncate">Value</span><ChevronDown aria-hidden="true" />
      </Button>
      <FilterMultiSelect
        v-else-if="field"
        :key="field.key"
        v-model="values"
        v-model:open="pickerOpen"
        v-model:search="search"
        :label="field.label"
        placeholder="Value"
        :show-done="false"
        @update:model-value="apply"
        @open-change="valueOpenChange"
        @interact-outside="outsideValue"
        @escape="close()"
        :options="
          field.options.filter((option) =>
            option.label.toLowerCase().includes(search.toLowerCase()),
          )
        "
        class="min-w-0 max-w-full shrink"
      />
      <FilterDateTimePicker
        v-else
        :key="filterType"
        v-model="date"
        v-model:open="pickerOpen"
        :label="filterType === 'from' ? 'Modified from' : 'Modified to'"
        :show-label="false"
        :show-done="false"
        @update:model-value="apply"
        @open-change="valueOpenChange"
        @interact-outside="outsideValue"
        @escape="close()"
        class="min-w-0 max-w-full shrink"
      />
    </div>
  </div>
</template>
