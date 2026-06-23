import { apiFetch } from './client.js'

export async function getClassReport(courseId, { skip = 0, limit = 20 } = {}) {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) })
  return apiFetch(`/api/courses/${encodeURIComponent(courseId)}/class-report?${params}`)
}
