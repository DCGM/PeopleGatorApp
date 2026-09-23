export type AssignmentFilter = 'all' | 'faces' | 'mentions'
export type AssignmentType = 'face' | 'text_mention'

export function normalizeAssignmentFilter(value: unknown): AssignmentFilter {
  if (value === 'faces' || value === 'mentions') return value
  if (value === 'names') return 'mentions'
  return 'all'
}

export function assignmentEntityFilter(filter: AssignmentFilter) {
  return {
    hasDetections: filter === 'faces' ? true : undefined,
    hasMentions: filter === 'mentions' ? true : undefined,
  }
}

export function assignmentType(filter: AssignmentFilter): AssignmentType | undefined {
  if (filter === 'faces') return 'face'
  if (filter === 'mentions') return 'text_mention'
  return undefined
}
