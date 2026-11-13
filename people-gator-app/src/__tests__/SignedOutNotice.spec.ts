import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SignedOutNotice from '@/components/custom/SignedOutNotice.vue'
import { signInProblem } from '@/query/client'

const signIn = vi.hoisted(() => vi.fn<() => Promise<void>>())
vi.mock('@/query/client', async () => {
  const { ref } = await import('vue')
  return { signIn, signInProblem: ref<'signed-out' | 'forbidden'>() }
})

afterEach(() => {
  signIn.mockReset()
  signInProblem.value = undefined
})

function render() {
  const queryClient = new QueryClient()
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
  const wrapper = mount(SignedOutNotice, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
  return { wrapper, invalidate }
}

describe('SignedOutNotice', () => {
  it('signs in again and reloads data', async () => {
    signInProblem.value = 'signed-out'
    signIn.mockImplementation(async () => {
      signInProblem.value = undefined
    })
    const { wrapper, invalidate } = render()
    expect(wrapper.text()).toContain('Signed out')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(signIn).toHaveBeenCalledOnce()
    expect(invalidate).toHaveBeenCalledOnce()
  })

  it('names an account without access and keeps the notice after another refusal', async () => {
    signInProblem.value = 'forbidden'
    signIn.mockRejectedValue(new Error('refused'))
    const { wrapper, invalidate } = render()
    expect(wrapper.text()).toContain('Access denied')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(invalidate).not.toHaveBeenCalled()
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
  })
})
