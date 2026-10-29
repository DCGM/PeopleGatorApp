<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronRight, Minus, Check } from '@lucide/vue'
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
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import PersonMentionOccurrences from './PersonMentionOccurrences.vue'
import PersonMentionItemSkeleton from './PersonMentionItemSkeleton.vue'
import { sortParams, type SortState } from '@/lib/sorting'
import { useTextMentionGroupsQuery, type TextMentionListParams } from '@/query/text-mentions'

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
  selected.value = { ...selected.value, [key(group)]: { all: value === true, ids: [] } }
  feedback.value = ''
}
function selectMention(group: TextMentionGroup, id: string, value: boolean) {
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
      },
      action,
    })
    feedback.value = `${count} mentions ${action === 'verify' ? 'verified' : 'unlinked'}.`
    selected.value = {}
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : 'Update failed.'
  }
}
watch(
  () =>
    JSON.stringify([
      props.personId,
      route.params.personId,
      props.filters,
      props.mode,
      props.groupSort,
      props.occurrenceSort,
    ]),
  () => {
    selected.value = {}
    feedback.value = ''
  },
)
const overrides = ref<Record<string, boolean>>({})
const isOpen = (group: TextMentionGroup) => overrides.value[key(group)] ?? !props.compact
function toggle(name: string, value: boolean) {
  overrides.value = { ...overrides.value, [name]: value }
}
watch(
  () => props.compact,
  () => {
    overrides.value = {}
  },
)
// Retain selection while new group pages arrive, but discard removed groups.
watch(groups, (items) => {
  const names = new Set(items.map(key))
  selected.value = Object.fromEntries(
    Object.entries(selected.value).filter(([name]) => names.has(name)),
  )
  overrides.value = Object.fromEntries(
    Object.entries(overrides.value).filter(([name]) => names.has(name)),
  )
})
</script>

<template>
  <div>
    <div
      v-if="allowed && selectedCount"
      role="toolbar"
      aria-label="Selected group actions"
      class="flex flex-wrap items-center gap-2 py-2"
    >
      <span>{{ selectedCount }} occurrences · filtered scope</span>
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
      <Button size="sm" variant="ghost" :disabled="mutation.isPending.value" @click="selected = {}"
        >Clear</Button
      >
    </div>
    <p v-if="feedback" :role="mutation.isError.value ? 'alert' : 'status'">{{ feedback }}</p>
    <ul class="divide-y" :aria-label="`${mode} groups`">
      <li v-for="group in groups" :key="key(group)">
        <Collapsible :open="isOpen(group)" @update:open="toggle(key(group), $event)">
          <div class="flex min-w-0 items-center gap-2">
            <Checkbox
              v-if="allowed"
              :aria-label="`Select group ${group.name}`"
              :model-value="checked(group)"
              :disabled="mutation.isPending.value"
              @update:model-value="select(group, $event)"
              ><Minus v-if="checked(group) === 'indeterminate'" class="size-3.5" /><Check
                v-else
                class="size-3.5"
            /></Checkbox>
            <CollapsibleTrigger as-child>
              <Button
                type="button"
                variant="ghost"
                class="h-auto min-w-0 flex-1 justify-start gap-3 py-3 text-left whitespace-normal"
              >
                <ChevronRight
                  class="size-4 shrink-0 transition-transform"
                  :class="isOpen(group) && 'rotate-90'"
                  aria-hidden="true"
                />
                <span class="min-w-0 flex-1 break-words font-sans"
                  ><span
                    :class="mode === 'mention' && 'text-secondary underline underline-offset-2'"
                    >{{ group.name }}</span
                  >
                  <small v-if="mode !== 'mention'" class="block text-muted-foreground"
                    >{{ group.library }} · {{ (group.document_id ?? group.source_id)?.slice(0, 8)
                    }}<template v-if="group.page_id">
                      · {{ group.page_id.slice(0, 8) }}</template
                    ></small
                  >
                </span>
                <Badge variant="outline" class="font-mono">
                  {{ group.occurrence_count }}
                  {{ group.occurrence_count === 1 ? 'occurrence' : 'occurrences' }}
                </Badge>
              </Button>
            </CollapsibleTrigger>
          </div>
          <CollapsibleContent class="pl-7">
            <PersonMentionOccurrences
              v-if="isOpen(group)"
              :name="mode === 'mention' ? group.name : undefined"
              :compact="compact"
              :selection="selection(group)"
              :disabled="mutation.isPending.value"
              @select-mention="(id, value) => selectMention(group, id, value)"
              :filters="scope(group)"
              :sort="occurrenceSort"
              :person-id="personId"
              :link-states="linkStates"
            />
          </CollapsibleContent>
        </Collapsible>
      </li>
    </ul>
    <PersonMentionItemSkeleton v-if="query.isPending.value && enabled" />
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
