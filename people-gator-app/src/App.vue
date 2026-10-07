<script setup lang="ts">
import { RouterView } from 'vue-router'

import TopBar from './components/custom/TopBar.vue'
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <TopBar />
    <RouterView />
  </div>
</template>
