import { QueryClient } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { AxiosError } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { appConfig } from '@/app-config'
import TopBar from '@/components/custom/TopBar.vue'
import LoginView from '@/views/LoginView.vue'
import * as session from '@/query/client'
import { installAuth, redirectTarget } from '@/router/auth'

vi.mock('@/query/media', async () => {
  const { ref } = await import('vue')
  return {
    useDocumentLookupQuery: () => ({ data: ref(undefined) }),
    usePageLookupQuery: () => ({ data: ref(undefined) }),
  }
})
vi.mock('@/query/entities', async () => {
  const { ref } = await import('vue')
  return { useEntityQuery: () => ({ data: ref(undefined) }) }
})
vi.mock('@/query/client', async (original) => {
  const actual = await original<typeof import('@/query/client')>()
  return {
    ...actual,
    login: vi.fn<typeof actual.login>(),
    loginAsPublic: vi.fn<typeof actual.loginAsPublic>(),
    getAccessToken: vi.fn<typeof actual.getAccessToken>(),
  }
})

const rejected = (status: number) =>
  new AxiosError('failed', String(status), undefined, undefined, { status } as never)

function testRouter() {
  const page = { template: '<div />' }
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', redirect: '/documents' },
      { path: '/documents', name: 'document-list', component: page },
      { path: '/people', name: 'people-search', component: page },
      { path: '/login', name: 'login', component: LoginView },
    ],
  })
}

beforeEach(() => {
  session.currentUser.value = undefined
  session.signInRequired.value = false
})
afterEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  appConfig.publicLogin = null
})

describe('login page', () => {
  async function open(path = '/login') {
    const router = testRouter()
    await router.push(path)
    const wrapper = mount(LoginView, { global: { plugins: [router] }, attachTo: document.body })
    return { router, wrapper }
  }

  it('signs in with the entered account and continues to the requested page', async () => {
    vi.mocked(session.login).mockResolvedValue('token')
    const { router, wrapper } = await open('/login?redirect=/people?q=Ada')
    await wrapper.get('input[name="username"]').setValue('alice')
    await wrapper.get('input[name="password"]').setValue('secret')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(session.login).toHaveBeenCalledWith('alice', 'secret')
    expect(router.currentRoute.value.fullPath).toBe('/people?q=Ada')
    wrapper.unmount()
  })

  it.each([
    [401, 'Wrong username or password.'],
    [403, 'This account has no access.'],
    [503, 'Could not sign in. Try again.'],
  ])('explains a %s rejection and stays on the page', async (status, message) => {
    vi.mocked(session.login).mockRejectedValue(rejected(status))
    const { router, wrapper } = await open()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe(message)
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('offers the public account only when the deployment has one', async () => {
    vi.mocked(session.loginAsPublic).mockResolvedValue('token')
    const closed = await open()
    expect(closed.wrapper.text()).not.toContain('Continue as guest')
    closed.wrapper.unmount()

    appConfig.publicLogin = { username: 'guest', password: 'open' }
    const { router, wrapper } = await open()
    const button = wrapper.findAll('button').find((item) => item.text() === 'Continue as guest')!
    await button.trigger('click')
    await flushPromises()
    expect(session.loginAsPublic).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toBe('/documents')
    wrapper.unmount()
  })

  it('continues only to pages of this app', () => {
    expect(redirectTarget('/people?q=Ada')).toBe('/people?q=Ada')
    for (const outside of ['//evil.example', 'https://evil.example', undefined, ['/a']]) {
      expect(redirectTarget(outside)).toBe('/')
    }
  })
})

describe('session guard', () => {
  it('sends a visitor without a session to the login page and back after signing in', async () => {
    const router = testRouter()
    const queries = new QueryClient()
    const clear = vi.spyOn(queries, 'clear')
    installAuth(router, queries)
    vi.mocked(session.getAccessToken).mockRejectedValue(new session.SignInRequiredError())
    await router.push('/people?q=Ada')
    expect(router.currentRoute.value.fullPath).toBe('/login?redirect=/people?q=Ada')

    vi.mocked(session.getAccessToken).mockResolvedValue('token')
    session.currentUser.value = 'alice'
    await flushPromises()
    expect(clear).toHaveBeenCalledOnce()
    await router.push(redirectTarget(router.currentRoute.value.query.redirect))
    expect(router.currentRoute.value.fullPath).toBe('/people?q=Ada')

    // A session that ends while a page is open also leads to the login page.
    session.signInRequired.value = true
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/login?redirect=/people?q=Ada')
  })

  it('opens the page when the API is unreachable, leaving the error to the page', async () => {
    const router = testRouter()
    installAuth(router, new QueryClient())
    vi.mocked(session.getAccessToken).mockRejectedValue(rejected(503))
    await router.push('/people')
    expect(router.currentRoute.value.name).toBe('people-search')
  })
})

describe('account control', () => {
  async function bar() {
    const router = testRouter()
    await router.push('/documents')
    return mount(TopBar, { global: { plugins: [router] }, attachTo: document.body })
  }

  it('offers sign-in from the public account', async () => {
    appConfig.publicLogin = { username: 'guest', password: 'open' }
    session.currentUser.value = 'guest'
    const wrapper = await bar()
    await wrapper.get('button[aria-label="Sign in"]').trigger('click')
    expect(session.signInRequired.value).toBe(true)
    expect(session.currentUser.value).toBeUndefined()
    wrapper.unmount()
  })

  it('names the signed-in person', async () => {
    session.currentUser.value = 'alice'
    const wrapper = await bar()
    expect(wrapper.find('button[aria-label="Sign in"]').exists()).toBe(false)
    expect(wrapper.get('button[aria-label="Account alice"]').text()).toBe('alice')
    wrapper.unmount()
  })
})
