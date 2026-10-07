<script setup lang="ts">
import { FileText, User } from '@lucide/vue'
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
  const library =
    typeof route.params.libraryId === 'string' ? route.params.libraryId : route.query.library
  const document =
    typeof route.params.documentId === 'string' ? route.params.documentId : route.query.document
  const items = [
    {
      label: 'PeopleGator',
      to: { name: 'document-search' } as RouteLocationRaw,
    },
  ]
  if (typeof library === 'string') {
    items.push({ label: library, to: { name: 'document-search', query: { library } } })
    if (typeof document === 'string') {
      items.push({ label: document, to: { name: 'document-search', query: { library, document } } })
    }
    if (route.name === 'document-page') {
      items.push({
        label: `Page ${String(route.params.pageId)}`,
        to: { path: route.path, query: route.query },
      })
    }
  } else if (route.name === 'people-search' || route.name === 'person-detail') {
    items.push({ label: 'People', to: { name: 'people-search' } })
    if (route.name === 'person-detail') {
      items.push({
        label: String(route.params.personId),
        to: { path: route.path, query: route.query },
      })
    }
  }
  return items
})

const isDocumentRoute = computed(
  () => route.name === 'document-search' || route.name === 'document-page',
)
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
        :to="{ name: 'document-search' }"
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
          :to="{ name: 'document-search' }"
          aria-label="Documents"
          class="flex flex-col items-center gap-1 border-b-2 pb-1 transition-colors"
          :class="
            isDocumentRoute
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
          :to="{ name: 'people-search' }"
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
