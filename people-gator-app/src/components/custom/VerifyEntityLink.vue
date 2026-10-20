<script setup lang="ts">
import { BadgeCheck } from '@lucide/vue'
import type { LinkMetadata } from '@/lib/entity-links'
import { linkTooltip } from '@/lib/entity-links'
import { Button } from '@/components/ui/button'
import { useVerifyLinkMutation } from '@/query/entity-links'
import { useCanAnnotate } from '@/composables/can-annotate'
defineProps<LinkMetadata & { id: string; kind: 'face' | 'mention' }>()
const mutation = useVerifyLinkMutation()
const allowed = useCanAnnotate()
</script>
<template>
  <div v-if="linkState" class="mt-2 text-xs">
    <p v-if="linkState === 'verified'" class="break-words text-muted-foreground">
      {{ linkTooltip({ linkState, verifiedBy, verifiedAt }) }}
    </p>
    <template v-else-if="allowed">
      <Button
        variant="outline"
        size="xs"
        :disabled="mutation.isPending.value"
        @click="mutation.mutate({ id, kind })"
        ><BadgeCheck class="size-3" aria-hidden="true" />{{
          mutation.isPending.value ? 'Verifying…' : 'Verify link'
        }}</Button
      >
      <p v-if="mutation.error.value" role="alert" class="mt-1 text-destructive">
        Could not verify this link. Try again.
      </p>
    </template>
  </div>
</template>
