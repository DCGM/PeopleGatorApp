<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import ActiveFilters from './ActiveFilters.vue'
import { useEvidenceFilters } from '@/viewmodels/evidence-filters'
import { activityGroups, localDayBounds, usePageActivity } from '@/viewmodels/page-activity'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
const props = defineProps<{ sourceId: string }>()
const route = useRoute(),
  router = useRouter()
const { items, loading, error, retry } = usePageActivity(() => props.sourceId)
const { filters } = useEvidenceFilters()
const userSearch = ref('')
const users = usePeopleFilterOptions('user', userSearch)
const mode = computed(() => (route.query.activity_group === 'user' ? 'user' : 'time'))
const groups = computed(() => activityGroups(items.value, mode.value))
const tags = computed(() => [
  ...(['touchedFrom', 'touchedTo'] as const).flatMap((key) =>
    filters.value[key]
      ? [
          {
            key,
            value: filters.value[key],
            label: `Annotation ${key === 'touchedFrom' ? 'from' : 'to'}: ${filters.value[key].replace('T', ' ')}`,
          },
        ]
      : [],
  ),
  ...filters.value.userIds.map((value) => ({
    key: 'userIds',
    value,
    label: `Annotation user: ${users.labels.value[value] ?? value}`,
  })),
])
function selectGroup(key: string) {
  if (!key) return
  if (mode.value === 'user')
    filters.value = {
      ...filters.value,
      userIds: filters.value.userIds.length === 1 && filters.value.userIds[0] === key ? [] : [key],
    }
  else {
    const bounds = localDayBounds(key)
    filters.value = {
      ...filters.value,
      ...(filters.value.touchedFrom === bounds.touchedFrom &&
      filters.value.touchedTo === bounds.touchedTo
        ? { touchedFrom: '', touchedTo: '' }
        : bounds),
    }
  }
}
function selected(key: string) {
  if (!key) return false
  if (mode.value === 'user') return filters.value.userIds.includes(key)
  const bounds = localDayBounds(key)
  return (
    filters.value.touchedFrom === bounds.touchedFrom && filters.value.touchedTo === bounds.touchedTo
  )
}
function label(key: string) {
  return key
    ? mode.value === 'user'
      ? (users.labels.value[key] ?? key)
      : new Date(key + 'T12:00:00').toLocaleDateString()
    : mode.value === 'user'
      ? 'User not recorded'
      : 'Edit time not recorded'
}
function remove(chip: { key: string; value: string }) {
  filters.value = {
    ...filters.value,
    [chip.key]:
      chip.key === 'userIds' ? filters.value.userIds.filter((value) => value !== chip.value) : '',
  }
}
function clear() {
  filters.value = { ...filters.value, touchedFrom: '', touchedTo: '', userIds: [] }
}
</script>
<template>
  <section class="min-w-0 space-y-3 p-5" aria-label="Page annotation activity">
    <h3>Annotation activity</h3>
    <p>
      <small
        >Latest face and mention edits on this page. Group by local day or last editor; select a
        group to filter the scan.</small
      >
    </p>
    <Tabs
      :model-value="mode"
      @update:model-value="
        (value) =>
          router.push({
            query: { ...route.query, activity_group: value === 'user' ? 'user' : undefined },
          })
      "
    >
      <TabsList aria-label="Group page activity"
        ><TabsTrigger value="time">By day</TabsTrigger
        ><TabsTrigger value="user">By user</TabsTrigger></TabsList
      >
    </Tabs>
    <ActiveFilters :filters="tags" @remove="remove" @clear="clear" />
    <p v-if="error" role="alert">
      Could not load activity. <Button variant="link" @click="retry">Retry</Button>
    </p>
    <p v-else-if="loading" role="status">Loading all page annotations…</p>
    <p v-else-if="!groups.length">No face or mention activity on this page.</p>
    <div v-else class="max-h-72 space-y-3 overflow-y-auto">
      <section v-for="group in groups" :key="group.key" class="min-w-0 space-y-2">
        <Button
          v-if="group.key"
          type="button"
          :variant="selected(group.key) ? 'secondary' : 'outline'"
          class="w-full max-w-full justify-between"
          :aria-pressed="selected(group.key)"
          :aria-label="`Filter ${mode === 'user' ? 'user' : 'day'} ${label(group.key)}`"
          @click="selectGroup(group.key)"
        >
          <span class="min-w-0 truncate">{{ label(group.key) }}</span
          ><span>{{ group.faces }} faces · {{ group.mentions }} mentions</span>
        </Button>
        <p v-else>
          {{ label(group.key) }} · {{ group.faces }} faces · {{ group.mentions }} mentions
        </p>
        <ul class="space-y-2" :aria-label="`Annotations for ${label(group.key)}`">
          <li v-for="item in group.records" :key="item.id" class="min-w-0 break-words">
            <small
              >{{ item.kind === 'face' ? 'Face' : 'Mention' }} · {{ item.label }}<br /><time
                v-if="item.touchedAt"
                :datetime="item.touchedAt"
                :title="item.touchedAt"
                >{{ new Date(item.touchedAt).toLocaleString() }}</time
              ><span v-else>Edit time not recorded</span></small
            >
          </li>
        </ul>
      </section>
    </div>
  </section>
</template>
