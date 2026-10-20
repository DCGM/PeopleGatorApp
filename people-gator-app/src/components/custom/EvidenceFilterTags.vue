<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useEvidenceFilters, originOptions, evidenceKeys } from '@/viewmodels/evidence-filters'
import type { EvidenceFilters } from '@/viewmodels/evidence-filters'
import { linkStateVisuals } from '@/lib/entity-links'
import { usePeopleFilterOptions } from '@/query/people-filter-options'
import ActiveFilters, { type ActiveFilter } from './ActiveFilters.vue'
const props = defineProps<{
  hideState?: boolean
  hideDocuments?: boolean
  additionalFilters?: ActiveFilter[]
}>()
const emit = defineEmits<{ removeAdditional: [filter: ActiveFilter] }>()
const route = useRoute(),
  router = useRouter()
const { filters, error } = useEvidenceFilters()
const empty = ref('')
const documents = usePeopleFilterOptions('document', empty, false),
  users = usePeopleFilterOptions('user', empty, false),
  keys = usePeopleFilterOptions('api-key', empty, false)
const tags = computed(() => {
  const f = filters.value
  const labels: Record<string, Record<string, string>> = {
    origins: Object.fromEntries(originOptions.map((o) => [o.id, o.label])),
    documentIds: documents.labels.value,
    userIds: users.labels.value,
    apiKeyIds: keys.labels.value,
  }
  const prefixes: Record<string, string> = {
    origins: 'Evidence origin',
    libraries: 'Evidence library',
    documentIds: 'Evidence document',
    sourceIds: 'Evidence source',
    userIds: 'Annotation last user',
    apiKeyIds: 'Annotation last API key',
  }
  return [
    ...(['assigned', 'unassigned'].includes(String(route.query.discovery_assignment))
      ? [
          {
            key: '$discovery_assignment',
            value: String(route.query.discovery_assignment),
            label: `Discovery assignment: ${route.query.discovery_assignment === 'assigned' ? 'Assigned elsewhere' : 'Unassigned'}`,
          },
        ]
      : []),
    ...Object.entries(route.query)
      .filter(
        ([key, value]) =>
          key.startsWith('evidence_') && value && !Object.values(f).flat().includes(String(value)),
      )
      .flatMap(([key, value]) => {
        if (!error.value) return []
        if ((key === 'evidence_from' && f.touchedFrom) || (key === 'evidence_to' && f.touchedTo))
          return []
        return [
          {
            key: '$' + key,
            value: String(value),
            label: `Invalid ${key.replace(/_/g, ' ')}: ${String(value)}`,
          },
        ]
      }),
    ...f.states.map((value) => ({
      key: 'states',
      value,
      label: `Link state: ${linkStateVisuals[value].label}`,
    })),
    ...Object.entries(prefixes).flatMap(([key, prefix]) =>
      (f[key as keyof EvidenceFilters] as string[]).map((value) => ({
        key,
        value,
        label: `${prefix}: ${labels[key]?.[value] ?? value}`,
      })),
    ),
    ...(['touchedFrom', 'touchedTo'] as const).flatMap((key) =>
      f[key]
        ? [
            {
              key,
              value: f[key],
              label: `Annotation touched ${key === 'touchedFrom' ? 'from' : 'to'}: ${f[key].replace('T', ' ')}`,
            },
          ]
        : [],
    ),
  ]
})
function remove(chip: ActiveFilter) {
  if (chip.key.startsWith('additional:')) {
    emit('removeAdditional', { ...chip, key: chip.key.slice(11), label: chip.label })
    return
  }
  if (chip.key.startsWith('$')) {
    void router.push({ query: { ...route.query, [chip.key.slice(1)]: undefined } })
    return
  }
  const key = chip.key as keyof EvidenceFilters,
    value = filters.value[key]
  filters.value = {
    ...filters.value,
    [key]: Array.isArray(value) ? value.filter((v) => v !== chip.value) : '',
  }
}
const combinedTags = computed(() => [
  ...tags.value.filter(
    (tag) =>
      !(props.hideState && tag.key === 'states') &&
      !(props.hideDocuments && tag.key === 'documentIds'),
  ),
  ...(props.additionalFilters ?? []).map((tag) => ({ ...tag, key: 'additional:' + tag.key })),
])
function clearPanel() {
  const keys = new Set<string>([
    ...evidenceKeys,
    'touched_from',
    'touched_to',
    'touched_by',
    'api_key',
    'library',
    'document',
    'assignment',
    'filters',
    'unassigned',
    'discovery_assignment',
  ])
  void router.push({
    query: Object.fromEntries(Object.entries(route.query).filter(([key]) => !keys.has(key))),
  })
}
</script>
<template>
  <p v-if="error" role="alert">{{ error }}</p>
  <ActiveFilters :filters="combinedTags" @remove="remove" @clear="clearPanel" />
</template>
