import { apiFetch } from './client.js'

export function listCourseRooms(courseId) {
  return apiFetch(`/api/courses/${encodeURIComponent(courseId)}/rooms`)
}

export function createRoom(courseId, payload) {
  return apiFetch(`/api/courses/${encodeURIComponent(courseId)}/rooms`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function getRoomBySlug(slug) {
  return apiFetch(`/api/rooms/${encodeURIComponent(slug)}`)
}

export function joinRoom(slug, password, sessionId) {
  return apiFetch(`/api/rooms/${encodeURIComponent(slug)}/join`, {
    method: 'POST',
    body: JSON.stringify({
      password: password || undefined,
      session_id: sessionId || undefined
    })
  })
}

export function updateRoom(roomId, payload) {
  return apiFetch(`/api/rooms/${encodeURIComponent(roomId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export function deleteRoom(roomId) {
  return apiFetch(`/api/rooms/${encodeURIComponent(roomId)}`, {
    method: 'DELETE'
  })
}

/**
 * 离开房间：通知后端该会话已结束，便于准确统计停留时长。
 */
export function leaveRoom(slug, sessionId) {
  return apiFetch(`/api/rooms/${encodeURIComponent(slug)}/leave`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId || undefined })
  })
}

/**
 * 获取房间二维码（后端可返回图片数据或链接）。
 */
export function getQRCode(slug) {
  return apiFetch(`/api/rooms/${encodeURIComponent(slug)}/qrcode`)
}
