<script setup lang="ts">
import SelectedEvidenceActions from './SelectedEvidenceActions.vue'
defineProps<{ count: number; busy?: boolean }>()
defineEmits<{ clear: [] }>()
</script>
<template>
  <SelectedEvidenceActions
    :count="count"
    :busy="busy"
    singular="face"
    plural="faces"
    label="Selected face actions"
    @clear="$emit('clear')"
  >
    <template #description><slot name="description" /></template>
    <slot />
  </SelectedEvidenceActions>
</template>
