import { apiFetch } from './client.js'

export function getCourseGraph(courseId) {
  return apiFetch(`/api/courses/${encodeURIComponent(courseId)}/graph`)
}

export function createKnowledgeNode(courseId, payload) {
  return apiFetch(`/api/courses/${encodeURIComponent(courseId)}/nodes`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function updateKnowledgeNode(nodeId, payload) {
  return apiFetch(`/api/nodes/${encodeURIComponent(nodeId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export function deleteKnowledgeNode(nodeId) {
  return apiFetch(`/api/nodes/${encodeURIComponent(nodeId)}`, {
    method: 'DELETE'
  })
}

export function createKnowledgeEdge(courseId, payload) {
  return apiFetch(`/api/courses/${encodeURIComponent(courseId)}/edges`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function deleteKnowledgeEdge(edgeId) {
  return apiFetch(`/api/edges/${encodeURIComponent(edgeId)}`, {
    method: 'DELETE'
  })
}
