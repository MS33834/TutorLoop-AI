<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useChatStore } from '../stores/chat.js'
import { useUserStore } from '../stores/user.js'

const chat = useChatStore()
const user = useUserStore()
const input = ref('')
const loading = ref(false)
const error = ref('')
const messageList = ref(null)
let abortController = null

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

onMounted(() => {
  chat.setRoom('global')
})

onBeforeUnmount(() => {
  cancelStream()
})

function cancelStream() {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messageList.value) {
    messageList.value.scrollTop = messageList.value.scrollHeight
  }
}

function handleError(message) {
  error.value = message
  loading.value = false
}

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return

  loading.value = true
  error.value = ''
  chat.addMessage('user', text)
  input.value = ''
  await scrollToBottom()

  chat.addMessage('assistant', '')

  // 取消上一个仍在进行的流
  cancelStream()
  abortController = new AbortController()

  try {
    const response = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      signal: abortController.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(user.token ? { Authorization: `Bearer ${user.token}` } : {})
      },
      body: JSON.stringify({ messages: [{ role: 'user', content: text }] })
    })

    if (!response.ok) {
      throw new Error(`请求失败：${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue

        const payload = trimmed.slice(5).trim()
        if (payload === '[DONE]') continue

        try {
          const data = JSON.parse(payload)
          if (data.type === 'token' && data.content) {
            chat.appendAssistantToken(data.content)
            await scrollToBottom()
          } else if (data.type === 'error') {
            handleError(data.message || 'AI 返回错误')
          }
        } catch {
          // ignore malformed SSE lines
        }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      // 用户主动取消或组件卸载，静默处理
      chat.updateLastAssistantContent('（已取消）')
    } else {
      handleError(err.message || '网络错误，请稍后重试')
    }
  } finally {
    loading.value = false
    abortController = null
    await scrollToBottom()
  }
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="chat">
    <div ref="messageList" class="message-list">
      <div
        v-for="message in chat.messages"
        :key="message.id"
        class="message"
        :class="message.role"
      >
        <div class="bubble">
          <p v-if="message.content" class="text">{{ message.content }}</p>
          <p v-else class="text placeholder">AI 思考中…</p>
        </div>
      </div>
      <div v-if="error" class="error-banner">{{ error }}</div>
    </div>

    <div class="input-area">
      <button class="screenshot-btn" type="button" title="截图提问（Phase 1 占位）">
        📷
      </button>
      <textarea
        v-model="input"
        class="input"
        rows="1"
        placeholder="输入问题，AI 将以苏格拉底方式引导你…"
        @keydown="onKeydown"
      />
      <button
        class="send-btn"
        type="button"
        :disabled="!input.trim() || loading"
        @click="send"
      >
        {{ loading ? '…' : '发送' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f6f8;
}

.message-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem;
  -webkit-overflow-scrolling: touch;
}

.message {
  display: flex;
  margin-bottom: 0.75rem;
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 80%;
  padding: 0.625rem 0.875rem;
  border-radius: 1rem;
  font-size: 0.9375rem;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
}

.message.user .bubble {
  background: #2563eb;
  color: #ffffff;
  border-bottom-right-radius: 0.25rem;
}

.message.assistant .bubble {
  background: #ffffff;
  color: #1a1a1a;
  border: 1px solid #e5e7eb;
  border-bottom-left-radius: 0.25rem;
}

.text {
  margin: 0;
}

.placeholder {
  color: #6b7280;
}

.error-banner {
  margin-top: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: #fee2e2;
  color: #b91c1c;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  text-align: center;
}

.input-area {
  flex-shrink: 0;
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  padding: 0.75rem;
  padding-bottom: calc(0.75rem + env(safe-area-inset-bottom, 0px));
  background: #ffffff;
  border-top: 1px solid #e5e7eb;
}

.screenshot-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border: none;
  border-radius: 50%;
  background: #f3f4f6;
  font-size: 1.125rem;
  cursor: pointer;
  flex-shrink: 0;
}

.input {
  flex: 1;
  resize: none;
  max-height: 6rem;
  padding: 0.625rem 0.875rem;
  border: 1px solid #e5e7eb;
  border-radius: 1.25rem;
  font-size: 0.9375rem;
  line-height: 1.4;
  outline: none;
  background: #f9fafb;
}

.input:focus {
  border-color: #2563eb;
  background: #ffffff;
}

.send-btn {
  height: 2.5rem;
  padding: 0 1rem;
  border: none;
  border-radius: 1.25rem;
  background: #2563eb;
  color: #ffffff;
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
  flex-shrink: 0;
}

.send-btn:disabled {
  background: #93c5fd;
  cursor: not-allowed;
}
</style>
