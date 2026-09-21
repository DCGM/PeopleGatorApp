import type { AssignmentType } from '@/client'

export type AssignmentFilter = 'all' | 'faces' | 'mentions'

export function normalizeAssignmentFilter(value: unknown): AssignmentFilter {
  if (value === 'faces' || value === 'mentions') return value
  if (value === 'names') return 'mentions'
  return 'all'
}

export function assignmentType(filter: AssignmentFilter): AssignmentType | undefined {
  if (filter === 'faces') return 'face'
  if (filter === 'mentions') return 'text_mention'
  return undefined
}
