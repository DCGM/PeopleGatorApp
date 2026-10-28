<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ScanFace, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import IdentityFaceGallery from './IdentityFaceGallery.vue'

const props = defineProps<{ personId: string; name: string }>()
const open = ref(false)
const pinned = ref(false)
const trigger = ref<InstanceType<typeof Button>>()
let activating = false
let timer: ReturnType<typeof setTimeout> | undefined

function cancelTimer() {
  clearTimeout(timer)
  timer = undefined
}
function hover(event: PointerEvent) {
  if (event.pointerType !== 'mouse') return
  cancelTimer()
  timer = setTimeout(() => {
    open.value = true
  }, 300)
}
function leave() {
  cancelTimer()
  if (!pinned.value)
    timer = setTimeout(() => {
      open.value = false
    }, 250)
}
function activate() {
  activating = true
}
// Keep the standard trigger's IDs and focus behavior. Clicking a hover-open
// preview pins it; clicking the pinned trigger collapses it.
async function updateOpen(value: boolean) {
  cancelTimer()
  if (activating) {
    activating = false
    pinned.value = !pinned.value
    open.value = pinned.value
    if (open.value) {
      await nextTick()
      const id = trigger.value?.$el.getAttribute('aria-controls')
      if (id) document.getElementById(id)?.focus()
    }
  } else open.value = value
}
function pin() {
  pinned.value = true
  cancelTimer()
}
function close() {
  cancelTimer()
  open.value = false
  trigger.value?.$el.focus()
}
watch(open, (value) => {
  if (!value) pinned.value = false
})
watch(
  () => props.personId,
  () => {
    cancelTimer()
    open.value = false
  },
)
onBeforeUnmount(cancelTimer)
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
        @keydown.esc.stop.prevent="close"
        @keydown.stop
      >
        <ScanFace aria-hidden="true" />View faces
      </Button>
    </PopoverTrigger>
    <PopoverContent
      tabindex="-1"
      align="start"
      :collision-padding="12"
      class="w-80 max-w-[calc(100vw-1.5rem)] space-y-3"
      @open-auto-focus.prevent
      @close-auto-focus.prevent
      @escape-key-down="close"
      @pointerenter="cancelTimer"
      @pointerleave="leave"
      @focusin="pin"
      @keydown.esc.stop.prevent="close"
      @keydown.stop
      @wheel.stop
      @pointerdown.stop
      @click.stop
    >
      <div class="flex items-center justify-between gap-2">
        <h4 class="min-w-0 break-words text-sm font-medium">Faces of {{ name }}</h4>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Close faces"
          @click="close"
        >
          <X aria-hidden="true" />
        </Button>
      </div>
      <IdentityFaceGallery v-if="open" :key="personId" :person-id="personId" :name="name" />
    </PopoverContent>
  </Popover>
</template>
