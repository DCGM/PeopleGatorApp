<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { BadgeCheck, Unlink } from '@lucide/vue'
import { useRoute } from 'vue-router'
import { Button } from '@/components/ui/button'
import SelectedEvidenceActions from './SelectedEvidenceActions.vue'
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
  <div class="min-w-0" :class="!selection && selected.size > 0 && 'pb-40 sm:pb-24'">
    <SelectedEvidenceActions
      v-if="!selection && selected.size && allowed"
      :count="selected.size"
      :busy="mutation.isPending.value"
      singular="mention"
      plural="mentions"
      label="Selected mention actions"
      @clear="selected = new Set()"
    >
      <template #description>
        <p v-if="feedback" :role="mutation.isError.value ? 'alert' : 'status'">{{ feedback }}</p>
      </template>
      <Button
        size="sm"
        variant="outline"
        :disabled="mutation.isPending.value"
        class="border-destructive text-destructive hover:bg-destructive/10 hover:text-destructive dark:border-destructive dark:hover:bg-destructive/10"
        @click="review('unlink')"
        ><Unlink aria-hidden="true" />Unlink</Button
      >
      <Button
        size="sm"
        variant="outline"
        :disabled="mutation.isPending.value"
        class="border-emerald-600 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800 dark:border-emerald-500 dark:text-emerald-400 dark:hover:bg-emerald-950 dark:hover:text-emerald-300"
        @click="review('verify')"
        ><BadgeCheck aria-hidden="true" />Verify</Button
      >
    </SelectedEvidenceActions>
    <p v-if="feedback && !selected.size" :role="mutation.isError.value ? 'alert' : 'status'">
      {{ feedback }}
    </p>
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
