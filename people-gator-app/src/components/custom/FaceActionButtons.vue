<script setup lang="ts">
import { BadgeCheck, Link2, RefreshCw, Trash2, Unlink } from '@lucide/vue'
import UiTooltip from './UiTooltip.vue'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import type { Face } from '@/viewmodels/document-workspace.types'

defineProps<{
  face: Face
  canAnnotate: boolean
  canDelete: boolean
  busy?: boolean
}>()
defineEmits<{ findProfile: []; unassign: []; verify: []; delete: [] }>()
</script>

<template>
  <ButtonGroup aria-label="Detection actions">
    <template v-if="canAnnotate">
      <UiTooltip
        :text="face.personId ? 'Reassign to another profile' : 'Link to an existing profile'"
      >
        <Button
          variant="outline"
          size="icon-xs"
          :disabled="busy"
          class="border-amber-600 text-amber-700 hover:text-amber-700 dark:border-amber-500 dark:text-amber-400 dark:hover:text-amber-400"
          :aria-label="
            face.personId ? 'Reassign to another profile' : 'Link to an existing profile'
          "
          @click="$emit('findProfile')"
        >
          <RefreshCw v-if="face.personId" aria-hidden="true" /><Link2 v-else aria-hidden="true" />
        </Button>
      </UiTooltip>
      <UiTooltip v-if="face.personId" text="Unassign current profile">
        <Button
          variant="outline"
          size="icon-xs"
          :disabled="busy"
          class="border-destructive text-destructive hover:text-destructive dark:border-destructive"
          aria-label="Unassign current profile"
          @click="$emit('unassign')"
          ><Unlink aria-hidden="true"
        /></Button>
      </UiTooltip>
      <UiTooltip v-if="face.personId && face.linkState !== 'verified'" text="Verify this link">
        <Button
          variant="outline"
          size="icon-xs"
          :disabled="busy"
          class="border-emerald-600 text-emerald-700 hover:text-emerald-700 dark:border-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-400"
          aria-label="Verify this link"
          @click="$emit('verify')"
          ><BadgeCheck aria-hidden="true"
        /></Button>
      </UiTooltip>
    </template>
    <UiTooltip v-if="canDelete" text="Delete detection">
      <Button
        variant="outline"
        size="icon-xs"
        :disabled="busy"
        class="border-destructive text-destructive hover:text-destructive dark:border-destructive"
        aria-label="Delete detection"
        @click="$emit('delete')"
        ><Trash2 aria-hidden="true"
      /></Button>
    </UiTooltip>
  </ButtonGroup>
</template>
