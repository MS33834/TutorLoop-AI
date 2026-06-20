import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useChatStore = defineStore('chat', () => {
  const messages = ref([])

  function addMessage(role, content) {
    messages.value.push({ role, content })
  }

  function appendAssistantToken(token) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content += token
    } else {
      addMessage('assistant', token)
    }
  }

  return {
    messages,
    addMessage,
    appendAssistantToken
  }
})
