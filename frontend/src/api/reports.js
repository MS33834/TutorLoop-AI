import { apiFetch } from './client.js'

export async function getClassReport(courseId, { skip = 0, limit = 20 } = {}) {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) })
  return apiFetch(`/api/courses/${encodeURIComponent(courseId)}/class-report?${params}`)
}

/**
 * 个人学习报告：掌握度、薄弱知识点、强项、汇总指标等。
 */
export function getReport(courseId) {
  return apiFetch(`/api/users/me/report?course_id=${encodeURIComponent(courseId)}`)
}

/**
 * 个人时间轴数据：日活、掌握度曲线、视频观看热力图等。
 */
export function getTimeline(courseId, { days = 30 } = {}) {
  return apiFetch(
    `/api/users/me/timeline?course_id=${encodeURIComponent(courseId)}&days=${days}`
  )
}
