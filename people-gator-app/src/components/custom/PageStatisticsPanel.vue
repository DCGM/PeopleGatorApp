<script setup lang="ts">
import PageNumberEditor from './PageNumberEditor.vue'
import type { DocumentResponse, PageResponse } from '@/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { linkStateVisuals } from '@/lib/entity-links'

defineProps<{
  page?: PageResponse | null
  document?: DocumentResponse | null
  loading?: boolean
  error?: boolean
}>()
defineEmits<{ retry: [] }>()
const states = ['automatic', 'manual', 'verified', 'unassigned'] as const
</script>

<template>
  <section class="min-w-0 space-y-5 p-5" aria-label="Page and document link statistics">
    <div>
      <h3>Link statistics</h3>
      <p class="mt-2 text-sm text-muted-foreground">
        All annotations, independent of the current evidence filters.
      </p>
    </div>
    <Card v-for="scope in ['page', 'document'] as const" :key="scope" class="min-w-0 gap-4">
      <CardHeader>
        <CardTitle>{{ scope === 'page' ? 'This page' : 'Whole document' }}</CardTitle>
        <p class="break-words text-xs text-muted-foreground [overflow-wrap:anywhere]">
          {{ page?.library }} · {{ page?.document_id
          }}<template v-if="scope === 'page'"> · {{ page?.page_id }}</template>
        </p>
      </CardHeader>
      <CardContent>
        <PageNumberEditor v-if="scope === 'page' && page" :page="page" />
        <p v-if="scope === 'document' && loading" role="status">Loading statistics…</p>
        <p v-else-if="scope === 'document' && error" role="alert">
          Could not load document statistics.
          <Button variant="link" @click="$emit('retry')">Retry</Button>
        </p>
        <div v-else-if="(scope === 'page' ? page : document)?.entity_link_stats" class="space-y-5">
          <section
            v-for="kind in ['faces', 'mentions'] as const"
            :key="kind"
            :aria-label="`${scope} ${kind}`"
          >
            <div class="mb-3 flex items-baseline justify-between gap-2">
              <h4 class="text-sm font-semibold capitalize">{{ kind }}</h4>
              <span class="text-sm tabular-nums"
                >{{
                  (scope === 'page' ? page : document)?.entity_link_stats?.[kind]?.total ?? 0
                }}
                total</span
              >
            </div>
            <dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <div
                v-for="state in states"
                :key="state"
                class="flex items-center justify-between gap-2"
              >
                <dt class="flex items-center gap-1.5">
                  <component
                    :is="linkStateVisuals[state].icon"
                    class="size-3 shrink-0"
                    aria-hidden="true"
                  />
                  {{ linkStateVisuals[state].label }}
                </dt>
                <dd class="tabular-nums">
                  {{
                    (scope === 'page' ? page : document)?.entity_link_stats?.[kind]?.[state] ?? 0
                  }}
                </dd>
              </div>
            </dl>
          </section>
        </div>
        <p v-else role="status">Statistics unavailable.</p>
      </CardContent>
    </Card>
  </section>
</template>
