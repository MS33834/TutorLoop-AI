import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useUserStore } from './user.js'

const DEFAULT_ROOM = '__global__'
// 最多持久化最近的消息条数，避免 localStorage 超出配额。
const MAX_PERSISTED_MESSAGES = 100

function buildRoomKey(roomSlug, userId) {
  return `${userId || 'anonymous'}:${roomSlug || DEFAULT_ROOM}`
}

function buildStorageKey(roomSlug, userId) {
  return `chat_messages_${userId || 'anonymous'}_${roomSlug || DEFAULT_ROOM}`
}

function generateMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function safeParse(raw, fallback) {
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : fallback
  } catch {
    return fallback
  }
}

export const useChatStore = defineStore('chat', () => {
  const userStore = useUserStore()

  // messagesMap: Map<roomKey, Array<{id, role, content}>>
  const messagesMap = ref(new Map())
  const currentRoomSlug = ref('')

  const roomKey = computed(() =>
    buildRoomKey(currentRoomSlug.value, userStore.userId)
  )

  const messages = computed(() => {
    return messagesMap.value.get(roomKey.value) || []
  })

  function ensureRoom(key) {
    if (!messagesMap.value.has(key)) {
      messagesMap.value.set(key, [])
    }
  }

  function persistRoom(slug, userId) {
    if (!slug || slug === DEFAULT_ROOM) return
    const key = buildRoomKey(slug, userId)
    const list = messagesMap.value.get(key)
    if (!list) return
    const trimmed = list.length > MAX_PERSISTED_MESSAGES
      ? list.slice(-MAX_PERSISTED_MESSAGES)
      : list
    try {
      localStorage.setItem(buildStorageKey(slug, userId), JSON.stringify(trimmed))
    } catch {
      // 忽略写入失败（隐私模式 / 配额超限）
    }
  }

  function restoreRoom(slug, userId) {
    if (!slug || slug === DEFAULT_ROOM) return
    const key = buildRoomKey(slug, userId)
    if (messagesMap.value.get(key)?.length) return
    try {
      const raw = localStorage.getItem(buildStorageKey(slug, userId))
      if (!raw) return
      const parsed = safeParse(raw, [])
      if (parsed.length) {
        messagesMap.value.set(key, parsed)
      }
    } catch {
      // ignore
    }
  }

  // 切换用户 / 房间时，旧 roomKey 的内存数据自然隔离（roomKey 已包含
  // userId），保留在 messagesMap 中但不再被访问，满足"保留但不再使用"。
  // 持久化按 (userId, roomSlug) 分别存储，互不干扰。

  function setRoom(slug) {
    currentRoomSlug.value = slug || DEFAULT_ROOM
    ensureRoom(roomKey.value)
    restoreRoom(currentRoomSlug.value, userStore.userId)
  }

  function resetRoom(slug) {
    const key = buildRoomKey(slug || currentRoomSlug.value, userStore.userId)
    messagesMap.value.set(key, [])
    persistRoom(slug || currentRoomSlug.value, userStore.userId)
  }

  function clearAll() {
    messagesMap.value.clear()
    currentRoomSlug.value = ''
  }

  function addMessage(role, content) {
    const key = roomKey.value
    ensureRoom(key)
    const next = messagesMap.value.get(key).concat({ id: generateMessageId(), role, content })
    messagesMap.value.set(key, next)
    persistRoom(currentRoomSlug.value, userStore.userId)
  }

  function appendAssistantToken(token) {
    const key = roomKey.value
    const list = messagesMap.value.get(key) || []
    const last = list[list.length - 1]
    let next
    if (last && last.role === 'assistant') {
      next = list.slice(0, -1).concat({ ...last, content: last.content + token })
    } else {
      next = list.concat({ id: generateMessageId(), role: 'assistant', content: token })
    }
    messagesMap.value.set(key, next)
    persistRoom(currentRoomSlug.value, userStore.userId)
  }

  function updateLastAssistantContent(content) {
    const key = roomKey.value
    const list = messagesMap.value.get(key)
    if (!list || !list.length) return
    const last = list[list.length - 1]
    if (last && last.role === 'assistant') {
      const next = list.slice(0, -1).concat({ ...last, content })
      messagesMap.value.set(key, next)
      persistRoom(currentRoomSlug.value, userStore.userId)
    }
  }

  function updateAssistantMessageById(messageId, content) {
    const key = roomKey.value
    const list = messagesMap.value.get(key)
    if (!list || !list.length) return
    const index = list.findIndex((m) => m.id === messageId && m.role === 'assistant')
    if (index === -1) return
    const next = list.slice()
    next[index] = { ...next[index], content }
    messagesMap.value.set(key, next)
    persistRoom(currentRoomSlug.value, userStore.userId)
  }

  function appendAssistantTokenById(messageId, token) {
    const key = roomKey.value
    const list = messagesMap.value.get(key)
    if (!list || !list.length) return
    const index = list.findIndex((m) => m.id === messageId && m.role === 'assistant')
    if (index === -1) return
    const next = list.slice()
    next[index] = { ...next[index], content: next[index].content + token }
    messagesMap.value.set(key, next)
    persistRoom(currentRoomSlug.value, userStore.userId)
  }

  function clearCurrentRoom() {
    messagesMap.value.delete(roomKey.value)
    try {
      localStorage.removeItem(buildStorageKey(currentRoomSlug.value, userStore.userId))
    } catch {
      // ignore
    }
  }

  return {
    messages,
    messagesMap,
    currentRoomSlug,
    roomKey,
    setRoom,
    resetRoom,
    clearRoom: clearCurrentRoom,
    clearAll,
    addMessage,
    appendAssistantToken,
    appendAssistantTokenById,
    updateLastAssistantContent,
    updateAssistantMessageById
  }
})
