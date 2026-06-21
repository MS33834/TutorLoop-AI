import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'tutorloop_user_id'

function generateUserId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `user-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export const useUserStore = defineStore('user', () => {
  const userId = ref('')

  function initUserId() {
    let id = ''
    try {
      id = localStorage.getItem(STORAGE_KEY) || ''
    } catch {
      // localStorage 不可用时直接生成
    }

    if (!id) {
      id = generateUserId()
      try {
        localStorage.setItem(STORAGE_KEY, id)
      } catch {
        // ignore
      }
    }

    userId.value = id
  }

  initUserId()

  return {
    userId,
    initUserId
  }
})
