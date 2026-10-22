<script setup lang="ts">
import { RouterView } from 'vue-router'

import WorkspaceShowcase from './components/custom/WorkspaceShowcase.vue'
</script>

<template>
  <WorkspaceShowcase>
    <RouterView />
  </WorkspaceShowcase>
</template>
