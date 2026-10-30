<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Minus, Check, BadgeCheck, Unlink } from '@lucide/vue'
import { Checkbox } from '@/components/ui/checkbox'
import { useCanAnnotate } from '@/composables/can-annotate'
import { useReviewMentionsMutation } from '@/query/mention-review'
import { useRoute } from 'vue-router'
import type {
  TextMentionGroup,
  EntityLinkState,
  TextMentionGroupSortField,
  TextMentionSortField,
} from '@/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import SelectedEvidenceActions from './SelectedEvidenceActions.vue'
import PersonMentionOccurrences from './PersonMentionOccurrences.vue'
import PersonMentionListSkeleton from './PersonMentionListSkeleton.vue'
import { sortParams, type SortState } from '@/lib/sorting'
import { useTextMentionGroupsQuery, type TextMentionListParams } from '@/query/text-mentions'
import { relatedQuery } from '@/viewmodels/shared-filters'

const props = withDefaults(
  defineProps<{
    mode?: 'mention' | 'document' | 'page'
    filters: TextMentionListParams
    groupSort: SortState<TextMentionGroupSortField>
    occurrenceSort: SortState<TextMentionSortField>
    personId: string
    linkStates: EntityLinkState[]
    enabled?: boolean
    compact?: boolean
  }>(),
  { enabled: true, mode: 'mention' },
)
const emit = defineEmits<{ broaden: [] }>()
const query = useTextMentionGroupsQuery(
  computed(() => ({
    ...props.filters,
    group_by: props.mode,
    ...sortParams(props.groupSort),
    limit: 25,
    return_total_count: true,
  })),
  computed(() => props.enabled),
)
const groups = computed(() => (query.data.value?.pages ?? []).flatMap((page) => page.items))
const total = computed(() => query.data.value?.pages[0]?.total_count ?? 0)
const allowed = useCanAnnotate()
const mutation = useReviewMentionsMutation()
const route = useRoute()
type Selection = { all: boolean; ids: string[] }
const selected = ref<Record<string, Selection>>({})
const groupAnchor = ref<string | null>(null)
const mentionAnchor = ref<string | null>(null)
const shiftSelecting = ref(false)
const loadedMentions = ref<Record<string, string[]>>({})
const verifiedMentions = ref<Record<string, string[]>>({})
function clear() {
  selected.value = {}
  groupAnchor.value = null
  mentionAnchor.value = null
}
const emptySelection: Selection = { all: false, ids: [] }
const selection = (group: TextMentionGroup) => selected.value[key(group)] ?? emptySelection
const selectionCount = (group: TextMentionGroup) => {
  const state = selection(group)
  return state.all ? Math.max(0, group.occurrence_count - state.ids.length) : state.ids.length
}
const checked = (group: TextMentionGroup): boolean | 'indeterminate' => {
  const count = selectionCount(group)
  return count === 0 ? false : count >= group.occurrence_count ? true : 'indeterminate'
}
const feedback = ref('')
const key = (group: TextMentionGroup) => group.source_id ?? group.name
const selectedGroups = computed(() => groups.value.filter((g) => selectionCount(g) > 0))
const selectedCount = computed(() =>
  selectedGroups.value.reduce((count, g) => count + selectionCount(g), 0),
)
function scope(group: TextMentionGroup): TextMentionListParams {
  return {
    ...props.filters,
    ...(props.mode === 'mention'
      ? { 'filter.name': [group.name] }
      : group.source_kind === 'document'
        ? { 'filter.document_source_id': [group.source_id!] }
        : { 'filter.source_id': [group.source_id!] }),
  }
}
function select(group: TextMentionGroup, value: boolean | 'indeterminate') {
  const start = groups.value.findIndex((item) => key(item) === groupAnchor.value)
  const end = groups.value.findIndex((item) => key(item) === key(group))
  const range = shiftSelecting.value && start >= 0 && end >= 0
  const targets = range
    ? groups.value.slice(Math.min(start, end), Math.max(start, end) + 1)
    : [group]
  selected.value = {
    ...selected.value,
    ...Object.fromEntries(
      targets.map((item) => [key(item), { all: range || value === true, ids: [] }]),
    ),
  }
  if (!range) groupAnchor.value = key(group)
  shiftSelecting.value = false
  feedback.value = ''
}
function selectMention(group: TextMentionGroup, id: string, value: boolean, shift = false) {
  const ordered = groups.value.flatMap((item) =>
    (loadedMentions.value[key(item)] ?? []).map((id) => ({ id, group: item })),
  )
  const start = ordered.findIndex((item) => item.id === mentionAnchor.value)
  const end = ordered.findIndex((item) => item.id === id)
  if (shift && start >= 0 && end >= 0) {
    for (const item of ordered.slice(Math.min(start, end), Math.max(start, end) + 1))
      setMention(item.group, item.id, true)
  } else {
    setMention(group, id, value)
    mentionAnchor.value = id
  }
}
function setMention(group: TextMentionGroup, id: string, value: boolean) {
  const state = selection(group)
  const ids = new Set(state.ids)
  if (value !== state.all) ids.add(id)
  else ids.delete(id)
  selected.value = { ...selected.value, [key(group)]: { all: state.all, ids: [...ids] } }
  feedback.value = ''
}
async function review(action: 'verify' | 'unlink') {
  if (!allowed.value || mutation.isPending.value) return
  try {
    const count = await mutation.mutateAsync({
      targets: {
        scopes: selectedGroups.value.filter((g) => selection(g).all).map(scope),
        ids: selectedGroups.value.filter((g) => !selection(g).all).flatMap((g) => selection(g).ids),
        excludeIds: selectedGroups.value
          .filter((g) => selection(g).all)
          .flatMap((g) => selection(g).ids),
        verifiedIds: Object.values(verifiedMentions.value).flat(),
      },
      action,
    })
    feedback.value = `${count} mentions ${action === 'verify' ? 'verified' : 'unlinked'}.`
    clear()
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : 'Update failed.'
  }
}
watch(
  () =>
    JSON.stringify([
      props.personId,
      route.params.personId,
      route.query.mention_view,
      props.filters,
      props.mode,
      props.groupSort,
      props.occurrenceSort,
    ]),
  () => {
    clear()
    feedback.value = ''
  },
)
// Retain selection while new group pages arrive, but discard removed groups.
watch(groups, (items) => {
  const names = new Set(items.map(key))
  loadedMentions.value = Object.fromEntries(
    Object.entries(loadedMentions.value).filter(([name]) => names.has(name)),
  )
  verifiedMentions.value = Object.fromEntries(
    Object.entries(verifiedMentions.value).filter(([name]) => names.has(name)),
  )
  if (groupAnchor.value && !names.has(groupAnchor.value)) groupAnchor.value = null
  if (
    mentionAnchor.value &&
    !Object.values(loadedMentions.value).flat().includes(mentionAnchor.value)
  )
    mentionAnchor.value = null
  selected.value = Object.fromEntries(
    Object.entries(selected.value).filter(([name]) => names.has(name)),
  )
})
</script>

