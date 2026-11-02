import type { QueryClient } from '@tanstack/vue-query'

type ObjectKind = 'entity' | 'face' | 'mention' | 'source'
const idFields: Record<ObjectKind, string> = {
  entity: 'entity_id',
  face: 'detection_id',
  mention: 'mention_id',
  source: 'source_id',
}

/** Use the version already read by the UI. Never refresh and retry a stale write. */
export function readVersion(client: QueryClient, kind: ObjectKind, id: string): number {
  const idField = idFields[kind]
  function find(value: unknown): number | undefined {
    if (!value || typeof value !== 'object') return
    if (Array.isArray(value)) {
      for (const item of value) {
        const version = find(item)
        if (version !== undefined) return version
      }
      return
    }
    const record = value as Record<string, unknown>
    // Linked entity_id/source_id on evidence does not identify that related object's version.
    const ownKind =
      'detection_id' in record
        ? 'face'
        : 'mention_id' in record
          ? 'mention'
          : 'entity_id' in record && !('source_id' in record)
            ? 'entity'
            : 'source_id' in record
              ? 'source'
              : undefined
    if (ownKind === kind && record[idField] === id && typeof record.version === 'number')
      return record.version
    for (const field of ['pages', 'items']) {
      const version = find(record[field])
      if (version !== undefined) return version
    }
  }
  for (const [, data] of client.getQueriesData({})) {
    const version = find(data)
    if (version !== undefined) return version
  }
  throw new Error('Reload this item before editing it.')
}
