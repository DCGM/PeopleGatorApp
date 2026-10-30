<script setup lang="ts">
import { BadgeCheck, Link2, RefreshCw, Trash2, Unlink } from '@lucide/vue'
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
      <Button
        variant="outline"
        size="icon-xs"
        :disabled="busy"
        class="border-amber-600 text-amber-700 hover:text-amber-700 dark:border-amber-500 dark:text-amber-400 dark:hover:text-amber-400"
        :aria-label="face.personId ? 'Reassign' : 'Link'"
        :title="face.personId ? 'Reassign' : 'Link'"
        @click="$emit('findProfile')"
      >
        <RefreshCw v-if="face.personId" aria-hidden="true" /><Link2 v-else aria-hidden="true" />
      </Button>
      <Button
        v-if="face.personId"
        variant="outline"
        size="icon-xs"
        :disabled="busy"
        class="border-destructive text-destructive hover:text-destructive dark:border-destructive"
        aria-label="Unlink"
        title="Unlink"
        @click="$emit('unassign')"
        ><Unlink aria-hidden="true"
      /></Button>
      <Button
        v-if="face.personId && face.linkState !== 'verified'"
        variant="outline"
        size="icon-xs"
        :disabled="busy"
        class="border-emerald-600 text-emerald-700 hover:text-emerald-700 dark:border-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-400"
        aria-label="Verify"
        title="Verify"
        @click="$emit('verify')"
        ><BadgeCheck aria-hidden="true"
      /></Button>
    </template>
    <Button
      v-if="canDelete"
      variant="outline"
      size="icon-xs"
      :disabled="busy"
      class="border-destructive text-destructive hover:text-destructive dark:border-destructive"
      aria-label="Delete detection"
      title="Delete detection"
      @click="$emit('delete')"
      ><Trash2 aria-hidden="true"
    /></Button>
  </ButtonGroup>
</template>