<template>
  <div :class="selectedCount > 0 && 'pb-40 sm:pb-24'">
    <SelectedEvidenceActions
      v-if="allowed && selectedCount"
      :count="selectedCount"
      :busy="mutation.isPending.value"
      singular="mention"
      plural="mentions"
      label="Selected group actions"
      @clear="clear"
    >
      <template #description>
        <span>Filtered scope</span>
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
    <p v-if="feedback && !selectedCount" :role="mutation.isError.value ? 'alert' : 'status'">
      {{ feedback }}
    </p>
    <ul class="divide-y" :aria-label="`${mode} groups`">
      <li v-for="group in groups" :key="key(group)">
        <div class="flex min-w-0 items-center gap-2">
          <Checkbox
            v-if="allowed"
            :aria-label="`Select group ${group.name}`"
            :model-value="checked(group)"
            :disabled="mutation.isPending.value"
            @click.capture="shiftSelecting = $event.shiftKey"
            @update:model-value="select(group, $event)"
            ><Minus v-if="checked(group) === 'indeterminate'" class="size-3.5" /><Check
              v-else
              class="size-3.5"
          /></Checkbox>
          <div class="flex min-w-0 flex-1 items-center gap-3 py-3">
            <span
              v-if="mode === 'document' && group.source_kind === 'document'"
              class="min-w-0 flex-1 font-sans"
              ><RouterLink
                :to="{
                  name: 'document-search',
                  query: relatedQuery(route, { document: group.source_id! }),
                }"
                class="underline wrap-anywhere"
                :title="`${group.library} · ${group.document_id}`"
                >{{ group.library }} · {{ group.name }}</RouterLink
              ></span
            >
            <span v-else class="min-w-0 flex-1 break-words font-sans"
              ><span :class="mode === 'mention' && 'text-secondary underline underline-offset-2'">{{
                group.name
              }}</span>
              <small v-if="mode !== 'mention'" class="block text-muted-foreground wrap-anywhere"
                >{{ group.library }} · {{ group.document_id ?? group.source_id
                }}<template v-if="group.page_id"> · {{ group.page_id }}</template></small
              >
            </span>
            <Badge variant="outline" class="font-mono">
              {{ group.occurrence_count }}
              {{ group.occurrence_count === 1 ? 'occurrence' : 'occurrences' }}
            </Badge>
          </div>
        </div>
        <div v-if="!compact" class="pl-7">
          <PersonMentionOccurrences
            :name="mode === 'mention' ? group.name : undefined"
            :compact="compact"
            :selection="selection(group)"
            :disabled="mutation.isPending.value"
            @loaded="
              (ids, verified) => {
                loadedMentions[key(group)] = ids
                verifiedMentions[key(group)] = verified
              }
            "
            @select-mention="(id, value, shift) => selectMention(group, id, value, shift)"
            :filters="scope(group)"
            :sort="occurrenceSort"
            :person-id="personId"
            :link-states="linkStates"
          />
        </div>
      </li>
    </ul>
    <PersonMentionListSkeleton
      v-if="enabled && (query.isPending.value || query.isFetchingNextPage.value)"
      :mode="mode"
      :class="groups.length > 0 && 'border-t'"
      :compact="compact"
      :count="query.isPending.value ? 3 : 2"
    />
    <div class="py-3 text-sm">
      <p v-if="query.error.value" role="alert">
        Could not load mention groups.
        <Button variant="link" @click="query.refetch()">Retry</Button>
      </p>
      <p v-else-if="!query.isPending.value">Showing {{ groups.length }} of {{ total }} groups</p>
      <p v-if="!query.error.value && !query.isPending.value && !groups.length">
        No mentions match the filters.
        <Button variant="link" @click="emit('broaden')">Clear filters</Button>
      </p>
      <Button
        v-if="query.hasNextPage.value"
        variant="outline"
        :disabled="query.isFetchingNextPage.value"
        @click="query.fetchNextPage()"
        >Load more groups</Button
      >
    </div>
  </div>
</template>
