<script setup lang="ts">
import { Check, Pencil, X } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'

const props = defineProps<{
  editing: boolean
  label: string
}>()

const emit = defineEmits<{
  edit: []
  save: []
  cancel: []
}>()
</script>

<template>
  <ButtonGroup class="shrink-0">
    <template v-if="props.editing">
      <slot />
      <Button
        size="icon-sm"
        :title="`Save ${props.label}`"
        :aria-label="`Save ${props.label}`"
        @click="emit('save')"
      >
        <Check aria-hidden="true" />
      </Button>
      <Button
        size="icon-sm"
        variant="outline"
        :title="`Cancel ${props.label} editing`"
        :aria-label="`Cancel ${props.label} editing`"
        @click="emit('cancel')"
      >
        <X aria-hidden="true" />
      </Button>
    </template>
    <Button
      v-else
      size="icon-sm"
      variant="ghost"
      :title="`Edit ${props.label}`"
      :aria-label="`Edit ${props.label}`"
      @click="emit('edit')"
    >
      <Pencil aria-hidden="true" />
    </Button>
  </ButtonGroup>
</template>
