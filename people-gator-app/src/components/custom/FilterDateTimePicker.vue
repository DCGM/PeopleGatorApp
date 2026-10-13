<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { CalendarIcon } from '@lucide/vue'
import { parseDate } from '@internationalized/date'
import type { DateValue } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

const props = defineProps<{ label: string; invalid?: boolean }>()
const value = defineModel<string>({ required: true })
const open = ref(false)
const labelId = useId()
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
  <div class="min-w-0 space-y-1 text-sm">
    <span :id="labelId">{{ label }}</span>
    <Popover v-model:open="open">
      <PopoverTrigger as-child>
        <Button
          type="button"
          variant="outline"
          class="w-full justify-start rounded-none font-normal"
          :class="!value && 'text-muted-foreground'"
          :aria-labelledby="labelId"
          :aria-invalid="!!invalid"
          :title="displayValue"
        >
          <CalendarIcon class="size-4 shrink-0" aria-hidden="true" />
          <span class="truncate">{{ displayValue }}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        :collision-padding="12"
        class="w-auto rounded-none p-0"
        :aria-label="label"
      >
        <Calendar
          :model-value="date"
          :default-placeholder="date"
          layout="month-and-year"
          initial-focus
          prevent-deselect
          @update:model-value="selectDate"
        />
        <div class="space-y-2 border-t p-3">
          <label :for="timeId">Time (local)</label>
          <Input
            :id="timeId"
            :model-value="time"
            type="time"
            step="0.001"
            :disabled="!date"
            :aria-label="`${props.label} time`"
            class="rounded-none"
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
