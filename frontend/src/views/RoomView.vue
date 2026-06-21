<script setup>
import {
  ref,
  onMounted,
  onBeforeUnmount,
  nextTick,
  watch,
  computed
} from 'vue'
import { useChatStore } from '../stores/chat.js'
import { useUserStore } from '../stores/user.js'
import { apiFetch } from '../api/client.js'
import VideoPlayer from '../components/VideoPlayer.vue'
import MasteryRadar from '../components/MasteryRadar.vue'
import RecommendCard from '../components/RecommendCard.vue'

const props = defineProps({
  slug: { type: String, required: true }
})

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const chat = useChatStore()
const user = useUserStore()

const course = ref(null)
const currentVideo = ref(null)
const currentTime = ref(0)
const screenshot = ref('')
const input = ref('')
const loading = ref(false)
const error = ref('')
const pageLoading = ref(false)
const messageList = ref(null)
const videoPlayerRef = ref(null)

const masteryItems = ref([])
const recommendation = ref(null)
const masteryError = ref('')
const recError = ref('')

const watchSeconds = ref(0)
const lastTickAt = ref(null)

const feedbackSubmittedForIndex = ref(-1)
const showNodePicker = ref(false)
const selectedNodeId = ref('')
const pendingFeedbackCorrect = ref(false)
const feedbackLoading = ref(false)

const courseId = computed(() => course.value?.id || props.slug)

onMounted(() => {
  loadCourse()
})

onBeforeUnmount(() => {
  sendWatchRecord()
})

watch(() => props.slug, loadCourse)

watch(currentVideo, () => {
  watchSeconds.value = 0
  lastTickAt.value = null
})

async function loadCourse() {
  pageLoading.value = true
  error.value = ''
  masteryError.value = ''
  recError.value = ''
  try {
    course.value = await apiFetch(`/api/courses/${props.slug}`)
    const videos = course.value?.videos || []
    currentVideo.value = videos[0] || null
    await loadMastery()
    await loadRecommendation()
  } catch (err) {
    error.value = err.message || '加载课程失败'
  } finally {
    pageLoading.value = false
  }
}

async function loadMastery() {
  if (!user.userId || !courseId.value) return
  try {
    const data = await apiFetch(
      `/api/users/${user.userId}/mastery?course_id=${encodeURIComponent(courseId.value)}`
    )
    masteryItems.value = Array.isArray(data) ? data : data?.items || []
  } catch (err) {
    masteryError.value = err.message || '掌握度加载失败'
  }
}

async function loadRecommendation() {
  if (!user.userId || !courseId.value) return
  try {
    const data = await apiFetch(
      `/api/users/${user.userId}/recommend?course_id=${encodeURIComponent(courseId.value)}`
    )
    recommendation.value = data?.recommendation || data || null
  } catch (err) {
    recError.value = err.message || '推荐加载失败'
  }
}

function onScreenshot(dataURL) {
  screenshot.value = dataURL
  scrollToBottom()
}

function onTimeUpdate(time) {
  const now = Date.now()
  if (lastTickAt.value) {
    const delta = (now - lastTickAt.value) / 1000
    // 正常播放 tick 间隔通常 < 1s， seek 时跳过累加
    if (delta > 0 && delta < 2.5) {
      watchSeconds.value += delta
    }
  }
  currentTime.value = time
  lastTickAt.value = now
}

