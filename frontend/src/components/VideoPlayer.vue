<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { apiFetch } from '../api/client'

const props = defineProps({
  src: { type: String, default: '' },
  poster: { type: String, default: '' },
  subtitles: { type: Array, default: () => [] },
  highlightWords: { type: Array, default: () => [] },
  videoId: { type: String, default: '' }
})

const emit = defineEmits(['screenshot', 'timeupdate', 'screenshot-error'])

const video = ref(null)
const videoContainerRef = ref(null)
const playing = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const buffered = ref(0)
const showControls = ref(true)
const playbackRate = ref(1)
const showSubtitles = ref(true)
const screenshotError = ref('')
const isDragging = ref(false)
const volume = ref(1)
const isFullscreen = ref(false)
let controlsTimer = null
let screenshotErrorTimer = null

const PLAYBACK_RATES = [0.5, 1, 1.25, 1.5, 2]

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]))
}

const formattedCurrentTime = computed(() => formatTime(currentTime.value))
const formattedDuration = computed(() => formatTime(duration.value))
const progressPercent = computed(() => {
  if (!duration.value) return 0
  return (currentTime.value / duration.value) * 100
})
const bufferedPercent = computed(() => {
  if (!duration.value) return 0
  return (buffered.value / duration.value) * 100
})

const currentSubtitle = computed(() => {
  if (!props.subtitles?.length) return null
  const t = currentTime.value
  return props.subtitles.find((cue) => cue.start <= t && cue.end >= t) || null
})

const cleanedHighlightWords = computed(() => {
  return (props.highlightWords || [])
    .map((w) => (typeof w === 'string' ? w.trim() : ''))
    .filter(Boolean)
})

