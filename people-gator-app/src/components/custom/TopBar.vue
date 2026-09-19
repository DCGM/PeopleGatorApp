<script setup lang="ts">
import { FileText, User } from '@lucide/vue'
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

defineProps<{
  title?: string
}>()

const route = useRoute()

const isDocumentRoute = computed(() => route.name === 'document-search' || route.name === 'document-page')
const isPeopleRoute = computed(() => route.name === 'people-search' || route.name === 'person-detail')
</script>

<template>
  <nav class="flex h-13 w-full items-center gap-3 border-b bg-background pl-3 pr-6">
    <div class="flex shrink-0 items-center gap-6">
      <RouterLink :to="{ name: 'document-search' }" class="z-20 flex h-12 w-28 shrink-0 items-center bg-background">
        <img src="/PeopleGator-logo.svg" alt="PeopleGator" class="h-auto max-h-11 w-full">
      </RouterLink>
      <div v-if="title" class="hidden flex-col leading-none sm:flex">
        <h1 class="text-lg">{{ title }}</h1>
      </div>
    </div>

    <div id="topbar-context" class="topbar-context min-w-0 flex-1 overflow-x-auto">
      <slot />
    </div>

    <div class="flex shrink-0 items-center gap-6">
      <slot name="navigation">
        <RouterLink :to="{ name: 'document-search' }"
          class="flex flex-col items-center gap-1 border-b-2 pb-1 transition-colors" :class="isDocumentRoute
            ? 'border-primary text-primary'
            : 'border-transparent text-muted-foreground hover:text-foreground'">
          <span class="flex items-center gap-2">
            <FileText class="size-[1em]" />
            <span class="hidden 2xl:inline">Documents</span>
          </span>
        </RouterLink>

        <RouterLink :to="{ name: 'people-search' }"
          class="flex flex-col items-center gap-1 border-b-2 pb-1 transition-colors" :class="isPeopleRoute
            ? 'border-primary text-primary'
            : 'border-transparent text-muted-foreground hover:text-foreground'">
          <span class="flex items-center gap-2">
            <User class="size-[1em]" />
            <span class="hidden 2xl:inline">People</span>
          </span>
        </RouterLink>
      </slot>
    </div>
  </nav>
</template>

<style scoped>
.topbar-context {
  --edge-fade-width: 0.75rem;

  -webkit-mask-image: linear-gradient(to right,
      transparent,
      black var(--edge-fade-width),
      black calc(100% - var(--edge-fade-width)),
      transparent);
  mask-image: linear-gradient(to right,
      transparent,
      black var(--edge-fade-width),
      black calc(100% - var(--edge-fade-width)),
      transparent);
  scrollbar-width: none;
}

.topbar-context::-webkit-scrollbar {
  display: none;
}
</style>
