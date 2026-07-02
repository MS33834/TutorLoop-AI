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
import { apiFetch, API_BASE } from '../api/client.js'
import { useRouter, useRoute } from 'vue-router'
import { getRoomBySlug, joinRoom } from '../api/rooms.js'
import VideoPlayer from '../components/VideoPlayer.vue'
import MasteryRadar from '../components/MasteryRadar.vue'
import RecommendCard from '../components/RecommendCard.vue'
import { formatDate } from '../utils/format.js'

const props = defineProps({
  slug: { type: String, required: true }
})

const chat = useChatStore()
const user = useUserStore()
const router = useRouter()
const route = useRoute()

const room = ref(null)
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

const subtitles = ref([])
const subtitleError = ref('')

const watchSeconds = ref(0)
const lastTickAt = ref(null)

const feedbackSubmittedForIndex = ref(-1)
const showNodePicker = ref(false)
const selectedNodeId = ref('')
const pendingFeedbackCorrect = ref(false)
const feedbackLoading = ref(false)

const showNodeDetail = ref(false)
const currentNode = ref(null)
const nodeInteractions = ref([])
const nodeDetailLoading = ref(false)
const nodeDetailError = ref('')

const fileInputRef = ref(null)
const imageUploadLoading = ref(false)

const isOnline = ref(navigator.onLine !== false)
const pendingQueue = ref([])
const isRetrying = ref(false)

const requirePassword = ref(false)
const requiresLogin = ref(false)
const roomPassword = ref('')
const passwordError = ref('')
const roomAccessGranted = ref(false)
const roomSessionId = ref('')

let streamAbortController = null
let streamReader = null
let isUnmounted = false

const courseId = computed(() => course.value?.id || '')
const roomUuid = computed(() => room.value?.id || '')
const videos = computed(() => course.value?.videos || [])

onMounted(() => {
  chat.setRoom(props.slug)
  // session_id is now server-issued (HMAC-signed) via getRoomBySlug; we no
  // longer generate a client-side UUID. roomSessionId is populated in
  // loadCourse() from room.value.session_token.
  // Use sendBeacon on page hide so watch records survive navigation/close.
  window.addEventListener('pagehide', onPageHide)
  window.addEventListener('online', onNetworkOnline)
  window.addEventListener('offline', onNetworkOffline)
  loadCourse()
})

function onPageHide() {
  sendWatchRecord(true)
}

onBeforeUnmount(() => {
  isUnmounted = true
  cancelStream()
  window.removeEventListener('pagehide', onPageHide)
  window.removeEventListener('online', onNetworkOnline)
  window.removeEventListener('offline', onNetworkOffline)
  sendWatchRecord(true)
})

watch(() => props.slug, (newSlug, oldSlug) => {
  if (newSlug !== oldSlug) {
    cancelStream()
    resetFeedbackState()
    chat.setRoom(newSlug)
  }
  loadCourse()
})

function cancelStream() {
  if (streamAbortController) {
    streamAbortController.abort()
    streamAbortController = null
  }
  // Also cancel the underlying reader to release the stream immediately,
  // even if the abort signal hasn't propagated yet.
  if (streamReader) {
    streamReader.cancel().catch(() => {})
    streamReader = null
  }
}

function resetFeedbackState() {
  feedbackSubmittedForIndex.value = -1
  showNodePicker.value = false
  selectedNodeId.value = ''
  pendingFeedbackCorrect.value = false
}

async function loadCourse() {
  pageLoading.value = true
  error.value = ''
  masteryError.value = ''
  recError.value = ''
  passwordError.value = ''
  requiresLogin.value = false
  try {
    room.value = await getRoomBySlug(props.slug)
    // Use the server-issued, signed session token for join dedup.
    roomSessionId.value = room.value.session_token || ''
    if (!room.value.allow_anonymous && !user.isLoggedIn) {
      requiresLogin.value = true
      pageLoading.value = false
      return
    }
    if (room.value.require_password && !roomAccessGranted.value) {
      requirePassword.value = true
      pageLoading.value = false
      return
    }
    requirePassword.value = false
    if (!room.value.require_password) {
      await recordRoomEntry()
    }
    course.value = await apiFetch(`/api/courses/${room.value.course_id}`)
    const courseVideos = course.value?.videos || []
    currentVideo.value = courseVideos[0] || null
    await loadMastery()
    await loadRecommendation()
  } catch (err) {
    error.value = err.message || '加载房间失败'
  } finally {
    pageLoading.value = false
  }
}