function highlightedSubtitle(text) {
  // Escape HTML first so subtitle text can never inject markup. Highlighting
  // then operates on the escaped string; highlight words are escaped too so
  // they still match entities like &amp; in the escaped text.
  const safe = escapeHtml(text)
  if (!safe || !cleanedHighlightWords.value.length) return safe
  let html = safe
  for (const word of cleanedHighlightWords.value) {
    const escapedWord = escapeHtml(word)
    if (!escapedWord) continue
    const pattern = new RegExp(`(${escapedWord.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
    html = html.replace(pattern, '<mark>$1</mark>')
  }
  return html
}

function formatTime(seconds) {
  if (!isFinite(seconds)) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function togglePlay() {
  if (!video.value) return
  if (video.value.paused) {
    video.value.play()
  } else {
    video.value.pause()
  }
}

function cyclePlaybackRate() {
  if (!video.value) return
  const current = playbackRate.value
  const idx = PLAYBACK_RATES.indexOf(current)
  const next = PLAYBACK_RATES[(idx + 1) % PLAYBACK_RATES.length]
  video.value.playbackRate = next
  playbackRate.value = next
}

function toggleSubtitles() {
  showSubtitles.value = !showSubtitles.value
}

function onPlay() {
  playing.value = true
}

function onPause() {
  playing.value = false
}

function onTimeUpdate() {
  if (!video.value) return
  currentTime.value = video.value.currentTime
  emit('timeupdate', currentTime.value)
  // 节流上报观看进度到后端（每 15 秒）
  _syncProgressThrottled()
}

let _lastSyncTs = 0
function _syncProgressThrottled() {
  if (!props.videoId || !video.value) return
  const now = Date.now()
  if (now - _lastSyncTs < 15000) return
  _lastSyncTs = now
  apiFetch(`/api/users/me/videos/${props.videoId}/progress`, {
    method: 'PUT',
    body: JSON.stringify({
      position_seconds: video.value.currentTime,
      watched_seconds: video.value.currentTime,
      video_id: props.videoId,
    }),
  }).catch(() => { /* 进度同步失败不影响播放 */ })
}

async function onLoadedMetadata() {
  if (!video.value) return
  duration.value = video.value.duration
  // 恢复上次播放位置
  if (props.videoId) {
    try {
      const res = await apiFetch(`/api/users/me/videos/${props.videoId}/progress`)
      if (res?.position_seconds && res.position_seconds > 5) {
        video.value.currentTime = res.position_seconds
      }
    } catch { /* 忽略，从头播放 */ }
  }
}

function onProgress() {
  if (!video.value || !video.value.buffered.length) return
  buffered.value = video.value.buffered.end(video.value.buffered.length - 1)
}

function seek(e) {
  if (!video.value || !duration.value) return
  const rect = e.currentTarget.getBoundingClientRect()
  const ratio = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1)
  video.value.currentTime = ratio * duration.value
}

// 进度条拖动 seek：pointerdown 起始定位，pointermove 持续跟随，pointerup 结束。
// 使用 window 级监听确保拖出进度条后仍能继续拖动。
function onProgressPointerDown(e) {
  isDragging.value = true
  seek(e)
  window.addEventListener('pointermove', onProgressPointerMove)
  window.addEventListener('pointerup', onProgressPointerUp)
}

function onProgressPointerMove(e) {
  if (!isDragging.value || !video.value || !duration.value) return
  // 使用进度条元素的矩形计算比例，保证拖动到边缘也能精确定位。
  const progressBar = e.currentTarget
  // move 事件注册在 window 上，currentTarget 为 window；改用首个进度条元素。
  const target = document.querySelector('.video-player .progress-bar')
  if (!target) return
  const rect = target.getBoundingClientRect()
  const ratio = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1)
  video.value.currentTime = ratio * duration.value
}

function onProgressPointerUp() {
  isDragging.value = false
  window.removeEventListener('pointermove', onProgressPointerMove)
  window.removeEventListener('pointerup', onProgressPointerUp)
}

function changeVolume(e) {
  if (!video.value) return
  const v = Number(e.target.value)
  volume.value = v
  video.value.volume = v
}

function toggleFullscreen() {
  const el = videoContainerRef.value
  if (!el) return
  if (document.fullscreenElement) {
    document.exitFullscreen?.()
  } else {
    el.requestFullscreen?.()
  }
}

function onFullscreenChange() {
  isFullscreen.value = Boolean(document.fullscreenElement)
}

function seekTo(seconds) {
  if (!video.value) return
  video.value.currentTime = Math.max(0, seconds)
}

function showScreenshotError(msg) {
  clearTimeout(screenshotErrorTimer)
  screenshotError.value = msg
  emit('screenshot-error', msg)
  // Clear via JS timer so consecutive failures re-trigger the toast. Relying
  // on a CSS animation alone would leave opacity:0 after the first error and
  // never replay for subsequent ones.
  screenshotErrorTimer = setTimeout(() => {
    screenshotError.value = ''
  }, 3000)
}

function takeScreenshot() {
  if (!video.value || !props.src) {
    showScreenshotError('视频尚未加载，无法截图')
    return
  }
  screenshotError.value = ''
  const canvas = document.createElement('canvas')
  canvas.width = video.value.videoWidth || 640
  canvas.height = video.value.videoHeight || 360
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    showScreenshotError('无法获取画布上下文，截图失败')
    return
  }
  try {
    ctx.drawImage(video.value, 0, 0, canvas.width, canvas.height)
  } catch (err) {
    showScreenshotError('视频帧尚未就绪，请稍后重试')
    return
  }
  const dataURL = canvas.toDataURL('image/jpeg', 0.9)
  emit('screenshot', dataURL)
}

function onContainerClick() {
  resetControlsTimer()
}

function onMouseMove() {
  showControls.value = true
  resetControlsTimer()
}

// 触摸开始时只显示控制栏一次，不重置计时器，避免触摸滑动时反复延后隐藏。
function onTouchStart() {
  showControls.value = true
  if (!controlsTimer) {
    resetControlsTimer()
  }
}

function resetControlsTimer() {
  clearTimeout(controlsTimer)
  controlsTimer = setTimeout(() => {
    if (playing.value) showControls.value = false
  }, 3000)
}

watch(() => props.src, () => {
  playing.value = false
  currentTime.value = 0
  duration.value = 0
  buffered.value = 0
  playbackRate.value = 1
})

onBeforeUnmount(() => {
  clearTimeout(controlsTimer)
  clearTimeout(screenshotErrorTimer)
  // 卸载时保存最后一次进度
  if (props.videoId && video.value) {
    apiFetch(`/api/users/me/videos/${props.videoId}/progress`, {
      method: 'PUT',
      body: JSON.stringify({
        position_seconds: video.value.currentTime,
        watched_seconds: video.value.currentTime,
        video_id: props.videoId,
      }),
    }).catch(() => {})
  }
  // 拖动未结束就卸载时，移除 window 级监听避免泄漏。
  window.removeEventListener('pointermove', onProgressPointerMove)
  window.removeEventListener('pointerup', onProgressPointerUp)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})

defineExpose({
  seekTo
})
</script>

<template>
  <div
    ref="videoContainerRef"
    class="video-player"
    @click="onContainerClick"
    @mousemove="onMouseMove"
    @touchstart="onTouchStart"
    @fullscreenchange="onFullscreenChange"
  >
    <video
      ref="video"
      class="video"
      :src="src"
      :poster="poster"
      playsinline
      preload="metadata"
      @play="onPlay"
      @pause="onPause"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMetadata"
      @progress="onProgress"
      @click.stop="togglePlay"
    />

    <div
      v-if="currentSubtitle && showSubtitles"
      class="subtitle-track"
      v-html="highlightedSubtitle(currentSubtitle.text)"
    />

    <div class="controls" :class="{ visible: showControls }">
      <div class="progress-bar" @pointerdown.stop="onProgressPointerDown">
        <div class="buffered" :style="{ width: `${bufferedPercent}%` }" />
        <div class="progress" :style="{ width: `${progressPercent}%` }" />
        <div class="thumb" :class="{ dragging: isDragging }" :style="{ left: `${progressPercent}%` }" />
      </div>

      <div class="controls-row">
        <button class="control-btn play-btn" type="button" @click.stop="togglePlay">
          {{ playing ? '⏸' : '▶' }}
        </button>

        <span class="time">{{ formattedCurrentTime }} / {{ formattedDuration }}</span>

        <input
          class="volume-slider"
          type="range"
          min="0"
          max="1"
          step="0.05"
          :value="volume"
          title="音量"
          aria-label="音量"
          @input="changeVolume"
          @click.stop
        />

        <button
          class="control-btn rate-btn"
          type="button"
          title="切换播放倍速"
          @click.stop="cyclePlaybackRate"
        >
          {{ playbackRate }}x
        </button>

        <button
          v-if="subtitles?.length"
          class="control-btn subtitle-btn"
          type="button"
          title="切换字幕"
          :class="{ active: showSubtitles }"
          @click.stop="toggleSubtitles"
        >
          CC
        </button>

        <button class="control-btn screenshot-btn" type="button" title="截图提问" @click.stop="takeScreenshot">
          📷
        </button>

        <button
          class="control-btn fullscreen-btn"
          type="button"
          :title="isFullscreen ? '退出全屏' : '全屏'"
          :aria-label="isFullscreen ? '退出全屏' : '全屏'"
          @click.stop="toggleFullscreen"
        >
          {{ isFullscreen ? '🗗' : '⛶' }}
        </button>
      </div>
    </div>

    <div v-if="screenshotError" class="screenshot-toast" role="alert">
      {{ screenshotError }}
    </div>
  </div>
</template>

<style scoped>
.video-player {
  position: relative;
  width: 100%;
  height: 100%;
  background: #000000;
  overflow: hidden;
  border-radius: 0.75rem;
  user-select: none;
}

.video {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.controls {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 0.75rem;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.7), transparent);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.controls.visible {
  opacity: 1;
}

.progress-bar {
  position: relative;
  height: 1.25rem;
  margin-bottom: 0.5rem;
  cursor: pointer;
}

.progress-bar::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 0.375rem;
  margin-top: -0.1875rem;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 0.25rem;
}

.buffered {
  position: absolute;
  top: 50%;
  left: 0;
  height: 0.375rem;
  margin-top: -0.1875rem;
  background: rgba(255, 255, 255, 0.4);
  border-radius: 0.25rem;
}

.progress {
  position: absolute;
  top: 50%;
  left: 0;
  height: 0.375rem;
  margin-top: -0.1875rem;
  background: #2563eb;
  border-radius: 0.25rem;
}

.thumb {
  position: absolute;
  top: 50%;
  width: 1rem;
  height: 1rem;
  margin-top: -0.5rem;
  margin-left: -0.5rem;
  background: #ffffff;
  border-radius: 50%;
  box-shadow: 0 0.125rem 0.25rem rgba(0, 0, 0, 0.3);
  transform: scale(1);
  transition: transform 0.15s ease;
}

.thumb.dragging {
  transform: scale(1.3);
}

.volume-slider {
  width: 4.5rem;
  height: 1rem;
  cursor: pointer;
  accent-color: #2563eb;
}

.controls-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.control-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  height: 2.75rem;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  color: #ffffff;
  font-size: 1.25rem;
  cursor: pointer;
  backdrop-filter: blur(4px);
}

.rate-btn {
  width: auto;
  min-width: 2.75rem;
  padding: 0 0.5rem;
  border-radius: 9999px;
  font-size: 0.875rem;
  font-weight: 500;
}

.screenshot-btn {
  margin-left: auto;
}

.subtitle-btn {
  font-size: 0.75rem;
  font-weight: 700;
  color: #ffffff;
}

.subtitle-btn.active {
  background: #2563eb;
}

.subtitle-track {
  position: absolute;
  left: 50%;
  bottom: 5rem;
  transform: translateX(-50%);
  max-width: 90%;
  padding: 0.5rem 1rem;
  background: rgba(0, 0, 0, 0.75);
  color: #ffffff;
  font-size: 1rem;
  line-height: 1.5;
  text-align: center;
  border-radius: 0.5rem;
  pointer-events: none;
}

.subtitle-track :deep(mark) {
  background: #facc15;
  color: #1a1a1a;
  border-radius: 0.25rem;
  padding: 0 0.125rem;
}

.time {
  color: #ffffff;
  font-size: 0.875rem;
  font-variant-numeric: tabular-nums;
}

.screenshot-toast {
  position: absolute;
  top: 0.75rem;
  left: 50%;
  transform: translateX(-50%);
  padding: 0.5rem 1rem;
  background: rgba(239, 68, 68, 0.9);
  color: #ffffff;
  font-size: 0.8125rem;
  border-radius: 0.375rem;
  pointer-events: none;
}
</style>
