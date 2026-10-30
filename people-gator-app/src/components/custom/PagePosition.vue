<script setup lang="ts">
import { pagePosition, pagePositionLabel } from '@/lib/page-position'

defineProps<{ number?: number | null; total?: number | null }>()
</script>

<template>
  <small class="tabular-nums"
    ><span aria-hidden="true">{{ pagePosition(number, total) }}</span
    ><span class="sr-only">{{ pagePositionLabel(number, total) }}</span></small
  >
</template>
