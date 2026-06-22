import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useUserStore } from './user.js'

const DEFAULT_ROOM = '__global__'

function buildRoomKey(roomSlug, userId) {
  return `${userId || 'anonymous'}:${roomSlug || DEFAULT_ROOM}`
}

function generateMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export const useChatStore = defineStore('chat', () => {
  const userStore = useUserStore()

  // messagesMap: Map<roomKey, Array<{id, role, content}>]
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

  function setRoom(slug) {
    currentRoomSlug.value = slug || DEFAULT_ROOM
    ensureRoom(roomKey.value)
  }

  function resetRoom(slug) {
    const key = buildRoomKey(slug || currentRoomSlug.value, userStore.userId)
    messagesMap.value.set(key, [])
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
  }

  function updateLastAssistantContent(content) {
    const key = roomKey.value
    const list = messagesMap.value.get(key)
    if (!list || !list.length) return
    const last = list[list.length - 1]
    if (last && last.role === 'assistant') {
      const next = list.slice(0, -1).concat({ ...last, content })
      messagesMap.value.set(key, next)
    }
  }

  function clearCurrentRoom() {
    messagesMap.value.delete(roomKey.value)
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
    updateLastAssistantContent
  }
})
