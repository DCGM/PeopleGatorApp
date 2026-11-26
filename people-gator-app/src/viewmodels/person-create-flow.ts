import { ref } from 'vue'

import type { PersonResponse } from '@/client'
import { usePutPersonMutation } from '@/query/people'

export type NewPerson = { name: string; shortDescription?: string }

/**
 * Create a person in place and link evidence to it (#176), shared by the face
 * and mention cards. The client picks the person's UUID and creates it with
 * `PUT /people/{entity_id}`, then links the targets. If linking fails, the next
 * attempt reuses the same UUID: the PUT is idempotent and no duplicate person
 * appears. The UUID is dropped once the flow succeeds or is cancelled.
 */
export function usePersonCreateFlow(newId: () => string = () => crypto.randomUUID()) {
  const put = usePutPersonMutation()
  const pending = ref(false)
  let pendingId: string | null = null

  async function createAndLink(
    person: NewPerson,
    link: (entityId: string) => Promise<unknown>,
  ): Promise<PersonResponse> {
    pendingId ??= newId()
    const entityId = pendingId
    pending.value = true
    try {
      const created = await put.mutateAsync({
        entityId,
        body: {
          entity_type: 'person',
          name: person.name,
          short_description: person.shortDescription || null,
        },
      })
      await link(created.entity_id)
      if (pendingId === entityId) pendingId = null
      return created
    } finally {
      pending.value = false
    }
  }

  /** Forget the pending UUID, for example when the card's target changes. */
  function cancel() {
    if (!pending.value) pendingId = null
  }

  return { createAndLink, cancel, pending }
}
