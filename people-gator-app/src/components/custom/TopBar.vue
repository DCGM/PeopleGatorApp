<script setup lang="ts">
import { FileText, User } from '@lucide/vue'
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()

const isDocumentRoute = computed(() => route.name === 'document-search' || route.name === 'document-page')
const isPeopleRoute = computed(() => route.name === 'people-search' || route.name === 'person-detail')
</script>

<template>
  <nav class="flex h-13 w-full items-center justify-between border-b bg-background pl-3 pr-6">
    <div class="flex items-center gap-6">
      <div class="h-16 w-16 z-20 flex items-center justify-center border-3 rotate-4 bg-background">
        <h1 class="rotate-[-4deg] text-border text-2xl">PG</h1>
      </div>
      <div class="flex-col leading-none hidden sm:flex">
        <h1 class="text-lg">People Gator</h1>
      </div>
    </div>

    <div class="flex items-center gap-6">
      <RouterLink :to="{ name: 'document-search' }"
        class="flex flex-col items-center gap-1 border-b-2 pb-1 transition-colors" :class="isDocumentRoute
          ? 'border-primary text-primary'
          : 'border-transparent text-muted-foreground hover:text-foreground'">
        <span class="flex items-center gap-2">
          <FileText class="size-[1em]" />
          <span class="hidden sm:inline">Documents</span>
        </span>
      </RouterLink>

      <RouterLink :to="{ name: 'people-search' }"
        class="flex flex-col items-center gap-1 border-b-2 pb-1 transition-colors" :class="isPeopleRoute
          ? 'border-primary text-primary'
          : 'border-transparent text-muted-foreground hover:text-foreground'">
        <span class="flex items-center gap-2">
          <User class="size-[1em]" />
          <span class="hidden sm:inline">People</span>
        </span>
      </RouterLink>
    </div>
  </nav>
</template>
