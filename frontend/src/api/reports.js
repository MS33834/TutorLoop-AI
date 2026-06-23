import { apiFetch } from './client.js'

export async function getClassReport(courseId) {
  return apiFetch(`/api/courses/${encodeURIComponent(courseId)}/class-report`)
}
