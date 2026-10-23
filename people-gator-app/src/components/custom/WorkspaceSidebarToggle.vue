<script setup lang="ts">
import { useSidebar } from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'
import PeopleGatorIcon from './PeopleGatorIcon'
import { nextTick, useTemplateRef, watch, type ComponentPublicInstance } from 'vue'

const { isMobile, openMobile, setOpenMobile } = useSidebar()
const trigger = useTemplateRef<ComponentPublicInstance>('trigger')

watch(openMobile, async (open, wasOpen) => {
  if (isMobile.value && wasOpen && !open) {
    await nextTick()
    trigger.value?.$el.focus()
  }
})
</script>

<template>
  <Button
    v-if="isMobile"
    ref="trigger"
    variant="ghost"
    size="icon"
    aria-label="Open sidebar"
    :aria-expanded="openMobile"
    @click="setOpenMobile(true)"
  >
    <PeopleGatorIcon class="size-8" aria-hidden="true" stroke-width="1" />
  </Button>
</template>
