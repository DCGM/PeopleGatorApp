<script setup lang="ts">
import { relatedQuery } from '@/viewmodels/shared-filters'
import { FileText, Scan, User } from '@lucide/vue'
import { computed } from 'vue'
import { RouterLink, useRoute, type RouteLocationRaw } from 'vue-router'

import PeopleGatorIcon from '@/components/custom/PeopleGatorIcon'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'

const route = useRoute()

const breadcrumbs = computed(() => {
  const library = route.params.libraryId
  const document = route.params.documentId
  const items = [
    {
      label: 'PeopleGator',
      to: { name: 'document-list', query: relatedQuery(route) } as RouteLocationRaw,
    },
  ]
  if (route.name === 'person-detail') {
    items.push({
      label: 'People',
      to: { name: 'people-search', query: relatedQuery(route) },
    })
    items.push({
      label: String(route.params.personId),
      to: { path: route.path, query: route.query },
    })
    return items
  }
  if (route.name === 'document-list') {
    items.push({
      label: 'Documents',
      to: { name: 'document-list', query: relatedQuery(route) },
    })
    return items
  }
  // A page's library/document crumbs open that scope in Scans. The archive
  // document ID resolves to its registered document there.
  if (route.name === 'document-page' && typeof library === 'string') {
    items.push({
      label: library,
      to: { name: 'document-search', query: relatedQuery(route, { library }) },
    })
    if (typeof document === 'string') {
      items.push({
        label: document,
        to: { name: 'document-search', query: relatedQuery(route, { library, archive_document: document }) },
      })
    }
    items.push({
      label: `Page ${String(route.params.pageId)}`,
      to: { path: route.path, query: route.query },
    })
  } else if (route.name === 'document-search') {
    items.push({ label: 'Scans', to: { name: 'document-search', query: route.query } })
  } else if (route.name === 'people-search' || route.name === 'person-detail') {
    items.push({
      label: 'People',
      to: { name: 'people-search', query: relatedQuery(route) },
    })
    if (route.name === 'person-detail') {
      items.push({
        label: String(route.params.personId),
        to: { path: route.path, query: route.query },
      })
    }
  }
  return items
})

const isScanRoute = computed(
  () => route.name === 'document-search' || route.name === 'document-page',
)
// Top-level navigation carries only the shared configuration; on Scans the
// tab keeps the current scan search.
const scansLink = computed(() => ({
  name: 'document-search',
  query: route.name === 'document-search' ? route.query : relatedQuery(route),
}))
const isPeopleRoute = computed(
  () => route.name === 'people-search' || route.name === 'person-detail',
)
</script>

<template>
  <nav
    class="sticky top-0 z-50 flex h-13 w-full items-center gap-2 border-b bg-background px-2 sm:gap-3 sm:px-4"
  >
    <div class="flex shrink-0 items-center gap-2">
      <RouterLink
        :to="{ name: 'document-list', query: relatedQuery(route) }"
        aria-label="PeopleGator"
        class="z-20 flex size-12 shrink-0 items-center justify-center bg-background"
      >
        <PeopleGatorIcon aria-hidden="true" class="size-10 text-primary" stroke-width="1" />
      </RouterLink>
    </div>

    <div class="min-w-0 flex-1">
      <Breadcrumb aria-label="Breadcrumb" class="min-w-0">
        <BreadcrumbList
          class="min-w-0 flex-nowrap gap-1 font-heading text-base font-extralight leading-normal sm:gap-2"
        >
          <template v-for="(crumb, index) in breadcrumbs" :key="index">
            <BreadcrumbSeparator v-if="index" class="shrink-0" />
            <BreadcrumbItem
              class="min-w-0"
              :class="index === breadcrumbs.length - 1 ? 'flex-[0_1_auto]' : 'flex-[0_2_auto]'"
            >
              <BreadcrumbLink
                as-child
                class="block min-w-0 truncate rounded-sm py-0.5 hover:text-primary focus-visible:outline-2 focus-visible:outline-primary"
                :class="
                  index === breadcrumbs.length - 1 ? 'text-foreground' : 'text-muted-foreground'
                "
              >
                <RouterLink
                  :to="crumb.to"
                  :title="crumb.label"
                  :aria-current="index === breadcrumbs.length - 1 ? 'page' : undefined"
                >
                  {{ crumb.label }}
                </RouterLink>
              </BreadcrumbLink>
            </BreadcrumbItem>
          </template>
        </BreadcrumbList>
      </Breadcrumb>
    </div>

    <div class="flex shrink-0 items-center gap-3 sm:gap-6">
      <slot name="navigation">
        <RouterLink
          :to="scansLink"
          aria-label="Scans"
          :aria-current="isScanRoute ? 'page' : undefined"
          class="flex flex-col items-center gap-1 border-b-2 pb-1 transition-colors"
          :class="
            isScanRoute
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          "
        >
          <span class="flex items-center gap-2">
            <Scan class="size-[1em]" />
            <span class="hidden 2xl:inline">Scans</span>
          </span>
        </RouterLink>

        <RouterLink
          :to="{ name: 'document-list', query: relatedQuery(route) }"
          aria-label="Documents"
          :aria-current="route.name === 'document-list' ? 'page' : undefined"
          class="flex flex-col items-center gap-1 border-b-2 pb-1 transition-colors"
          :class="
            route.name === 'document-list'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          "
        >
          <span class="flex items-center gap-2">
            <FileText class="size-[1em]" />
            <span class="hidden 2xl:inline">Documents</span>
          </span>
        </RouterLink>

        <RouterLink
          :to="{ name: 'people-search', query: relatedQuery(route) }"
          aria-label="People"
          class="flex flex-col items-center gap-1 border-b-2 pb-1 transition-colors"
          :class="
            isPeopleRoute
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          "
        >
          <span class="flex items-center gap-2">
            <User class="size-[1em]" />
            <span class="hidden 2xl:inline">People</span>
          </span>
        </RouterLink>
      </slot>
    </div>
  </nav>
</template>
