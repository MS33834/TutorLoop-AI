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

export function joinRoom(slug, password) {
  return apiFetch(`/api/rooms/${encodeURIComponent(slug)}/join`, {
    method: 'POST',
    body: JSON.stringify({ password: password || undefined })
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
