<script setup lang="ts">
import { BadgeCheck, Link2, RefreshCw, Trash2, Unlink, UserPlus } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import type { Face } from '@/viewmodels/document-workspace.types'

defineProps<{
  face: Face
  canAnnotate: boolean
  canDelete: boolean
  busy?: boolean
  showCreate?: boolean
}>()
defineEmits<{ findProfile: []; create: []; unassign: []; verify: []; delete: [] }>()
</script>

<template>
  <ButtonGroup aria-label="Detection actions">
    <template v-if="canAnnotate">
      <Button
        variant="outline"
        size="icon-xs"
        :disabled="busy"
        class="border-fuchsia-600 text-fuchsia-700 hover:bg-fuchsia-50 hover:text-fuchsia-800 dark:border-fuchsia-500 dark:text-fuchsia-400 dark:hover:bg-fuchsia-950 dark:hover:text-fuchsia-300"
        :aria-label="face.personId ? 'Reassign' : 'Link'"
        :title="face.personId ? 'Reassign' : 'Link'"
        @click="$emit('findProfile')"
      >
        <RefreshCw v-if="face.personId" aria-hidden="true" /><Link2 v-else aria-hidden="true" />
      </Button>
      <Button
        v-if="showCreate"
        variant="outline"
        size="icon-xs"
        :disabled="busy"
        class="border-fuchsia-600 text-fuchsia-700 hover:bg-fuchsia-50 hover:text-fuchsia-800 dark:border-fuchsia-500 dark:text-fuchsia-400 dark:hover:bg-fuchsia-950 dark:hover:text-fuchsia-300"
        aria-label="New person"
        title="New person"
        @click="$emit('create')"
        ><UserPlus aria-hidden="true"
      /></Button>
      <Button
        v-if="face.personId"
        variant="outline"
        size="icon-xs"
        :disabled="busy"
        class="border-destructive text-destructive hover:bg-destructive/10 hover:text-destructive dark:border-destructive dark:hover:bg-destructive/10"
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
        class="border-emerald-600 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800 dark:border-emerald-500 dark:text-emerald-400 dark:hover:bg-emerald-950 dark:hover:text-emerald-300"
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
      class="border-destructive text-destructive hover:bg-destructive/10 hover:text-destructive dark:border-destructive dark:hover:bg-destructive/10"
      aria-label="Delete detection"
      title="Delete detection"
      @click="$emit('delete')"
      ><Trash2 aria-hidden="true"
    /></Button>
  </ButtonGroup>
</template>
