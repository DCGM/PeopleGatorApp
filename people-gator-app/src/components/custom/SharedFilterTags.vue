<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  invalidSharedValues,
  legacyFilterNotice,
  sharedKeys,
  useSharedFilters,
  type SharedFilters,
} from '@/viewmodels/shared-filters'
import { linkStateVisuals } from '@/lib/entity-links'
import { useActorLabels, useSourceLabels } from '@/query/people-filter-options'
import ActiveFilters, { type ActiveFilter } from './ActiveFilters.vue'

// Shared tags first, then the screen's specific filters. Clear all keeps search,
// sort and view-specific state such as tabs; clearing search is separate.
const props = defineProps<{
  specificFilters?: ActiveFilter[]
  /** URL keys of the screen's specific filters, cleared together with shared ones. */
  specificKeys?: string[]
  /** Document values with a screen-specific meaning, such as unregistered archive IDs. */
  documentLabels?: Record<string, string>
}>()
const emit = defineEmits<{ removeSpecific: [filter: ActiveFilter] }>()
const route = useRoute(),
  router = useRouter()
const { filters, error } = useSharedFilters()
const users = useActorLabels('user', () => filters.value.userIds),
  keys = useActorLabels('api-key', () => filters.value.apiKeyIds)
const documents = useSourceLabels('document', () => filters.value.documentIds)
const pages = useSourceLabels('page', () => filters.value.pageIds)
const prefixes: [keyof SharedFilters, string][] = [
  ['libraries', 'Library'],
  ['documentIds', 'Document'],
  ['pageIds', 'Page'],
  ['userIds', 'Modified by'],
  ['apiKeyIds', 'Modified via key'],
]
const tags = computed<ActiveFilter[]>(() => {
  const f = filters.value
  const labels: Partial<Record<keyof SharedFilters, Record<string, string>>> = {
    documentIds: { ...documents.labels.value, ...props.documentLabels },
    pageIds: pages.labels.value,
    userIds: users.labels.value,
    apiKeyIds: keys.labels.value,
  }
  return [
    ...prefixes.flatMap(([key, prefix]) =>
      (f[key] as string[]).map((value) => ({
        key,
        value,
        label: `${prefix}: ${labels[key]?.[value] ?? value}`,
      })),
    ),
    ...f.linkStates.map((value) => ({
      key: 'linkStates',
      value,
      label: `Link state: ${linkStateVisuals[value].label}`,
    })),
    ...(['touchedFrom', 'touchedTo'] as const).flatMap((key) =>
      f[key]
        ? [
            {
              key,
              value: f[key],
              label: `Modified ${key === 'touchedFrom' ? 'from' : 'to'}: ${f[key].replace('T', ' ')}`,
            },
          ]
        : [],
    ),
    ...invalidSharedValues(route.query).map(({ key, value }) => ({
      key: '$' + key,
      value,
      label: `Invalid ${key.replace(/_/g, ' ')}: ${value}`,
    })),
  ]
})
function remove(chip: ActiveFilter) {
  if (chip.key.startsWith('specific:')) {
    emit('removeSpecific', { ...chip, key: chip.key.slice(9) })
    return
  }
  if (chip.key.startsWith('$')) {
    const key = chip.key.slice(1)
    const values = [route.query[key]].flat().filter((value) => value !== chip.value)
    void router.push({ query: { ...route.query, [key]: values.length ? values : undefined } })
    return
  }
  const key = chip.key as keyof SharedFilters,
    value = filters.value[key]
  filters.value = {
    ...filters.value,
    [key]: Array.isArray(value) ? value.filter((v) => v !== chip.value) : '',
  }
}
const combined = computed(() => [
  ...tags.value,
  ...(props.specificFilters ?? []).map((tag) => ({ ...tag, key: 'specific:' + tag.key })),
])
function clearAll() {
  const cleared = new Set<string>([...sharedKeys, ...(props.specificKeys ?? [])])
  void router.push({
    query: Object.fromEntries(Object.entries(route.query).filter(([key]) => !cleared.has(key))),
  })
}
</script>
<template>
  <p v-if="legacyFilterNotice.length" role="status" class="mt-2 text-sm">
    Removed unsupported filters from this link: {{ legacyFilterNotice.join(', ') }}.
  </p>
  <p v-if="error" role="alert" class="mt-2 text-sm text-destructive">{{ error }}</p>
  <ActiveFilters :filters="combined" @remove="remove" @clear="clearAll" />
</template>
