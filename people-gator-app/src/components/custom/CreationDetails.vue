<script setup lang="ts">
import type { EntityResponse, FaceResponse, TextMentionResponse } from '@/client'
defineProps<{
  record: EntityResponse | FaceResponse | TextMentionResponse
  label: string
  expanded?: boolean
}>()
function format(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : 'Not recorded'
}
</script>
<template>
  <details :open="expanded" class="max-w-full break-words">
    <summary>{{ label }}</summary>
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