async function submitPassword() {
  passwordError.value = ''
  try {
    await joinRoom(props.slug, roomPassword.value, roomSessionId.value)
    roomAccessGranted.value = true
    await loadCourse()
  } catch (err) {
    passwordError.value = err.message || '密码验证失败'
  }
}

async function recordRoomEntry() {
  try {
    await joinRoom(props.slug, null, roomSessionId.value)
  } catch (err) {
    // 入口记录失败不应阻塞学生学习
    // eslint-disable-next-line no-console
    console.warn('记录房间访问失败', err)
  }
}

async function loadMastery() {
  if (!user.isLoggedIn || !courseId.value) return
  try {
    const data = await apiFetch(
      `/api/users/me/mastery?course_id=${encodeURIComponent(courseId.value)}`
    )
    masteryItems.value = Array.isArray(data) ? data : data?.items || []
  } catch (err) {
    masteryError.value = err.message || '掌握度加载失败'
  }
}

async function loadRecommendation() {
  if (!user.isLoggedIn || !courseId.value) return
  try {
    const data = await apiFetch(
      `/api/users/me/recommend?course_id=${encodeURIComponent(courseId.value)}`
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

function switchVideo(video) {
  if (!video || video.id === currentVideo.value?.id) return
  // Flush watch time for the outgoing video before switching.
  sendWatchRecord()
  currentVideo.value = video
  // The watcher on currentVideo will reset watchSeconds and load subtitles.
}

function clearScreenshot() {
  screenshot.value = ''
}

function triggerImageUpload() {
  fileInputRef.value?.click()
}

function compressImage(dataURL, maxWidth = 1280, quality = 0.8) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      let { width, height } = img
      if (width > maxWidth) {
        height = Math.round((height * maxWidth) / width)
        width = maxWidth
      }
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        reject(new Error('无法获取画布上下文'))
        return
      }
      ctx.drawImage(img, 0, 0, width, height)
      resolve(canvas.toDataURL('image/jpeg', quality))
    }
    img.onerror = () => reject(new Error('图片加载失败'))
    img.src = dataURL
  })
}

