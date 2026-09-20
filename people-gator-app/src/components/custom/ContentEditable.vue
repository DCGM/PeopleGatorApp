<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    as?: 'h1' | 'h4' | 'p' | 'span'
    editable?: boolean
    singleLine?: boolean
  }>(),
  {
    as: 'span',
    editable: false,
    singleLine: false,
  },
)

const model = defineModel<string>({ required: true })
const element = ref<HTMLElement | null>(null)

function syncContent() {
  if (!element.value || document.activeElement === element.value) return
  if (element.value.textContent !== model.value) element.value.textContent = model.value
}

function updateModel(event: Event) {
  model.value = (event.currentTarget as HTMLElement).textContent ?? ''
}

function preventLineBreak(event: KeyboardEvent) {
  if (props.singleLine && event.key === 'Enter') event.preventDefault()
}

onMounted(syncContent)
watch([model, () => props.editable], syncContent)
</script>

<template>
  <component
    :is="props.as"
    ref="element"
    :contenteditable="props.editable ? 'plaintext-only' : 'false'"
    :role="props.editable ? 'textbox' : undefined"
    :aria-multiline="props.editable ? !props.singleLine : undefined"
    @input="updateModel"
    @keydown="preventLineBreak"
  />
</template>
