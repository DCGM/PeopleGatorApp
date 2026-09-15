<script setup lang="ts">
import { computed, provide, ref } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import { topBarContextKey } from './components/custom/top-bar-context'
import TopBar from './components/custom/TopBar.vue'

const topBarContext = ref<HTMLElement | null>(null)
const route = useRoute()
const topBarTitle = computed(() => route.name === 'document-page' ? undefined : 'People Gator')

provide(topBarContextKey, topBarContext)
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <TopBar :title="topBarTitle">
      <div ref="topBarContext" class="contents" />
    </TopBar>
    <RouterView />
  </div>
</template>
