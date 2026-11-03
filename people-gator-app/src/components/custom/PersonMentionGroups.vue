<script setup lang="ts">
import PersonNameTitle from './PersonNameTitle.vue'
import { computed, ref, watch } from 'vue'
import { Minus, Check, BadgeCheck, Unlink } from '@lucide/vue'
import { Checkbox } from '@/components/ui/checkbox'
import { useCanAnnotate } from '@/composables/can-annotate'
import { useAutomaticPagination } from '@/composables/automatic-pagination'
import { resolveMentionTargets, useReviewMentionsMutation } from '@/query/mention-review'
import { useRoute } from 'vue-router'
import type {
  TextMentionGroup,
  TextMentionResponse,
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

const props = withDefaults(
  defineProps<{
    mode?: 'mention' | 'document' | 'page'
    filters: TextMentionListParams
    groupSort: SortState<TextMentionGroupSortField>
    occurrenceSort: SortState<TextMentionSortField>
    personId?: string
    linkStates: EntityLinkState[]
    enabled?: boolean
    compact?: boolean
    /** Show occurrences under each group in their compact form. */
    compactOccurrences?: boolean
    /** Show phrase headings in the person-card name style (the scan sidebar). */
    cardTitles?: boolean
    /** Load further groups when the list end scrolls into view. */
    automatic?: boolean
    /** Offer selection and the selected-mention review actions. */
    selectable?: boolean
  }>(),
  { enabled: true, mode: 'mention', selectable: true },
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
const listEnd = ref<HTMLElement | null>(null)
useAutomaticPagination({
  target: listEnd,
  hasNextPage: query.hasNextPage,
  isFetching: query.isFetching,
  error: query.error,
  enabled: () => Boolean(props.automatic) && props.enabled,
  loadMore: () => query.fetchNextPage(),
})
const total = computed(() => query.data.value?.pages[0]?.total_count ?? 0)
const canAnnotate = useCanAnnotate()
const allowed = computed(() => props.selectable && canAnnotate.value)
const mutation = useReviewMentionsMutation()
const route = useRoute()
type Selection = { all: boolean; ids: string[] }
const selected = ref<Record<string, Selection>>({})
const groupAnchor = ref<string | null>(null)
const mentionAnchor = ref<string | null>(null)
const shiftSelecting = ref(false)
type SelectedMention = { id: string; version: number; verified?: boolean }
const groupSnapshots = new Map<string, Promise<{ items: SelectedMention[]; error?: string }>>()
const selectedVerified = ref<Record<string, boolean>>({})
const loadedVersions = ref<Record<string, number>>({})
const selectedVersions = ref<Record<string, number>>({})
const loadedMentions = ref<Record<string, string[]>>({})
const verifiedMentions = ref<Record<string, string[]>>({})
function clear() {
  groupSnapshots.clear()
  selectedVersions.value = {}
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
  for (const item of targets) {
    if (range || value === true) {
      const versions = new Map<string, number>()
      const records = new Map<string, TextMentionResponse>()
      groupSnapshots.set(
        key(item),
        resolveMentionTargets({ scopes: [scope(item)] }, 'unlink', versions, records)
          .then((ids) => ({
            items: ids.map((id) => ({
              id,
              version: versions.get(id)!,
              verified: records.get(id)?.entity_link_state === 'verified',
            })),
          }))
          .catch(() => ({
            items: [],
            error: 'Could not load the selection. Select the group again.',
          })),
      )
    } else groupSnapshots.delete(key(item))
  }
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
  if (value) {
    selectedVersions.value[id] = loadedVersions.value[id]!
    selectedVerified.value[id] = Object.values(verifiedMentions.value).flat().includes(id)
  } else delete selectedVersions.value[id]
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
    const items: SelectedMention[] = []
    for (const group of selectedGroups.value) {
      const state = selection(group)
      if (state.all) {
        const snapshot = await groupSnapshots.get(key(group))
        if (!snapshot || snapshot.error)
          throw new Error(snapshot?.error ?? 'Select the group again before updating.')
        items.push(...snapshot.items.filter((item) => !state.ids.includes(item.id)))
      } else {
        items.push(
          ...state.ids.map((id) => ({
            id,
            version: selectedVersions.value[id]!,
            verified: selectedVerified.value[id],
          })),
        )
      }
    }
    const count = await mutation.mutateAsync({
      targets: { items: action === 'verify' ? items.filter((item) => !item.verified) : items },
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
                  query: { document: group.source_id! },
                }"
                class="block truncate underline"
                :title="`${group.library} · ${group.document_id}`"
                >{{ group.library }} · {{ group.name }}</RouterLink
              ></span
            >
            <span
              v-else-if="mode === 'page' && group.source_kind === 'page'"
              class="min-w-0 flex-1 font-sans"
              ><RouterLink
                :to="{
                  name: 'document-page',
                  params: {
                    libraryId: group.library!,
                    documentId: group.document_id!,
                    pageId: group.page_id!,
                  },
                  query: {
                    selectedPerson: personId,
                  },
                }"
                class="block truncate underline"
                :title="`${group.library} · ${group.document_id} · ${group.page_id}`"
                >{{ group.library }} · {{ group.name }} · {{ group.page_id }}</RouterLink
              ></span
            >
            <div v-else-if="cardTitles && mode === 'mention'" class="min-w-0 flex-1">
              <PersonNameTitle :name="group.name" />
            </div>
            <span v-else class="min-w-0 flex-1 break-words font-sans"
              ><span :class="mode === 'mention' && 'font-serif'">{{ group.name }}</span>
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
            :compact="compactOccurrences"
            :selectable="selectable"
            :selection="selection(group)"
            :disabled="mutation.isPending.value"
            @loaded="
              (ids, verified, items) => {
                for (const item of items) loadedVersions[item.id] = item.version
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
    <div
      v-if="automatic && query.hasNextPage.value"
      ref="listEnd"
      class="h-px"
      aria-hidden="true"
    />
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
