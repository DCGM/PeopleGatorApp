import type { QueryClient } from '@tanstack/vue-query'
import { watch } from 'vue'
import type { RouteLocationRaw, Router } from 'vue-router'
import { SignInRequiredError, currentUser, getAccessToken, signInRequired } from '@/query/client'

function loginLocation(redirect: string): RouteLocationRaw {
  return { name: 'login', query: redirect === '/' ? {} : { redirect }, replace: true }
}

/** Where to continue after signing in; only paths inside the app. */
export function redirectTarget(redirect: unknown): string {
  return typeof redirect === 'string' && /^\/(?!\/)/.test(redirect) ? redirect : '/'
}

/** Send visitors without a session to the login page, and drop cached data when the user changes. */
export function installAuth(router: Router, queryClient: QueryClient) {
  router.beforeEach(async (to) => {
    if (to.name === 'login') return
    try {
      await getAccessToken()
    } catch (error) {
      if (error instanceof SignInRequiredError) return loginLocation(to.fullPath)
      // An unreachable API is reported by the page's own requests.
    }
  })
  watch(signInRequired, (required) => {
    const route = router.currentRoute.value
    if (required && route.name !== 'login') void router.replace(loginLocation(route.fullPath))
  })
  watch(currentUser, () => queryClient.clear())
}
