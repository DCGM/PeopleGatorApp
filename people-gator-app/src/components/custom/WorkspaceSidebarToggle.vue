<script setup lang="ts">
import { SidebarTrigger, useSidebar } from '@/components/ui/sidebar'
import { nextTick, useTemplateRef, watch, type ComponentPublicInstance } from 'vue'

const props = defineProps<{ location: 'sidebar' | 'topbar' }>()
const { isMobile, openMobile } = useSidebar()
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
    v-if="location === 'sidebar' ? !isMobile || openMobile : isMobile && !openMobile"
    ref="trigger"
  />
</template>
