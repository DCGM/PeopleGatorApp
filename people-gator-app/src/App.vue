<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'

import TopBar from './components/custom/TopBar.vue'

const route = useRoute()
</script>

<template>
  <div
    class="min-h-screen bg-background text-foreground"
    :class="{
      'lg:flex lg:h-dvh lg:flex-col':
        route.name === 'document-list' || route.name === 'people-search',
    }"
  >
    <TopBar v-if="route.name !== 'login'" class="shrink-0" />
    <RouterView />
  </div>
</template>