async function onImageSelected(event) {
  const file = event.target.files?.[0]
  if (!file) return

  imageUploadLoading.value = true
  error.value = ''

  try {
    if (!file.type.startsWith('image/')) {
      throw new Error('请选择图片文件（JPG/PNG）')
    }
    if (file.size > 8 * 1024 * 1024) {
      throw new Error('图片过大，请选择 8MB 以内的图片')
    }

    const dataURL = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = (e) => resolve(e.target.result)
      reader.onerror = () => reject(new Error('读取图片失败'))
      reader.readAsDataURL(file)
    })

    const compressed = await compressImage(dataURL)
    screenshot.value = compressed
    scrollToBottom()
  } catch (err) {
    error.value = err.message || '图片处理失败'
  } finally {
    imageUploadLoading.value = false
    event.target.value = ''
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

function onNetworkOnline() {
  isOnline.value = true
  error.value = ''
  processPendingQueue()
}

function onNetworkOffline() {
  isOnline.value = false
  error.value = '网络已断开，问题会暂存并在恢复后自动发送'
}

async function processPendingQueue() {
  if (isRetrying.value || pendingQueue.value.length === 0 || !isOnline.value) return
  isRetrying.value = true
  while (pendingQueue.value.length > 0 && isOnline.value) {
    const item = pendingQueue.value[0]
    const { body, assistantMessageId } = item
    if (assistantMessageId) {
      chat.updateAssistantMessageById(assistantMessageId, '（网络已恢复，正在重试…）')
    } else {
      chat.updateLastAssistantContent('（网络已恢复，正在重试…）')
    }
    try {
      await _sendStreamRequest(body, assistantMessageId)
      pendingQueue.value.shift()
    } catch (err) {
      if (err.name === 'AbortError' || err.code === 'ABORTED') {
        // User cancelled the retry; keep it in queue for next online event.
        break
      }
      if (!isOnline.value || err.code === 'NETWORK_ERROR' || err.message?.includes('网络')) {
        if (assistantMessageId) {
          chat.updateAssistantMessageById(assistantMessageId, '（网络仍不可用，恢复后继续重试）')
        } else {
          chat.updateLastAssistantContent('（网络仍不可用，恢复后继续重试）')
        }
        break
      }
      // Non-network error: remove from queue to avoid infinite retry.
      pendingQueue.value.shift()
      if (assistantMessageId) {
        chat.updateAssistantMessageById(assistantMessageId, `（发送失败：${err.message}）`)
      } else {
        chat.updateLastAssistantContent(`（发送失败：${err.message}）`)
      }
    }
  }
  isRetrying.value = false
}

async function sendWatchRecord(useBeacon = false) {
  if (!courseId.value || watchSeconds.value <= 0) return
  // Anonymous watch records are only stored when tied to a room.
  if (!user.isLoggedIn && !roomUuid.value) return
  const payload = {
    course_id: courseId.value,
    room_id: roomUuid.value || null,
    video_id: currentVideo.value?.id || null,
    video_timestamp: currentTime.value,
    node_id: recommendation.value?.node?.id || recommendation.value?.node_id || null,
    is_correct: null,
    question_text: '[观看记录]',
    answer_text: '',
    watch_seconds: Math.round(watchSeconds.value)
  }

  // When unloading the page, use fetch with keepalive so the request survives
  // navigation AND can still carry the Authorization header. sendBeacon cannot
  // set custom headers, so authenticated watch records would be 401'd.
  if (useBeacon) {
    try {
      await fetch(`${API_BASE}/api/interactions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(user.token ? { Authorization: `Bearer ${user.token}` } : {})
        },
        body: JSON.stringify(payload),
        keepalive: true
      })
      watchSeconds.value = 0
      lastTickAt.value = null
    } catch {
      // Best effort — silently ignore.
    }
    return
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
    body: JSON.stringify({ ...payload, room_id: roomUuid.value || null })
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

const subtitleKeywords = computed(() => {
  const text = input.value?.trim() || chat.messages[lastUserIndex.value]?.content || ''
  if (!text) return []
  const words = []
  const english = text.match(/[a-zA-Z]{3,}/g) || []
  words.push(...english)
  const chinese = text.match(/[\u4e00-\u9fa5]{2,}/g) || []
  words.push(...chinese)
  const nodeNames = (masteryItems.value || []).map((i) => i.name).filter(Boolean)
  words.push(...nodeNames)
  return [...new Set(words)].slice(0, 10)
})

async function loadSubtitles(videoId) {
  if (!videoId) {
    subtitles.value = []
    return
  }
  subtitleError.value = ''
  try {
    const data = await apiFetch(`/api/videos/${encodeURIComponent(videoId)}/subtitles`)
    subtitles.value = Array.isArray(data?.cues) ? data.cues : []
  } catch (err) {
    subtitleError.value = err.message || '字幕加载失败'
    subtitles.value = []
  }
}

watch(currentVideo, () => {
  watchSeconds.value = 0
  lastTickAt.value = null
  loadSubtitles(currentVideo.value?.id)
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
    error.value = err.message || '反馈没能记录下来，不影响你继续学习'
  } finally {
    feedbackLoading.value = false
  }
}

function confirmNodeForFeedback() {
  if (!selectedNodeId.value) return
  sendFeedback(pendingFeedbackCorrect.value)
}

function handleNodeClick(node) {
  currentNode.value = node
  showNodeDetail.value = true
  nodeDetailError.value = ''
  nodeInteractions.value = []
  if (user.isLoggedIn && courseId.value) {
    loadNodeInteractions(node)
  }
}

async function loadNodeInteractions(node) {
  nodeDetailLoading.value = true
  try {
    const nodeId = node.node_id || node.name
    const data = await apiFetch(
      `/api/users/me/interactions?course_id=${encodeURIComponent(courseId.value)}&node_id=${encodeURIComponent(nodeId)}&limit=20`
    )
    nodeInteractions.value = Array.isArray(data) ? data : []
  } catch (err) {
    nodeDetailError.value = err.message || '交互记录加载失败'
  } finally {
    nodeDetailLoading.value = false
  }
}

function closeNodeDetail() {
  showNodeDetail.value = false
  currentNode.value = null
  nodeInteractions.value = []
  nodeDetailError.value = ''
}

async function _sendStreamRequest(body, assistantMessageId = null) {
  // Execute the SSE chat request. Tokens are appended to the assistant message
  // identified by assistantMessageId, or the last assistant message if not provided.
  // 取消上一个仍在进行的流
  cancelStream()
  streamAbortController = new AbortController()

  // 尝试发起流式请求；遇到 401 时先尝试静默刷新令牌再重试一次。
  let response = null
  let refreshed = false
  while (true) {
    response = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      signal: streamAbortController.signal,
      // credentials: 'include' 让 HttpOnly refresh cookie 能被发送/接收。
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(user.token ? { Authorization: `Bearer ${user.token}` } : {})
      },
      body: JSON.stringify(body)
    })

    if (response.status === 401) {
      // 尚未刷新过时尝试一次静默刷新（refresh token 由 HttpOnly cookie 携带）。
      if (!refreshed) {
        refreshed = true
        const newToken = await user.refreshAccessToken()
        if (newToken) {
          // 丢弃当前响应，用新令牌重试。
          try { await response.body?.cancel() } catch { /* ignore */ }
          continue
        }
      }
      // 刷新失败或已刷新过 —— 清除登录态并跳转。
      user.clearAuth()
      router.push({ path: '/login', query: { redirect: route.fullPath } })
      throw new Error('登录已过期，请重新登录')
    }
    break
  }

  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`)
  }

  const reader = response.body.getReader()
  streamReader = reader
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    if (isUnmounted) {
      reader.cancel().catch(() => {})
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data:')) continue

      const payload = trimmed.slice(5).trim()
      if (payload === '[DONE]') continue

      // 将 JSON 解析与业务错误处理分离：之前 throw 的错误事件被
      // 与 JSON.parse 共用的 catch 静默吞掉，导致后端下发的 error 事件
      // 永远无法到达上层的错误提示逻辑。
      let data
      try {
        data = JSON.parse(payload)
      } catch {
        // 忽略无法解析的 SSE 行
        continue
      }

      if (data.type === 'token' && data.content) {
        if (assistantMessageId) {
          chat.appendAssistantTokenById(assistantMessageId, data.content)
        } else {
          chat.appendAssistantToken(data.content)
        }
        await scrollToBottom()
      } else if (data.type === 'error') {
        throw new Error(data.message || '辅导回复出错，请重试')
      }
    }
  }
}

async function send(needAnswer = false) {
  const text = input.value.trim()
  if ((!text && !screenshot.value) || loading.value) return

  loading.value = true

  // 每次提问前 flush 已累积的观看时长（fire-and-forget，不阻塞提问）
  sendWatchRecord()

  error.value = ''
  chat.addMessage('user', text || '[截图提问]')
  input.value = ''
  await scrollToBottom()

  chat.addMessage('assistant', '')
  const assistantMessageId = chat.messages[chat.messages.length - 1]?.id || null

  const history = chat.messages
    .filter((m) => m.content || m.role === 'user')
    .map((m) => ({ role: m.role, content: m.content }))
  const body = {
    messages: history,
    room_slug: props.slug,
    timestamp: currentTime.value,
    video_id: currentVideo.value?.id || null,
    need_answer: needAnswer
  }

  if (screenshot.value) {
    body.screenshot = screenshot.value
  }

  if (needAnswer) {
    // 用户明确选择直接看答案，此时在聊天记录中追加系统提示占位。
    chat.updateLastAssistantContent('（已切换为直接解答模式）')
  }

  screenshot.value = ''

  const queueItem = { body, assistantMessageId }

  // 离线时暂存问题，网络恢复后自动重试，避免学生问题丢失。
  if (!isOnline.value) {
    pendingQueue.value.push(queueItem)
    if (assistantMessageId) {
      chat.updateAssistantMessageById(assistantMessageId, '（网络已断开，问题已保存，恢复后自动发送）')
    } else {
      chat.updateLastAssistantContent('（网络已断开，问题已保存，恢复后自动发送）')
    }
    loading.value = false
    await scrollToBottom()
    return
  }

  try {
    await _sendStreamRequest(body, assistantMessageId)
  } catch (err) {
    if (err.name === 'AbortError' || err.code === 'ABORTED') {
      // 用户主动取消或组件卸载，静默处理
      if (assistantMessageId) {
        chat.updateAssistantMessageById(assistantMessageId, '（已停止生成）')
      } else {
        chat.updateLastAssistantContent('（已停止生成）')
      }
    } else if (!isOnline.value || err.code === 'NETWORK_ERROR' || err.message?.includes('网络')) {
      // 网络异常：把请求体加入待重试队列，稍后自动重发。
      pendingQueue.value.push(queueItem)
      if (assistantMessageId) {
        chat.updateAssistantMessageById(assistantMessageId, '（网络异常，恢复后自动重试）')
      } else {
        chat.updateLastAssistantContent('（网络异常，恢复后自动重试）')
      }
      handleError('网络异常，已暂存问题，恢复后自动重试')
    } else {
      // 更新占位气泡，避免 UI 卡在"正在为你梳理思路…"
      if (assistantMessageId) {
        chat.updateAssistantMessageById(assistantMessageId, '（生成失败，请重试）')
      } else {
        chat.updateLastAssistantContent('（生成失败，请重试）')
      }
      handleError(err.message || '网络错误，请稍后重试')
    }
  } finally {
    loading.value = false
    streamAbortController = null
    streamReader = null
    await scrollToBottom()
  }
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

// 将秒数格式化为 m:ss，用于视频标签上的时长展示。
function formatVideoDuration(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0))
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}
</script>

