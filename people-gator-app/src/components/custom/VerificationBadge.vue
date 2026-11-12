<script setup lang="ts">
import { computed } from 'vue'
import type { VerificationState } from '@/client'
import { Badge } from '@/components/ui/badge'
import { verificationVisuals } from '@/lib/verification'

// Same label shape as the verified link-state badge (#149).
const props = defineProps<{ state?: VerificationState | null }>()
const visual = computed(() => verificationVisuals[props.state ?? 'not_verified'])
</script>

<template>
  <Badge
    data-verification-badge
    :data-state="state ?? 'not_verified'"
    class="gap-1 border-0 px-2 py-0.5 text-xs font-normal"
    :class="visual.classes"
  >
    <component :is="visual.icon" class="size-3 shrink-0" aria-hidden="true" />
    <span class="min-w-0 truncate">{{ visual.label }}</span>
  </Badge>
</template>
