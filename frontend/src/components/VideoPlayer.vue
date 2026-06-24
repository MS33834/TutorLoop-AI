<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'

const props = defineProps({
  src: { type: String, default: '' },
  poster: { type: String, default: '' }
})

const emit = defineEmits(['screenshot', 'timeupdate'])

const video = ref(null)
const playing = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const buffered = ref(0)
const showControls = ref(true)
let controlsTimer = null

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
}

function onLoadedMetadata() {
  if (!video.value) return
  duration.value = video.value.duration
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

function seekTo(seconds) {
  if (!video.value) return
  video.value.currentTime = Math.max(0, seconds)
}

function takeScreenshot() {
  if (!video.value || !props.src) return
  const canvas = document.createElement('canvas')
  canvas.width = video.value.videoWidth || 640
  canvas.height = video.value.videoHeight || 360
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    // getContext can return null when the context is unavailable (e.g. in
    // some privacy/incognito modes or when GPU resources are exhausted).
    return
  }
  try {
    ctx.drawImage(video.value, 0, 0, canvas.width, canvas.height)
  } catch {
    // drawImage can throw if the video frame is not yet available.
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
})

onBeforeUnmount(() => {
  clearTimeout(controlsTimer)
})

defineExpose({
  seekTo
})
</script>

<template>
  <div class="video-player" @click="onContainerClick" @mousemove="onMouseMove" @touchstart="onMouseMove">
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

    <div class="controls" :class="{ visible: showControls }">
      <div class="progress-bar" @click.stop="seek">
        <div class="buffered" :style="{ width: `${bufferedPercent}%` }" />
        <div class="progress" :style="{ width: `${progressPercent}%` }" />
        <div class="thumb" :style="{ left: `${progressPercent}%` }" />
      </div>

      <div class="controls-row">
        <button class="control-btn play-btn" type="button" @click.stop="togglePlay">
          {{ playing ? '⏸' : '▶' }}
        </button>

        <span class="time">{{ formattedCurrentTime }} / {{ formattedDuration }}</span>

        <button class="control-btn screenshot-btn" type="button" title="截图提问" @click.stop="takeScreenshot">
          📷
        </button>
      </div>
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

.screenshot-btn {
  margin-left: auto;
}

.time {
  color: #ffffff;
  font-size: 0.875rem;
  font-variant-numeric: tabular-nums;
}
</style>
