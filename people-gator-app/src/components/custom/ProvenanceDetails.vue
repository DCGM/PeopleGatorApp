<script setup lang="ts">
import type { EntityResponse, FaceResponse, TextMentionResponse } from '@/client'
import { originOptions } from '@/viewmodels/evidence-filters'
const props = defineProps<{
  record: EntityResponse | FaceResponse | TextMentionResponse
  label: string
}>()
function format(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : 'Not recorded'
}
</script>
<template>
  <details class="max-w-full break-words">
    <summary>
      {{ label }}:
      {{
        originOptions.find((o) => o.id === props.record.provenance?.origin)?.label ??
        'Unknown / not recorded'
      }}
    </summary>
    <p v-if="record.provenance?.source_name">Source: {{ record.provenance.source_name }}</p>
    <p v-if="record.provenance?.reference_id">
      Reference:
      <a
        v-if="record.provenance.reference_url"
        :href="record.provenance.reference_url"
        target="_blank"
        rel="noopener noreferrer"
        >{{ record.provenance.reference_id }}</a
      >
      <span v-else>{{ record.provenance.reference_id }} (link not recorded)</span>
    </p>
    <p>Recorded creation / ingestion: {{ format(record.created_at) }}</p>
    <p>Creation / import actor: {{ record.created_by_user_id ?? 'Not recorded' }}</p>
    <p>
      Creation / import API key:
      {{ record.created_by_api_key_id ?? (record.created_at ? 'None (JWT)' : 'Not recorded') }}
    </p>
    <template v-if="'entity_link_state' in record">
      <p>Annotation last changed: {{ format(record.last_touched_at) }}</p>
      <p>Annotation last user: {{ record.last_touched_by_user_id ?? 'Not recorded' }}</p>
      <p>
        Annotation last API key:
        {{
          record.last_touched_by_api_key_id ??
          (record.last_touched_at ? 'None (JWT)' : 'Not recorded')
        }}
      </p>
      <p>Source ID: {{ record.source_id }}</p>
    </template>
  </details>
</template>
