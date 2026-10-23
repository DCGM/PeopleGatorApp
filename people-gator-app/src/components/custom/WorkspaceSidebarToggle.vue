<script setup lang="ts">
import { SidebarTrigger, useSidebar } from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'
import PeopleGatorIcon from './PeopleGatorIcon'
import { nextTick, useTemplateRef, watch, type ComponentPublicInstance } from 'vue'

const props = defineProps<{ location: 'sidebar' | 'topbar' }>()
const { isMobile, openMobile, open, setOpenMobile } = useSidebar()
const trigger = useTemplateRef<ComponentPublicInstance>('trigger')

watch(openMobile, async (open, wasOpen) => {
  if (props.location === 'topbar' && isMobile.value && wasOpen && !open) {
    await nextTick()
    trigger.value?.$el.focus()
  }
})
</script>

<template>
  <SidebarTrigger
    v-if="location === 'sidebar' && (isMobile ? openMobile : open)"
    :aria-label="isMobile ? 'Close sidebar' : 'Collapse sidebar'"
  />
  <Button
    v-if="location === 'topbar' && isMobile && !openMobile"
    ref="trigger"
    variant="ghost"
    size="icon"
    aria-label="Open sidebar"
    :aria-expanded="false"
    @click="setOpenMobile(true)"
  >
    <PeopleGatorIcon class="size-8" aria-hidden="true" stroke-width="1" />
  </Button>
</template>