<template>
  <div class="room">
    <div v-if="pageLoading" class="page-status">正在准备学习房间…</div>
    <div v-else-if="error && !currentVideo" class="page-status error">{{ error }}</div>

    <div v-else-if="requirePassword" class="password-gate">
      <h2 class="password-title">该房间需要密码</h2>
      <p class="password-hint">请输入老师分享的房间密码后进入学习。</p>
      <input
        v-model="roomPassword"
        type="password"
        class="password-input"
        placeholder="房间密码"
        @keydown.enter="submitPassword"
      />
      <button class="password-btn" type="button" @click="submitPassword">进入房间</button>
      <div v-if="passwordError" class="password-error">{{ passwordError }}</div>
    </div>

    <div v-else-if="requiresLogin" class="password-gate">
      <h2 class="password-title">该房间需要登录</h2>
      <p class="password-hint">老师设置了仅登录学生可进入，请先登录账号。</p>
      <button class="password-btn" type="button" @click="router.push({ path: '/login', query: { redirect: route.fullPath } })">去登录</button>
    </div>

    <template v-else>
      <div class="video-section">
        <div class="video-wrapper">
          <VideoPlayer
            v-if="currentVideo?.video_url || currentVideo?.url"
            ref="videoPlayerRef"
            :src="currentVideo.video_url || currentVideo.url"
            :poster="currentVideo.poster_url || ''"
            :subtitles="subtitles"
            :highlight-words="subtitleKeywords"
            :video-id="currentVideo?.id || ''"
            @screenshot="onScreenshot"
            @timeupdate="onTimeUpdate"
          />
          <div v-else class="video-placeholder">
            <p>课程视频还在准备中</p>
            <p class="sub">老师上传后即可开始学习。</p>
          </div>
          <div v-if="subtitleError" class="subtitle-error" role="alert">
            {{ subtitleError }}
          </div>
        </div>

        <div class="course-info">
          <h2 class="course-title">{{ room?.title || course?.title || '学习房间' }}</h2>
          <p v-if="room?.welcome_message" class="course-welcome">{{ room.welcome_message }}</p>
          <p class="course-desc">{{ course?.description || '' }}</p>

          <div v-if="videos.length > 1" class="video-tabs">
            <button
              v-for="video in videos"
              :key="video.id"
              class="video-tab"
              :class="{ active: video.id === currentVideo?.id }"
              type="button"
              @click="switchVideo(video)"
            >
              <img
                v-if="video.poster_url"
                :src="video.poster_url"
                :alt="video.title || '未命名视频'"
                class="video-tab-thumb"
                loading="lazy"
              />
              <span class="video-tab-title">{{ video.title || '未命名视频' }}</span>
              <span v-if="video.duration" class="video-tab-duration">{{ formatVideoDuration(video.duration) }}</span>
            </button>
          </div>

          <p class="room-slug">房间号：{{ props.slug }}</p>
        </div>
      </div>

      <div class="chat-section">
        <div class="learner-panel">
          <MasteryRadar :items="masteryItems" @node-click="handleNodeClick" />
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
            v-for="message in chat.messages"
            :key="message.id"
            class="message"
            :class="message.role"
          >
            <div class="bubble">
              <p v-if="message.content" class="text">{{ message.content }}</p>
              <p v-else class="text placeholder">正在为你梳理思路…</p>
            </div>
          </div>

          <div v-if="screenshot" class="screenshot-preview">
            <img :src="screenshot" alt="截图预览" />
            <button class="clear-screenshot" type="button" @click="clearScreenshot">×</button>
          </div>

          <div v-if="error" class="error-banner">{{ error }}</div>
        </div>

        <div v-if="!isOnline || pendingQueue.length" class="network-bar">
          <span v-if="!isOnline" class="offline-hint">网络已断开</span>
          <span v-else-if="pendingQueue.length" class="pending-hint">
            {{ pendingQueue.length }} 条消息待发送
          </span>
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
            <button
              class="feedback-btn answer"
              type="button"
              :disabled="feedbackLoading || loading"
              @click="send(true)"
            >
              📖 我要看答案
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
              提交反馈
            </button>
          </div>
        </div>

        <div class="input-area">
          <input
            ref="fileInputRef"
            type="file"
            accept="image/*"
            class="hidden-file-input"
            @change="onImageSelected"
          />
          <button
            class="attach-btn"
            type="button"
            title="上传图片/拍照"
            :disabled="imageUploadLoading || loading"
            @click="triggerImageUpload"
          >
            {{ imageUploadLoading ? '…' : '📎' }}
          </button>
          <textarea
            v-model="input"
            class="input"
            rows="1"
            placeholder="说说你卡在哪里，我们一起理清思路…"
            @keydown="onKeydown"
          />
          <button
            v-if="loading"
            class="stop-btn"
            type="button"
            @click="cancelStream"
          >
            停止
          </button>
          <button
            v-else
            class="send-btn"
            type="button"
            :disabled="(!input.trim() && !screenshot)"
            @click="send"
          >
            提问
          </button>
        </div>

        <div v-if="showNodeDetail" class="node-detail-modal" @click.self="closeNodeDetail">
          <div class="node-detail-card">
            <div class="node-detail-header">
              <h3 class="node-detail-title">{{ currentNode?.name }}</h3>
              <button class="node-detail-close" type="button" @click="closeNodeDetail">×</button>
            </div>

            <div class="node-detail-body">
              <p class="node-detail-desc">{{ currentNode?.description || '暂无描述' }}</p>

              <div class="node-detail-stats">
                <div class="stat">
                  <span class="stat-label">掌握度</span>
                  <span class="stat-value" :class="{ weak: (currentNode?.pKnownPercent || 0) < (currentNode?.thresholdPercent || 0) }">
                    {{ currentNode?.pKnownPercent ?? 0 }}%
                  </span>
                </div>
                <div class="stat">
                  <span class="stat-label">阈值</span>
                  <span class="stat-value">{{ currentNode?.thresholdPercent ?? 0 }}%</span>
                </div>
              </div>

              <div class="node-interactions">
                <h4 class="interactions-title">最近交互记录</h4>
                <div v-if="nodeDetailLoading" class="interactions-status">加载中…</div>
                <div v-else-if="nodeDetailError" class="interactions-status error">{{ nodeDetailError }}</div>
                <ul v-else-if="nodeInteractions.length" class="interactions-list">
                  <li v-for="record in nodeInteractions" :key="record.id" class="interaction-item">
                    <span class="interaction-time">{{ formatDate(record.created_at) }}</span>
                    <span class="interaction-result" :class="{ correct: record.is_correct === true, wrong: record.is_correct === false }">
                      {{ record.is_correct === true ? '正确' : record.is_correct === false ? '错误' : '观看/提问' }}
                    </span>
                  </li>
                </ul>
                <p v-else class="interactions-empty">该知识点暂无交互记录</p>
              </div>
            </div>
          </div>
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

