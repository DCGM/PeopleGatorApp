<script setup lang="ts">
import { computed } from 'vue'
import { PanelLeft } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useSidebar } from '@/components/ui/sidebar'
import PeopleGatorIcon from './PeopleGatorIcon'

const { isMobile, open, openMobile, toggleSidebar } = useSidebar()
const expanded = computed(() => (isMobile.value ? openMobile.value : open.value))
const label = computed(() =>
  isMobile.value
    ? 'Close PeopleGator sidebar'
    : expanded.value
      ? 'Collapse PeopleGator sidebar'
      : 'Expand PeopleGator sidebar',
)
</script>

<template>
  <Button
    variant="ghost"
    class="h-12 w-full justify-start gap-2 px-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
    :aria-label="label"
    :aria-expanded="expanded"
    @click="toggleSidebar"
  >
    <PeopleGatorIcon class="size-8 shrink-0" aria-hidden="true" stroke-width="1" />
    <span class="font-heading text-xl group-data-[collapsible=icon]:hidden">PeopleGator</span>
    <PanelLeft
      class="ml-auto size-4 shrink-0 group-data-[collapsible=icon]:hidden"
      aria-hidden="true"
    />
  </Button>
</template>
