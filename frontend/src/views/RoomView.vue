<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { useChatStore } from '../stores/chat.js'
import { apiFetch } from '../api/client.js'
import VideoPlayer from '../components/VideoPlayer.vue'

const props = defineProps({
  slug: { type: String, required: true }
})

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const chat = useChatStore()
const course = ref(null)
const currentVideo = ref(null)
const currentTime = ref(0)
const screenshot = ref('')
const input = ref('')
const loading = ref(false)
const error = ref('')
const pageLoading = ref(false)
const messageList = ref(null)

onMounted(() => {
  loadCourse()
})

watch(() => props.slug, loadCourse)

async function loadCourse() {
  pageLoading.value = true
  error.value = ''
  try {
    course.value = await apiFetch(`/api/courses/${props.slug}`)
    const videos = course.value?.videos || []
    currentVideo.value = videos[0] || null
  } catch (err) {
    error.value = err.message || '加载课程失败'
  } finally {
    pageLoading.value = false
  }
}

function onScreenshot(dataURL) {
  screenshot.value = dataURL
  scrollToBottom()
}

function onTimeUpdate(time) {
  currentTime.value = time
}

function clearScreenshot() {
  screenshot.value = ''
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
  if ((!text && !screenshot.value) || loading.value) return

  error.value = ''
  chat.addMessage('user', text || '[截图提问]')
  input.value = ''
  await scrollToBottom()

  loading.value = true
  chat.addMessage('assistant', '')

  try {
    const body = {
      messages: [{ role: 'user', content: text }],
      timestamp: currentTime.value,
      video_id: currentVideo.value?.id || null
    }

    if (screenshot.value) {
      body.screenshot = screenshot.value
    }

    const response = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
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
    handleError(err.message || '网络错误，请稍后重试')
  } finally {
    loading.value = false
    screenshot.value = ''
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
  <div class="room">
    <div v-if="pageLoading" class="page-status">加载中…</div>
    <div v-else-if="error && !currentVideo" class="page-status error">{{ error }}</div>

    <template v-else>
      <div class="video-section">
        <div class="video-wrapper">
          <VideoPlayer
            v-if="currentVideo?.video_url || currentVideo?.url"
            :src="currentVideo.video_url || currentVideo.url"
            :poster="currentVideo.poster_url || ''"
            @screenshot="onScreenshot"
            @timeupdate="onTimeUpdate"
          />
          <div v-else class="video-placeholder">
            <p>暂无视频</p>
            <p class="sub">请老师先在“上传”页面添加课程视频。</p>
          </div>
        </div>

        <div class="course-info">
          <h2 class="course-title">{{ course?.title || '学习房间' }}</h2>
          <p class="course-desc">{{ course?.description || '' }}</p>
        </div>
      </div>

      <div class="chat-section">
        <div ref="messageList" class="message-list">
          <div
            v-for="(message, index) in chat.messages"
            :key="index"
            class="message"
            :class="message.role"
          >
            <div class="bubble">
              <p v-if="message.content" class="text">{{ message.content }}</p>
              <p v-else class="text placeholder">AI 思考中…</p>
            </div>
          </div>

          <div v-if="screenshot" class="screenshot-preview">
            <img :src="screenshot" alt="截图预览" />
            <button class="clear-screenshot" type="button" @click="clearScreenshot">×</button>
          </div>

          <div v-if="error" class="error-banner">{{ error }}</div>
        </div>

        <div class="input-area">
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
            :disabled="(!input.trim() && !screenshot) || loading"
            @click="send"
          >
            {{ loading ? '…' : '发送' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.room {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 0.75rem;
  padding: 0.75rem;
}

@media (min-width: 768px) {
  .room {
    flex-direction: row;
  }

  .video-section {
    width: 60%;
  }

  .chat-section {
    width: 40%;
  }
}

.video-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-height: 0;
}

.video-wrapper {
  flex: 1;
  min-height: 12rem;
  background: #000000;
  border-radius: 0.75rem;
  overflow: hidden;
}

.video-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #9ca3af;
  text-align: center;
  padding: 1rem;
}

.video-placeholder .sub {
  font-size: 0.875rem;
}

.course-info {
  flex-shrink: 0;
  padding: 0.75rem 1rem;
  background: #ffffff;
  border-radius: 0.75rem;
  border: 1px solid #e5e7eb;
}

.course-title {
  margin: 0 0 0.25rem;
  font-size: 1.0625rem;
  font-weight: 600;
}

.course-desc {
  margin: 0;
  font-size: 0.875rem;
  color: #4b5563;
  line-height: 1.5;
}

.chat-section {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: #f5f6f8;
  border-radius: 0.75rem;
  overflow: hidden;
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
  color: #9ca3af;
}

.screenshot-preview {
  position: relative;
  display: inline-block;
  max-width: 80%;
  margin-bottom: 0.75rem;
}

.screenshot-preview img {
  display: block;
  max-width: 100%;
  max-height: 10rem;
  border-radius: 0.75rem;
  border: 1px solid #e5e7eb;
}

.clear-screenshot {
  position: absolute;
  top: -0.5rem;
  right: -0.5rem;
  width: 1.5rem;
  height: 1.5rem;
  border: none;
  border-radius: 50%;
  background: #1a1a1a;
  color: #ffffff;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
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

.page-status {
  padding: 2rem;
  text-align: center;
  color: #6b7280;
}

.page-status.error {
  color: #b91c1c;
  background: #fee2e2;
  border-radius: 0.5rem;
}
</style>