.subtitle-error {
  margin-top: 0.5rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
  color: #b91c1c;
  background: #fee2e2;
  border-radius: 0.375rem;
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
  color: #6b7280;
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

.network-bar {
  flex-shrink: 0;
  padding: 0.375rem 0.75rem;
  background: #fff7ed;
  color: #c2410c;
  font-size: 0.8125rem;
  text-align: center;
  border-top: 1px solid #ffedd5;
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

.feedback-btn.answer {
  color: #2563eb;
  border-color: #bfdbfe;
  background: #eff6ff;
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

.hidden-file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.attach-btn {
  width: 2.5rem;
  height: 2.5rem;
  padding: 0;
  border: 1px solid #e5e7eb;
  border-radius: 50%;
  background: #f9fafb;
  color: #4b5563;
  font-size: 1rem;
  cursor: pointer;
  flex-shrink: 0;
}

.attach-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
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

.stop-btn {
  height: 2.5rem;
  padding: 0 1rem;
  border: none;
  border-radius: 1.25rem;
  background: #ef4444;
  color: #ffffff;
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
  flex-shrink: 0;
}

.stop-btn:hover {
  background: #dc2626;
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

.password-gate {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  height: 100%;
  padding: 1.5rem;
  text-align: center;
}

.password-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.password-hint {
  margin: 0;
  color: #6b7280;
  font-size: 0.875rem;
}

.password-input {
  width: 100%;
  max-width: 20rem;
  padding: 0.625rem 0.875rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  font-size: 0.9375rem;
}

.password-btn {
  width: 100%;
  max-width: 20rem;
  padding: 0.625rem 0.875rem;
  border: none;
  border-radius: 0.5rem;
  background: #2563eb;
  color: #ffffff;
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
}

.password-error {
  color: #b91c1c;
  font-size: 0.875rem;
}

.room-slug {
  margin: 0.25rem 0 0;
  font-size: 0.8125rem;
  color: #6b7280;
}

.course-welcome {
  margin: 0 0 0.25rem;
  font-size: 0.875rem;
  color: #4b5563;
  line-height: 1.5;
}

.video-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.625rem 0;
}

.video-tab {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  background: #f9fafb;
  color: #4b5563;
  font-size: 0.8125rem;
  cursor: pointer;
  white-space: nowrap;
}

.video-tab-thumb {
  width: 3rem;
  height: 1.875rem;
  object-fit: cover;
  border-radius: 0.25rem;
  flex-shrink: 0;
}

.video-tab-title {
  overflow: hidden;
  text-overflow: ellipsis;
}

.video-tab-duration {
  font-size: 0.6875rem;
  color: #6b7280;
  background: #ffffff;
  padding: 0.0625rem 0.3125rem;
  border-radius: 0.25rem;
  flex-shrink: 0;
}

.video-tab.active {
  background: #2563eb;
  color: #ffffff;
  border-color: #2563eb;
}

.video-tab.active .video-tab-duration {
  background: rgba(255, 255, 255, 0.2);
  color: #ffffff;
}

.node-detail-modal {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.5);
}

.node-detail-card {
  width: 100%;
  max-width: 24rem;
  max-height: 80vh;
  background: #ffffff;
  border-radius: 0.75rem;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.node-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #e5e7eb;
}

.node-detail-title {
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 600;
}

.node-detail-close {
  width: 1.75rem;
  height: 1.75rem;
  border: none;
  border-radius: 50%;
  background: #f3f4f6;
  color: #4b5563;
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
}

.node-detail-body {
  padding: 1rem;
  overflow-y: auto;
}

.node-detail-desc {
  margin: 0 0 0.75rem;
  font-size: 0.9375rem;
  color: #4b5563;
  line-height: 1.5;
}

.node-detail-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.node-detail-stats .stat {
  padding: 0.625rem;
  background: #f9fafb;
  border-radius: 0.5rem;
  text-align: center;
}

.stat-label {
  display: block;
  font-size: 0.75rem;
  color: #6b7280;
  margin-bottom: 0.25rem;
}

.stat-value {
  font-size: 1.125rem;
  font-weight: 600;
  color: #2563eb;
}

.stat-value.weak {
  color: #ef4444;
}

.node-interactions {
  border-top: 1px solid #e5e7eb;
  padding-top: 0.75rem;
}

.interactions-title {
  margin: 0 0 0.5rem;
  font-size: 0.9375rem;
  font-weight: 600;
}

.interactions-status {
  font-size: 0.875rem;
  color: #6b7280;
  text-align: center;
  padding: 0.5rem 0;
}

.interactions-status.error {
  color: #b91c1c;
  background: #fee2e2;
  border-radius: 0.375rem;
}

.interactions-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.interaction-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.625rem;
  background: #f9fafb;
  border-radius: 0.375rem;
  font-size: 0.875rem;
}

.interaction-time {
  color: #374151;
}

.interaction-result {
  font-weight: 500;
  color: #6b7280;
}

.interaction-result.correct {
  color: #047857;
}

.interaction-result.wrong {
  color: #b91c1c;
}

.interactions-empty {
  margin: 0;
  font-size: 0.875rem;
  color: #6b7280;
  text-align: center;
  padding: 0.5rem 0;
}
</style>
