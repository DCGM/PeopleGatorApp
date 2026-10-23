<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { CalendarIcon } from '@lucide/vue'
import { parseDate } from '@internationalized/date'
import type { DateValue } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

const props = withDefaults(
  defineProps<{ label: string; invalid?: boolean; showLabel?: boolean }>(),
  { showLabel: true },
)
const value = defineModel<string>({ required: true })
const open = ref(false)
const timeId = useId()

const date = computed<DateValue | undefined>(() => {
  const day = value.value.split('T')[0]
  return day ? parseDate(day) : undefined
})
const time = computed(() => value.value.split('T')[1] ?? '00:00:00.000')
const displayValue = computed(() => {
  if (!value.value) return 'Pick date and time'
  const day = new Date(value.value).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
  return `${day} ${time.value.replace(/:00(?:\.000)?$/, '')}`
})

function selectDate(day: DateValue | undefined) {
  value.value = day ? `${day.toString()}T${time.value}` : ''
}
function updateTime(clock: string | number) {
  if (date.value && typeof clock === 'string' && clock)
    value.value = `${date.value.toString()}T${clock}`
}
function clear() {
  value.value = ''
  open.value = false
}
</script>

<template>
  <div class="min-w-0 max-w-full flex-none">
    <Popover v-model:open="open">
      <PopoverTrigger as-child>
        <Button
          type="button"
          variant="outline"
          class="w-full justify-start"
          :aria-label="label"
          :aria-invalid="!!invalid"
          :title="`${label}: ${displayValue}`"
        >
          <CalendarIcon class="size-4 shrink-0" aria-hidden="true" />
          <span class="min-w-0 truncate"
            ><template v-if="showLabel">{{ label }}: </template>{{ displayValue }}</span
          >
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" :collision-padding="12" class="w-auto p-0" :aria-label="label">
        <Calendar
          :model-value="date"
          :default-placeholder="date"
          layout="month-and-year"
          initial-focus
          prevent-deselect
          @update:model-value="selectDate"
        />
        <div class="space-y-2 p-3">
          <label :for="timeId">Time (local)</label>
          <Input
            :id="timeId"
            :model-value="time.replace(/(\.\d{3})\d+$/, '$1')"
            type="time"
            step="0.001"
            :disabled="!date"
            :aria-label="`${props.label} time`"
            @update:model-value="updateTime"
          />
          <div class="flex justify-between">
            <Button type="button" variant="ghost" size="sm" :disabled="!value" @click="clear"
              >Clear</Button
            >
            <Button type="button" variant="outline" size="sm" @click="open = false">Done</Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  </div>
</template>
