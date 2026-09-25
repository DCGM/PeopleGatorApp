<script setup lang="ts">
import { Search, X } from '@lucide/vue'
import { ref } from 'vue'

import type { Face } from '@/viewmodels/document-workspace.types'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'

const props = defineProps<{
  selectedFace: Face | null
}>()

const query = defineModel<string>({ default: '' })
const inputElement = ref<InstanceType<typeof InputGroupInput> | null>(null)

function focus() {
  const input = inputElement.value?.$el as HTMLInputElement | undefined
  input?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  input?.focus()
}

defineExpose({ focus })
</script>

<template>
  <section aria-labelledby="similar-people-search-title">
    <p
      id="similar-people-search-title"
      class="font-mono text-xs font-semibold uppercase text-secondary"
    >
      {{ props.selectedFace?.personId ? 'Reassign to similar' : 'Assign to similar' }}
    </p>
    <InputGroup class="mt-2 w-full">
      <InputGroupAddon align="inline-start">
        <Search aria-hidden="true" />
      </InputGroupAddon>
      <InputGroupInput
        ref="inputElement"
        v-model="query"
        placeholder="Search by name or alias"
        aria-label="Search people"
        :disabled="!props.selectedFace"
      />
      <InputGroupAddon align="inline-end">
        <InputGroupButton
          v-if="query"
          type="button"
          size="icon-sm"
          aria-label="Clear people search"
          @click="query = ''"
        >
          <X aria-hidden="true" />
        </InputGroupButton>
      </InputGroupAddon>
    </InputGroup>
    <p
      v-if="props.selectedFace && !props.selectedFace.embeddingModel && !query.trim()"
      class="mt-2 text-xs text-muted-foreground"
    >
      Face similarity is unavailable for this detection. Search by name or alias instead.
    </p>
  </section>
</template>
