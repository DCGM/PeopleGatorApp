<script setup lang="ts">
import { computed, nextTick, ref, useTemplateRef, type ComponentPublicInstance } from 'vue'
import { ChevronDown, Plus } from '@lucide/vue'
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
const adding = ref(false)
const typeOpen = ref(false)
const pickerOpen = ref(false)
const openValueOnTypeClose = ref(false)
const filterType = ref<string>()
const values = ref<string[]>([])
const search = ref('')
const date = ref('')
const addButton = useTemplateRef<ComponentPublicInstance>('addButton')
const row = useTemplateRef<HTMLElement>('row')
let valueOpen = false
let restoreFocus = true
const field = computed(() => props.fields.find((field) => field.key === filterType.value))

function resetValue() {
  valueOpen = false
  pickerOpen.value = false
  values.value = []
  search.value = ''
  date.value = ''
}
function start() {
  openValueOnTypeClose.value = false
  filterType.value = undefined
  resetValue()
  adding.value = true
  typeOpen.value = true
}
async function close(focus = true) {
  openValueOnTypeClose.value = false
  adding.value = false
  typeOpen.value = false
  resetValue()
  await nextTick()
  if (focus) addButton.value?.$el.focus()
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
  if (!openValueOnTypeClose.value || !adding.value || !filterType.value) return
  event.preventDefault()
  openValueOnTypeClose.value = false
  // Let the type dropdown release focus before opening the value picker.
  await nextTick()
  pickerOpen.value = true
}
</script>

<template>
  <div class="flex w-full min-w-0 flex-row flex-wrap gap-2" aria-label="Workspace sample filters">
    <Button
      v-if="!adding"
      ref="addButton"
      variant="outline"
      aria-label="Add filter"
      @click="start"
    >
      <Plus aria-hidden="true" /> Add filter
    </Button>
    <div
      v-else
      ref="row"
      class="flex w-full min-w-0 items-center gap-1"
      role="group"
      aria-label="New filter"
      @keydown.esc.stop.prevent="close()"
    >
      <Select v-model="filterType" v-model:open="typeOpen" @update:model-value="selectType">
        <SelectTrigger
          aria-label="Filter type"
          :title="
            field?.label ??
            (filterType === 'from'
              ? 'Modified from'
              : filterType === 'to'
                ? 'Modified to'
                : 'Filter type')
          "
          class="min-w-0 max-w-full shrink px-2"
        >
          <SelectValue placeholder="Filter">
            <span v-if="filterType" class="min-w-0 truncate">{{
              field?.label ?? (filterType === 'from' ? 'From' : 'To')
            }}</span>
          </SelectValue>
        </SelectTrigger>
        <SelectContent @close-auto-focus="afterTypeClose" @escape-key-down.prevent="close()">
          <SelectItem
            v-for="field in fields"
            :key="field.key"
            :value="field.key"
            @select="openValueOnTypeClose = true"
            >{{ field.label }}</SelectItem
          >
          <SelectItem value="from" @select="openValueOnTypeClose = true">Modified from</SelectItem>
          <SelectItem value="to" @select="openValueOnTypeClose = true">Modified to</SelectItem>
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
