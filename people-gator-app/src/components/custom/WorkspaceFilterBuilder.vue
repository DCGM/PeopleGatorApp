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

export type WorkspaceFilterDraft = { key: string; values: string[]; date: string }
const props = defineProps<{
  fields: { key: string; label: string; options: FilterOption[] }[]
}>()
const emit = defineEmits<{ add: [filter: WorkspaceFilterDraft] }>()
const adding = ref(false)
const typeOpen = ref(false)
const filterType = ref<string>()
const values = ref<string[]>([])
const search = ref('')
const date = ref('')
const addButton = useTemplateRef<ComponentPublicInstance>('addButton')
const row = useTemplateRef<HTMLElement>('row')
let valueOpen = false
const submitOnClose = ref(true)
let restoreFocus = true
const field = computed(() => props.fields.find((field) => field.key === filterType.value))
const canAdd = computed(
  () => !!filterType.value && (field.value ? values.value.length > 0 : !!date.value),
)

function resetValue() {
  valueOpen = false
  values.value = []
  search.value = ''
  date.value = ''
}
function start() {
  filterType.value = undefined
  resetValue()
  adding.value = true
  typeOpen.value = true
}
async function close(focus = true) {
  adding.value = false
  typeOpen.value = false
  resetValue()
  await nextTick()
  if (focus) addButton.value?.$el.focus()
}
function add() {
  if (!canAdd.value || !filterType.value) return
  emit('add', { key: filterType.value, values: [...values.value], date: date.value })
  void close(restoreFocus)
}
function valueOpenChange(open: boolean) {
  if (open) {
    valueOpen = true
    submitOnClose.value = true
    restoreFocus = true
  } else if (valueOpen) {
    valueOpen = false
    if (submitOnClose.value) add()
  }
}
function outsideValue(event: Event) {
  if (event.defaultPrevented) return
  const target = (event as CustomEvent<{ originalEvent: Event }>).detail.originalEvent.target
  // Changing type or clicking Cancel must not apply the draft first.
  if (target instanceof Node && row.value?.contains(target)) submitOnClose.value = false
  restoreFocus = false
}
function typeOpenChange(open: boolean) {
  // Opening another dropdown moves focus into its portal before pointer dismissal.
  if (open) submitOnClose.value = false
}
</script>

<template>
  <div class="flex w-full min-w-0 flex-row flex-wrap gap-2" aria-label="Workspace sample filters">
    <Button
      v-if="!adding"
      ref="addButton"
      variant="outline"
      size="icon"
      aria-label="Add filter"
      @click="start"
    >
      <Plus aria-hidden="true" />
    </Button>
    <div
      v-else
      ref="row"
      class="flex w-full min-w-0 items-center gap-1"
      role="group"
      aria-label="New filter"
    >
      <Select
        v-model="filterType"
        v-model:open="typeOpen"
        @update:open="typeOpenChange"
        @update:model-value="resetValue"
      >
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
        <SelectContent>
          <SelectItem v-for="field in fields" :key="field.key" :value="field.key">{{
            field.label
          }}</SelectItem>
          <SelectItem value="from">Modified from</SelectItem>
          <SelectItem value="to">Modified to</SelectItem>
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
        v-model:search="search"
        :label="field.label"
        placeholder="Value"
        @open-change="valueOpenChange"
        @interact-outside="outsideValue"
        @escape="submitOnClose = false"
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
        :label="filterType === 'from' ? 'Modified from' : 'Modified to'"
        :show-label="false"
        @open-change="valueOpenChange"
        @interact-outside="outsideValue"
        @escape="submitOnClose = false"
        class="min-w-0 max-w-full shrink"
      />
      <Button variant="ghost" size="sm" aria-label="Cancel filter" @click="close()">Cancel</Button>
    </div>
  </div>
</template>
