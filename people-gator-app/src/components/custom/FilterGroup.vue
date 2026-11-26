<script setup lang="ts">
// One titled group of related filter controls in a filter sidebar or drawer (#178).
defineProps<{ title: string }>()
</script>

<template>
  <div class="flex w-full min-w-0 flex-col gap-2" role="group" :aria-label="title">
    <small class="uppercase text-secondary">{{ title }}</small>
    <div class="flex w-full min-w-0 flex-row flex-wrap items-start gap-2"><slot /></div>
  </div>
</template>
