import { ref } from 'vue'

import type { PersonResponse } from '@/client'
import { usePutPersonMutation } from '@/query/people'

export type NewPerson = { name: string; shortDescription?: string }

/**
 * Create a person in place and link evidence to it (#176), shared by the face
 * and mention cards. The client picks the person's UUID and creates it with
 * `PUT /people/{entity_id}`, then links the targets (face or mention IDs).
 *
 * If linking fails, the UUID is kept for the next attempt on overlapping
 * targets, even when some of them disappeared meanwhile. The PUT is idempotent,
 * so a retry never makes a second person. Unrelated targets get a new UUID, so
 * they never rename a person created for others. Success forgets the UUID.
 */
export function usePersonCreateFlow(newId: () => string = () => crypto.randomUUID()) {
  const put = usePutPersonMutation()
  const pending = ref(false)
  let unfinished: { id: string; targets: Set<string> } | null = null

  async function createAndLink(
    person: NewPerson,
    targets: readonly string[],
    link: (entityId: string) => Promise<unknown>,
  ): Promise<PersonResponse> {
    if (!unfinished || !targets.some((target) => unfinished!.targets.has(target)))
      unfinished = { id: newId(), targets: new Set(targets) }
    const attempt = unfinished
    pending.value = true
    try {
      const created = await put.mutateAsync({
        entityId: attempt.id,
        body: {
          entity_type: 'person',
          name: person.name,
          short_description: person.shortDescription || null,
        },
      })
      await link(created.entity_id)
      if (unfinished === attempt) unfinished = null
      return created
    } finally {
      pending.value = false
    }
  }

  return { createAndLink, pending }
}
