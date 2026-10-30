<script lang="ts">
import { ref } from 'vue'

// Only one identity gallery is shown at a time. A clicked (pinned) gallery
// stays until dismissed; hovering other triggers does not replace it.
const active = ref<{ id: symbol; pinned: boolean } | null>(null)
</script>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, watch } from 'vue'
import { ScanFace } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import IdentityFaceGallery from './IdentityFaceGallery.vue'

const props = defineProps<{ personId: string; name: string }>()
const self = Symbol('identity-face-preview')
const open = computed(() => active.value?.id === self)
const pinned = computed(() => open.value && active.value!.pinned)
const trigger = ref<InstanceType<typeof Button>>()
let activating = false
let timer: ReturnType<typeof setTimeout> | undefined

function show(pin: boolean) {
  active.value = { id: self, pinned: pin }
}
function hide() {
  if (open.value) active.value = null
}
function cancelTimer() {
  clearTimeout(timer)
  timer = undefined
}
function hover(event: PointerEvent) {
  if (event.pointerType !== 'mouse') return
  cancelTimer()
  timer = setTimeout(() => {
    if (!active.value?.pinned) show(false)
  }, 300)
}
function leave() {
  cancelTimer()
  if (!pinned.value) timer = setTimeout(hide, 250)
}
// Reka toggles from the trigger's click without saying so; mark only the
// current click dispatch so a skipped toggle cannot leak into a later dismissal.
function activate() {
  activating = true
  setTimeout(() => {
    activating = false
  })
}
// Keep the standard trigger's IDs and focus behavior. Clicking a hover-open
// preview pins it; clicking the pinned trigger collapses it.
async function updateOpen(value: boolean) {
  cancelTimer()
  if (activating) {
    activating = false
    if (pinned.value) hide()
    else {
      show(true)
      await nextTick()
      content()?.focus()
    }
  } else if (value) show(true)
  else hide()
}
function content() {
  const id = trigger.value?.$el.getAttribute('aria-controls')
  return id ? document.getElementById(id) : null
}
function pin() {
  if (open.value) show(true)
  cancelTimer()
}
// The single Escape path: Reka reports Escape for the topmost layer only.
function escape(event: KeyboardEvent) {
  event.preventDefault()
  cancelTimer()
  const focused = content()?.contains(document.activeElement)
  hide()
  if (focused) trigger.value?.$el.focus()
}
// Keep gallery and trigger keys out of scan shortcuts while letting Escape
// reach the popover's dismissal.
function isolateKeys(event: KeyboardEvent) {
  if (event.key !== 'Escape') event.stopPropagation()
}
watch(
  () => props.personId,
  () => {
    cancelTimer()
    hide()
  },
)
onBeforeUnmount(() => {
  cancelTimer()
  hide()
})
</script>

<template>
  <Popover :open="open" @update:open="updateOpen">
    <PopoverTrigger as-child>
      <Button
        ref="trigger"
        type="button"
        variant="outline"
        size="xs"
        class="border-sky-600 text-sky-700 hover:text-sky-700 dark:border-sky-500 dark:text-sky-400 dark:hover:text-sky-400"
        :aria-label="`View faces of ${name}`"
        @pointerenter="hover"
        @pointerleave="leave"
        @click.capture="activate"
        @click.stop
        @keydown="isolateKeys"
      >
        <ScanFace aria-hidden="true" />View faces
      </Button>
    </PopoverTrigger>
    <PopoverContent
      tabindex="-1"
      align="start"
      :collision-padding="12"
      class="w-64 max-w-[calc(100vw-1.5rem)] p-2"
      @open-auto-focus.prevent
      @close-auto-focus.prevent
      @escape-key-down="escape"
      @pointerenter="cancelTimer"
      @pointerleave="leave"
      @focusin="pin"
      @keydown="isolateKeys"
      @wheel.stop
      @click.stop
    >
      <IdentityFaceGallery v-if="open" :key="personId" :person-id="personId" :name="name" />
    </PopoverContent>
  </Popover>
</template>
