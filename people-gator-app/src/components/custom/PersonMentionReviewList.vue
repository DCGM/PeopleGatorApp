<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import PersonMentionEntry from './PersonMentionEntry.vue'
import { useCanAnnotate } from '@/composables/can-annotate'
import { useReviewMentionsMutation } from '@/query/mention-review'
import type { EntityLinkState } from '@/client'
import type { PersonMention } from '@/viewmodels/person-detail.types'
const props = defineProps<{
  mentions: PersonMention[]
  personId: string
  linkStates: EntityLinkState[]
  compact?: boolean
  selection?: { all: boolean; ids: string[] }
  disabled?: boolean
}>()
const emit = defineEmits<{ selectMention: [id: string, value: boolean] }>()
const selected = ref(new Set<string>())
const allowed = useCanAnnotate()
const mutation = useReviewMentionsMutation()
const route = useRoute()
const feedback = ref('')
const selectedMentions = computed(() => props.mentions.filter((m) => selected.value.has(m.id)))
function toggle(id: string, value: boolean | 'indeterminate') {
  if (props.selection) {
    emit('selectMention', id, value === true)
    return
  }
  const next = new Set(selected.value)
  if (value === true) next.add(id)
  else next.delete(id)
  selected.value = next
  feedback.value = ''
}
async function review(action: 'verify' | 'unlink') {
  if (!allowed.value || mutation.isPending.value) return
  const ids = selectedMentions.value
    .filter((m) => action === 'unlink' || m.linkState !== 'verified')
    .map((m) => m.id)
  try {
    const count = await mutation.mutateAsync({ targets: { ids }, action })
    feedback.value = `${count} mentions ${action === 'verify' ? 'verified' : 'unlinked'}.`
    selected.value = new Set()
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : 'Update failed.'
  }
}
watch(
  () =>
    JSON.stringify([
      route.params,
      Object.fromEntries(Object.entries(route.query).filter(([key]) => key !== 'mention_density')),
    ]),
  () => {
    selected.value = new Set()
    feedback.value = ''
  },
)
watch(
  () => props.mentions,
  (mentions) => {
    const available = new Set(mentions.map((m) => m.id))
    selected.value = new Set([...selected.value].filter((id) => available.has(id)))
  },
)
</script>
<template>
  <div class="min-w-0">
    <div
      v-if="!selection && selected.size && allowed"
      role="toolbar"
      aria-label="Selected mention actions"
      class="flex flex-wrap items-center gap-2 py-2"
    >
      <span>{{ selected.size }} selected</span>
      <Button
        size="sm"
        variant="outline"
        :disabled="mutation.isPending.value"
        @click="review('verify')"
        >Verify</Button
      >
      <Button
        size="sm"
        variant="outline"
        :disabled="mutation.isPending.value"
        @click="review('unlink')"
        >Unlink</Button
      >
      <Button
        size="sm"
        variant="ghost"
        :disabled="mutation.isPending.value"
        @click="selected = new Set()"
        >Clear</Button
      >
    </div>
    <p v-if="feedback" :role="mutation.isError.value ? 'alert' : 'status'">{{ feedback }}</p>
    <div
      v-for="mention in mentions"
      :key="mention.id"
      class="flex min-w-0 items-start gap-3 border-b py-2 last:border-b-0"
    >
      <Checkbox
        v-if="allowed"
        class="mt-1 shrink-0"
        :aria-label="`Select mention ${mention.id}`"
        :model-value="
          selection
            ? selection.all !== selection.ids.includes(mention.id)
            : selected.has(mention.id)
        "
        :disabled="disabled || mutation.isPending.value"
        @update:model-value="toggle(mention.id, $event)"
      />
      <PersonMentionEntry
        class="min-w-0 flex-1"
        :mention="mention"
        :person-id="personId"
        :link-states="linkStates"
        :compact="compact"
      />
    </div>
  </div>
</template>