function onSeek(seconds) {
  videoPlayerRef.value?.seekTo?.(seconds)
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

async function sendWatchRecord() {
  if (!user.userId || !courseId.value || watchSeconds.value <= 0) return
  const payload = {
    user_id: user.userId,
    course_id: courseId.value,
    video_id: currentVideo.value?.id || null,
    video_timestamp: currentTime.value,
    node_id: recommendation.value?.node?.id || recommendation.value?.node_id || null,
    is_correct: null,
    question_text: '[观看记录]',
    answer_text: '',
    watch_seconds: Math.round(watchSeconds.value)
  }
  try {
    await apiFetch('/api/interactions', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
    watchSeconds.value = 0
    lastTickAt.value = null
  } catch (err) {
    // 观看记录失败不影响主流程
    // eslint-disable-next-line no-console
    console.warn('观看记录提交失败', err)
  }
}

async function sendInteraction(payload) {
  return apiFetch('/api/interactions', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

const lastAssistantIndex = computed(() => {
  for (let i = chat.messages.length - 1; i >= 0; i--) {
    if (chat.messages[i].role === 'assistant') return i
  }
  return -1
})

const lastUserIndex = computed(() => {
  for (let i = chat.messages.length - 1; i >= 0; i--) {
    if (chat.messages[i].role === 'user') return i
  }
  return -1
})

const showFeedback = computed(() => {
  const idx = lastAssistantIndex.value
  if (idx < 0) return false
  if (loading.value) return false
  if (feedbackSubmittedForIndex.value === idx) return false
  return chat.messages[idx]?.content?.length > 0
})

const recommendedNodeId = computed(() => {
  const node = recommendation.value?.node
  if (node && typeof node === 'object') return node.id || node.name || null
  return recommendation.value?.node_id || recommendation.value?.node || null
})

async function sendFeedback(isCorrect) {
  if (feedbackLoading.value) return

  let nodeId = recommendedNodeId.value
  if (!nodeId) {
    if (!selectedNodeId.value) {
      pendingFeedbackCorrect.value = isCorrect
      showNodePicker.value = true
      return
    }
    nodeId = selectedNodeId.value
  }

  feedbackLoading.value = true
  error.value = ''

  try {
    const questionText = chat.messages[lastUserIndex.value]?.content || ''
    const answerText = chat.messages[lastAssistantIndex.value]?.content || ''

    await sendInteraction({
      user_id: user.userId,
      course_id: courseId.value,
      video_id: currentVideo.value?.id || null,
      video_timestamp: currentTime.value,
      node_id: nodeId,
      is_correct: isCorrect,
      question_text: questionText,
      answer_text: answerText,
      watch_seconds: Math.round(watchSeconds.value)
    })

    feedbackSubmittedForIndex.value = lastAssistantIndex.value
    showNodePicker.value = false
    selectedNodeId.value = ''
    pendingFeedbackCorrect.value = false

    await loadMastery()
    await loadRecommendation()
  } catch (err) {
    error.value = err.message || '反馈提交失败，请重试'
  } finally {
    feedbackLoading.value = false
  }
}

function confirmNodeForFeedback() {
  if (!selectedNodeId.value) return
  sendFeedback(pendingFeedbackCorrect.value)
}

async function send() {
  const text = input.value.trim()
  if ((!text && !screenshot.value) || loading.value) return

  // 每次提问前 flush 已累积的观看时长
  await sendWatchRecord()

  error.value = ''
  chat.addMessage('user', text || '[截图提问]')
  input.value = ''
  await scrollToBottom()

  loading.value = true
  chat.addMessage('assistant', '')

  try {
    const history = chat.messages
      .filter((m) => m.content || m.role === 'user')
      .map((m) => ({ role: m.role, content: m.content }))
    const body = {
      messages: history,
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
            ref="videoPlayerRef"
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
        <div class="learner-panel">
          <MasteryRadar :items="masteryItems" />
          <RecommendCard
            :recommendation="recommendation"
            @jump="onSeek"
          />
          <router-link
            v-if="courseId"
            :to="`/report/${encodeURIComponent(courseId)}`"
            class="report-link"
          >
            查看完整学习报告
          </router-link>
          <div v-if="masteryError || recError" class="panel-error">
            {{ masteryError || recError }}
          </div>
        </div>

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

        <div v-if="showFeedback" class="feedback-bar">
          <span class="feedback-title">这个回答对你有帮助吗？</span>
          <div class="feedback-actions">
            <button
              class="feedback-btn good"
              type="button"
              :disabled="feedbackLoading"
              @click="sendFeedback(true)"
            >
              ✅ 明白了
            </button>
            <button
              class="feedback-btn bad"
              type="button"
              :disabled="feedbackLoading"
              @click="sendFeedback(false)"
            >
              ❌ 还不懂
            </button>
          </div>

          <div v-if="showNodePicker" class="node-picker">
            <p class="picker-hint">请选择要反馈的知识点：</p>
            <select v-model="selectedNodeId" class="node-select">
              <option value="" disabled>选择知识点</option>
              <option
                v-for="item in masteryItems"
                :key="item.name"
                :value="item.node_id || item.name"
              >
                {{ item.name }}
              </option>
            </select>
            <button
              class="confirm-btn"
              type="button"
              :disabled="!selectedNodeId || feedbackLoading"
              @click="confirmNodeForFeedback"
            >
              确认
            </button>
          </div>
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

.learner-panel {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.75rem;
  max-height: 55%;
  overflow-y: auto;
  border-bottom: 1px solid #e5e7eb;
  background: #f5f6f8;
}

.panel-error {
  padding: 0.5rem 0.75rem;
  background: #fee2e2;
  color: #b91c1c;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  text-align: center;
}

.report-link {
  display: block;
  text-align: center;
  padding: 0.5rem;
  background: #eff6ff;
  color: #2563eb;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  text-decoration: none;
  font-weight: 500;
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

.feedback-bar {
  flex-shrink: 0;
  padding: 0.625rem 0.75rem;
  background: #ffffff;
  border-top: 1px solid #e5e7eb;
}

.feedback-title {
  display: block;
  margin-bottom: 0.5rem;
  font-size: 0.8125rem;
  color: #6b7280;
  text-align: center;
}

.feedback-actions {
  display: flex;
  gap: 0.5rem;
}

.feedback-btn {
  flex: 1;
  padding: 0.5rem 0;
  border: 1px solid #e5e7eb;
  border-radius: 0.625rem;
  background: #f9fafb;
  font-size: 0.875rem;
  cursor: pointer;
}

.feedback-btn.good {
  color: #047857;
}

.feedback-btn.bad {
  color: #b91c1c;
}

.feedback-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.node-picker {
  margin-top: 0.625rem;
  padding-top: 0.625rem;
  border-top: 1px dashed #e5e7eb;
}

.picker-hint {
  margin: 0 0 0.375rem;
  font-size: 0.8125rem;
  color: #6b7280;
}

.node-select {
  width: 100%;
  padding: 0.5rem 0.625rem;
  margin-bottom: 0.5rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  font-size: 0.9375rem;
  background: #ffffff;
}

.confirm-btn {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: none;
  border-radius: 0.5rem;
  background: #2563eb;
  color: #ffffff;
  font-size: 0.9375rem;
  cursor: pointer;
}

.confirm-btn:disabled {
  background: #93c5fd;
  cursor: not-allowed;
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
