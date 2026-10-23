<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { nextTick, useTemplateRef, watch, type ComponentPublicInstance } from 'vue'
import { Button } from '@/components/ui/button'
import { useSidebar } from '@/components/ui/sidebar'
import { relatedQuery } from '@/viewmodels/shared-filters'
import PeopleGatorIcon from './PeopleGatorIcon'

const route = useRoute()
const { isMobile, open, setOpen } = useSidebar()
const brand = useTemplateRef<ComponentPublicInstance>('brand')

watch(open, async (expanded) => {
  if (isMobile.value) return
  await nextTick()
  const element = brand.value?.$el as HTMLElement | undefined
  if (expanded) {
    element
      ?.closest('[data-sidebar=header]')
      ?.querySelector<HTMLButtonElement>('[data-sidebar=trigger]')
      ?.focus()
  } else element?.focus()
})
</script>

<template>
  <Button
    v-if="!isMobile && !open"
    ref="brand"
    variant="ghost"
    size="icon"
    aria-label="Expand sidebar"
    :aria-expanded="false"
    @click="setOpen(true)"
  >
    <PeopleGatorIcon class="size-8" aria-hidden="true" stroke-width="1" />
  </Button>
  <RouterLink
    v-else
    ref="brand"
    :to="{ name: 'document-list', query: relatedQuery(route) }"
    class="flex min-w-0 flex-1 items-center gap-2 p-2"
    aria-label="PeopleGator"
  >
    <PeopleGatorIcon class="size-8 shrink-0" aria-hidden="true" stroke-width="1" />
    <span class="font-heading text-xl">PeopleGator</span>
  </RouterLink>
</template>
