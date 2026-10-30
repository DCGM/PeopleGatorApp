<script setup lang="ts">
import { BadgeCheck } from '@lucide/vue'
import type { LinkMetadata } from '@/lib/entity-links'
import { linkTooltip } from '@/lib/entity-links'
import { Button } from '@/components/ui/button'
import UiTooltip from './UiTooltip.vue'
import { useVerifyLinkMutation } from '@/query/entity-links'
import { useCanAnnotate } from '@/composables/can-annotate'
defineProps<LinkMetadata & { id: string; kind: 'face' | 'mention'; inline?: boolean }>()
const mutation = useVerifyLinkMutation()
const allowed = useCanAnnotate()
</script>
<template>
  <div v-if="linkState" :class="inline ? 'contents' : 'mt-2 text-xs'">
    <p v-if="linkState === 'verified' && !inline" class="break-words text-muted-foreground">
      {{ linkTooltip({ linkState, verifiedBy, verifiedAt }) }}
    </p>
    <template v-else-if="linkState !== 'verified' && allowed">
      <UiTooltip v-if="inline" text="Verify this link">
        <Button
          variant="outline"
          size="icon-xs"
          class="border-emerald-600 text-emerald-700 hover:text-emerald-700 dark:border-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-400"
          :disabled="mutation.isPending.value"
          aria-label="Verify this link"
          @click="mutation.mutate({ id, kind })"
          ><BadgeCheck aria-hidden="true"
        /></Button>
      </UiTooltip>
      <Button
        v-else
        variant="outline"
        size="xs"
        :disabled="mutation.isPending.value"
        @click="mutation.mutate({ id, kind })"
        ><BadgeCheck class="size-3" aria-hidden="true" />{{
          mutation.isPending.value ? 'Verifying…' : 'Verify link'
        }}</Button
      >
      <p
        v-if="mutation.error.value"
        role="alert"
        class="mt-1 text-xs text-destructive"
        :class="inline && 'order-last basis-full'"
      >
        Could not verify this link. Try again.
      </p>
    </template>
  </div>
</template>
