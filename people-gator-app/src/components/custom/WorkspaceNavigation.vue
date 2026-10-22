<script setup lang="ts">
import { FileText, Scan, User } from '@lucide/vue'
import { RouterLink, useRoute } from 'vue-router'
import { relatedQuery } from '@/viewmodels/shared-filters'
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'
const route = useRoute()
const { setOpenMobile } = useSidebar()
const navigation = [
  { label: 'Documents', name: 'document-list', icon: FileText, routes: ['document-list'] },
  {
    label: 'Scans',
    name: 'document-search',
    icon: Scan,
    routes: ['document-search', 'document-page'],
  },
  {
    label: 'People',
    name: 'people-search',
    icon: User,
    routes: ['people-search', 'person-detail'],
  },
]
</script>
<template>
  <SidebarGroup>
    <SidebarGroupLabel>Explore</SidebarGroupLabel>
    <SidebarMenu>
      <SidebarMenuItem v-for="item in navigation" :key="item.name">
        <SidebarMenuButton as-child :is-active="item.routes.includes(String(route.name))">
          <RouterLink
            :aria-label="item.label"
            :to="{
              name: item.name,
              query: route.name === item.name ? route.query : relatedQuery(route),
            }"
            :aria-current="item.routes.includes(String(route.name)) ? 'page' : undefined"
            @click="setOpenMobile(false)"
          >
            <component :is="item.icon" aria-hidden="true" /><span>{{ item.label }}</span>
          </RouterLink>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  </SidebarGroup>
</template>
