<script setup lang="ts">
import { computed, reactive, ref, useId, watch } from 'vue'

import EditableActions from '@/components/custom/EditableActions.vue'
import { Input } from '@/components/ui/input'
import { formatLifeDate, lifeDatesError } from '@/lib/life-dates'
import type { PersonNameDates } from '@/viewmodels/person-detail.types'

const props = defineProps<{ modelValue: PersonNameDates }>()
const emit = defineEmits<{ 'update:modelValue': [value: PersonNameDates] }>()

const FIELDS = [
  { key: 'firstName', label: 'First name', type: 'text' },
  { key: 'middleNames', label: 'Middle names', type: 'text' },
  { key: 'surname', label: 'Surname', type: 'text' },
  { key: 'birthDate', label: 'Born', type: 'date' },
  { key: 'deathDate', label: 'Died', type: 'date' },
] as const

const editing = ref(false)
const submitted = ref(false)
const draft = reactive<PersonNameDates>({ ...props.modelValue })
const errorId = useId()
const error = computed(() =>
  submitted.value ? lifeDatesError(draft.birthDate, draft.deathDate) : undefined,
)

watch(
  () => props.modelValue,
  (value) => {
    if (!editing.value) Object.assign(draft, value)
  },
  { deep: true },
)

function display(key: keyof PersonNameDates) {
  const value = props.modelValue[key]
  return value && key.endsWith('Date') ? formatLifeDate(value) : value
}

function begin() {
  Object.assign(draft, props.modelValue)
  submitted.value = false
  editing.value = true
}

function save() {
  submitted.value = true
  const next: PersonNameDates = {
    firstName: draft.firstName.trim(),
    middleNames: draft.middleNames.split(/\s+/).filter(Boolean).join(' '),
    surname: draft.surname.trim(),
    birthDate: draft.birthDate,
    deathDate: draft.deathDate,
  }
  if (lifeDatesError(next.birthDate, next.deathDate)) return
  Object.assign(draft, next)
  editing.value = false
  emit('update:modelValue', next)
}

function cancel() {
  Object.assign(draft, props.modelValue)
  editing.value = false
}
</script>

<template>
  <section aria-label="Name and life dates" class="mt-4 flex min-w-0 items-start gap-2">
    <dl class="flex min-w-0 flex-1 flex-wrap gap-x-5 gap-y-2 text-sm">
      <div
        v-for="field in FIELDS"
        :key="field.key"
        class="flex min-w-0 max-w-full items-center gap-2"
      >
        <dt class="shrink-0 text-xs font-semibold uppercase text-muted-foreground">
          {{ field.label }}
        </dt>
        <dd class="min-w-0">
          <Input
            v-if="editing"
            v-model="draft[field.key]"
            :type="field.type"
            :aria-label="field.label"
            :aria-invalid="field.type === 'date' && !!error"
            :aria-describedby="field.type === 'date' && error ? errorId : undefined"
            class="h-8 w-auto max-w-full"
            @keydown.enter.prevent="save"
            @keydown.esc.prevent="cancel"
          />
          <span v-else-if="props.modelValue[field.key]" class="break-words">{{
            display(field.key)
          }}</span>
          <span v-else class="text-muted-foreground">—</span>
        </dd>
      </div>
      <p v-if="error" :id="errorId" role="alert" class="basis-full text-destructive">
        {{ error }}
      </p>
    </dl>
    <EditableActions
      :editing="editing"
      label="name and life dates"
      @edit="begin"
      @save="save"
      @cancel="cancel"
    />
  </section>
</template>
