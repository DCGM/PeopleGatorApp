<script setup lang="ts">
import { relatedQuery } from '@/viewmodels/shared-filters'
import { computed } from 'vue'
import { RouterLink, useRoute, type RouteLocationRaw } from 'vue-router'

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
        to: {
          name: 'document-search',
          query: relatedQuery(route, { library, archive_document: document }),
        },
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
</script>

<template>
  <nav
    class="sticky top-0 z-20 flex h-13 w-full items-center gap-2 border-b bg-background px-2 sm:gap-3 sm:px-4"
  >
    <slot name="toggle" />

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
  </nav>
</template>
