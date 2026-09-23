import { toValue, type MaybeRefOrGetter } from 'vue'

export type CursorParams = {
  cursor?: string | null
}

export type CursorResponse = {
  cursor?: string | null
}

export function initialCursor<Params extends CursorParams>(
  params?: MaybeRefOrGetter<Params | undefined>,
) {
  return toValue(params)?.cursor ?? null
}

export function withCursor<Params extends object>(
  params: Params | undefined,
  cursor: string | null,
): Params & CursorParams {
  return { ...params, cursor } as Params & CursorParams
}

export function nextCursor(page: CursorResponse, previousCursor: string | null) {
  const cursor = page.cursor ?? null
  return cursor === previousCursor ? null : cursor
}
