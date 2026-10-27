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
      aria-label="Delete detection"
      title="Delete detection"
      @click="$emit('delete')"
      ><Trash2 aria-hidden="true"
    /></Button>
  </ButtonGroup>
</template>
