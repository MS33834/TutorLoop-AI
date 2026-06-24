<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import Qrcode from 'qrcode.vue'
import { apiFetch } from '../api/client.js'
import { listCourseRooms, createRoom, deleteRoom, updateRoom } from '../api/rooms.js'
import { formatDate as formatDateTime } from '../utils/format.js'

const router = useRouter()
const courses = ref([])
const roomsByCourse = ref({})
const loading = ref(false)
const error = ref('')
const expandedCourse = ref('')
const refreshTimer = ref(null)

const creatingFor = ref('')
const createTitle = ref('')
const createPassword = ref('')
const createExpiresAt = ref('')
const createAllowAnonymous = ref(true)
const createLoading = ref(false)
const createError = ref('')

const editingRoomId = ref('')
const editTitle = ref('')
const editWelcomeMessage = ref('')
const editExpiresAt = ref('')
const editAllowAnonymous = ref(true)
const editMaxParticipants = ref('')
const editPassword = ref('')
const editLoading = ref(false)
const editError = ref('')

const showQrcodeFor = ref('')
const qrcodeSlug = ref('')
const copyHint = ref('')

onMounted(() => {
  loadCourses()
})

onBeforeUnmount(() => {
  clearRefreshTimer()
})

function clearRefreshTimer() {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value)
    refreshTimer.value = null
  }
}

async function loadCourses() {
  loading.value = true
  error.value = ''
  try {
    const data = await apiFetch('/api/courses')
    courses.value = Array.isArray(data) ? data : []
  } catch (err) {
    error.value = err.message || '加载课程失败'
  } finally {
    loading.value = false
  }
}

async function toggleCourse(courseId) {
  if (expandedCourse.value === courseId) {
    expandedCourse.value = ''
    clearRefreshTimer()
    return
  }
  expandedCourse.value = courseId
  clearRefreshTimer()
  await loadRooms(courseId)
  refreshTimer.value = setInterval(() => {
    if (expandedCourse.value === courseId) {
      loadRooms(courseId)
    }
  }, 10000)
}

async function loadRooms(courseId) {
  try {
    const data = await listCourseRooms(courseId)
    roomsByCourse.value[courseId] = Array.isArray(data) ? data : []
  } catch (err) {
    error.value = err.message || '加载房间失败'
  }
}

function startCreate(courseId) {
  creatingFor.value = courseId
  createTitle.value = ''
  createPassword.value = ''
  createExpiresAt.value = ''
  createAllowAnonymous.value = true
  createError.value = ''
}

function cancelCreate() {
  creatingFor.value = ''
}

function goToClassReport(courseId) {
  router.push(`/class-report/${encodeURIComponent(courseId)}`)
}

async function submitCreate(courseId) {
  createLoading.value = true
  createError.value = ''
  try {
    const payload = {
      title: createTitle.value.trim() || undefined,
      password: createPassword.value.trim() || undefined,
      expires_at: createExpiresAt.value || undefined,
      allow_anonymous: createAllowAnonymous.value
    }
    await createRoom(courseId, payload)
    await loadRooms(courseId)
    cancelCreate()
  } catch (err) {
    createError.value = err.message || '创建房间失败'
  } finally {
    createLoading.value = false
  }
}

async function removeRoom(courseId, roomId) {
  if (!confirm('确定要删除这个房间吗？学生将无法再通过该房间号进入。')) return
  try {
    await deleteRoom(roomId)
    await loadRooms(courseId)
  } catch (err) {
    error.value = err.message || '删除房间失败'
  }
}

async function toggleRoomActive(courseId, room) {
  try {
    await updateRoom(room.id, { is_active: !room.is_active })
    await loadRooms(courseId)
  } catch (err) {
    error.value = err.message || '更新房间状态失败'
  }
}

function shareUrl(slug) {
  return `${window.location.origin}/room/${encodeURIComponent(slug)}`
}

function openQrcode(room) {
  qrcodeSlug.value = room.slug
  showQrcodeFor.value = room.id
  copyHint.value = ''
}

function closeQrcode() {
  showQrcodeFor.value = ''
  qrcodeSlug.value = ''
}

async function copyLink(slug) {
  const url = shareUrl(slug)
  try {
    await navigator.clipboard.writeText(url)
    copyHint.value = '链接已复制'
  } catch {
    prompt('请复制以下链接', url)
  }
}

function startEdit(room) {
  editingRoomId.value = room.id
  editTitle.value = room.title || ''
  editWelcomeMessage.value = room.welcome_message || ''
  editExpiresAt.value = room.expires_at ? toDatetimeLocal(room.expires_at) : ''
  editAllowAnonymous.value = room.allow_anonymous
  editMaxParticipants.value = room.max_participants ?? ''
  editPassword.value = ''
  editError.value = ''
}

function cancelEdit() {
  editingRoomId.value = ''
}

async function submitEdit(courseId, roomId) {
  editLoading.value = true
  editError.value = ''
  try {
    const payload = {
      title: editTitle.value.trim() || undefined,
      welcome_message: editWelcomeMessage.value.trim() || undefined,
      expires_at: editExpiresAt.value || undefined,
      allow_anonymous: editAllowAnonymous.value,
      max_participants: editMaxParticipants.value ? Number(editMaxParticipants.value) : undefined
    }
    if (editPassword.value.trim()) {
      payload.password = editPassword.value.trim()
    }
    await updateRoom(roomId, payload)
    await loadRooms(courseId)
    cancelEdit()
  } catch (err) {
    editError.value = err.message || '保存失败'
  } finally {
    editLoading.value = false
  }
}

function toDatetimeLocal(iso) {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatDate(iso) {
  // Room expiry uses a distinct empty-state label ("永不过期").
  return iso ? formatDateTime(iso) : '永不过期'
}

function formatActivity(iso) {
  return iso ? formatDateTime(iso) : '还未开始活动'
}
</script>

<template>
  <div class="dashboard">
    <h2 class="page-title">老师后台 · 房间管理</h2>

    <div v-if="loading" class="status">加载中…</div>
    <div v-else-if="error" class="status error">{{ error }}</div>
    <div v-else-if="courses.length === 0" class="status empty">
      还没有课程，去上传第一个视频开始吧。
    </div>

    <div v-else class="course-list">
      <div
        v-for="course in courses"
        :key="course.id"
        class="course-card"
      >
        <div class="course-header" @click="toggleCourse(course.id)">
          <div class="course-meta">
            <h3 class="course-title">{{ course.title }}</h3>
            <p class="course-desc">{{ course.description || '暂无描述' }}</p>
          </div>
          <span class="toggle-icon">{{ expandedCourse === course.id ? '▼' : '▶' }}</span>
        </div>

        <div v-if="expandedCourse === course.id" class="course-body">
          <div
            v-if="creatingFor !== course.id"
            class="course-actions"
          >
            <button
              class="create-btn"
              type="button"
              @click="startCreate(course.id)"
            >
              + 创建学习房间
            </button>
            <button
              class="report-btn"
              type="button"
              @click="goToClassReport(course.id)"
            >
              学情看板
            </button>
          </div>

          <form
            v-else
            class="create-form"
            @submit.prevent="submitCreate(course.id)"
          >
            <label class="field">
              <span class="field-label">房间名称</span>
              <input v-model="createTitle" class="field-input" type="text" placeholder="例如：初一1班晚自习" />
            </label>
            <label class="field">
              <span class="field-label">房间密码（留空表示公开）</span>
              <input v-model="createPassword" class="field-input" type="password" placeholder="可选" />
            </label>
            <label class="field">
              <span class="field-label">过期时间（留空表示永不过期）</span>
              <input v-model="createExpiresAt" class="field-input" type="datetime-local" />
            </label>
            <label class="field checkbox">
              <input v-model="createAllowAnonymous" type="checkbox" />
              <span class="field-label">允许未登录学生进入</span>
            </label>
            <div class="form-actions">
              <button class="submit-btn" type="submit" :disabled="createLoading">
                {{ createLoading ? '创建中…' : '创建' }}
              </button>
              <button class="cancel-btn" type="button" @click="cancelCreate">取消</button>
            </div>
            <div v-if="createError" class="form-error">{{ createError }}</div>
          </form>

          <div v-if="roomsByCourse[course.id]?.length" class="room-list">
            <div
              v-for="room in roomsByCourse[course.id]"
              :key="room.id"
              class="room-item"
              :class="{ inactive: !room.is_active }"
            >
              <div v-if="editingRoomId === room.id" class="edit-form">
                <label class="field">
                  <span class="field-label">房间名称</span>
                  <input v-model="editTitle" class="field-input" type="text" />
                </label>
                <label class="field">
                  <span class="field-label">欢迎语</span>
                  <textarea v-model="editWelcomeMessage" class="field-input" rows="2" placeholder="学生进入房间时看到的提示"></textarea>
                </label>
                <label class="field">
                  <span class="field-label">过期时间</span>
                  <input v-model="editExpiresAt" class="field-input" type="datetime-local" />
                </label>
                <label class="field">
                  <span class="field-label">人数上限（留空表示不限）</span>
                  <input v-model="editMaxParticipants" class="field-input" type="number" min="1" />
                </label>
                <label class="field">
                  <span class="field-label">新密码（留空表示不变）</span>
                  <input v-model="editPassword" class="field-input" type="password" placeholder="仅在需要修改时填写" />
                </label>
                <label class="field checkbox">
                  <input v-model="editAllowAnonymous" type="checkbox" />
                  <span class="field-label">允许未登录学生进入</span>
                </label>
                <div class="form-actions">
                  <button class="submit-btn" type="button" :disabled="editLoading" @click="submitEdit(course.id, room.id)">
                    {{ editLoading ? '保存中…' : '保存' }}
                  </button>
                  <button class="cancel-btn" type="button" @click="cancelEdit">取消</button>
                </div>
                <div v-if="editError" class="form-error">{{ editError }}</div>
              </div>

              <template v-else>
                <div class="room-info">
                  <div class="room-title-row">
                    <span class="room-name">{{ room.title || '未命名房间' }}</span>
                    <span class="room-status">{{ room.is_active ? '进行中' : '已关闭' }}</span>
                  </div>
                  <p v-if="room.welcome_message" class="room-welcome">{{ room.welcome_message }}</p>
                  <div class="room-meta">
                    <span>房间号：{{ room.slug }}</span>
                    <span>过期：{{ formatDate(room.expires_at) }}</span>
                    <span>{{ room.allow_anonymous ? '允许匿名' : '需登录' }}</span>
                    <span>访问：{{ room.entry_count }}次</span>
                    <span>最近活动：{{ formatActivity(room.last_activity_at) }}</span>
                    <span v-if="room.max_participants">上限：{{ room.max_participants }}人</span>
                  </div>
                </div>
                <div class="room-actions">
                  <button class="action-btn" type="button" @click="copyLink(room.slug)">复制链接</button>
                  <button class="action-btn" type="button" @click="openQrcode(room)">二维码</button>
                  <button class="action-btn" type="button" @click="startEdit(room)">编辑</button>
                  <button
                    class="action-btn"
                    type="button"
                    @click="toggleRoomActive(course.id, room)"
                  >
                    {{ room.is_active ? '关闭' : '开启' }}
                  </button>
                  <button class="action-btn danger" type="button" @click="removeRoom(course.id, room.id)">删除</button>
                </div>
              </template>
            </div>
          </div>
          <div v-else class="empty-rooms">这门课还没有学习房间，点击上方创建一个吧。</div>
        </div>
      </div>
    </div>

    <div v-if="showQrcodeFor" class="qrcode-modal" @click.self="closeQrcode">
      <div class="qrcode-panel">
        <h3 class="qrcode-title">扫码进入房间</h3>
        <Qrcode :value="shareUrl(qrcodeSlug)" :size="168" />
        <p class="qrcode-slug">房间号：{{ qrcodeSlug }}</p>
        <div class="qrcode-actions">
          <button class="submit-btn" type="button" @click="copyLink(qrcodeSlug)">复制链接</button>
          <button class="cancel-btn" type="button" @click="closeQrcode">关闭</button>
        </div>
        <p v-if="copyHint" class="copy-hint">{{ copyHint }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  padding: 1rem;
  max-width: 52rem;
  margin: 0 auto;
}

.page-title {
  margin: 0 0 1rem;
  font-size: 1.25rem;
  font-weight: 600;
}

.status {
  padding: 1rem;
  text-align: center;
  color: #6b7280;
  background: #ffffff;
  border-radius: 0.75rem;
  border: 1px solid #e5e7eb;
}

.status.error {
  color: #b91c1c;
  background: #fee2e2;
}

.course-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.course-card {
  background: #ffffff;
  border-radius: 0.75rem;
  border: 1px solid #e5e7eb;
  overflow: hidden;
}

.course-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.875rem 1rem;
  cursor: pointer;
  transition: background 0.15s ease;
}

.course-header:hover {
  background: #f9fafb;
}

.course-title {
  margin: 0 0 0.25rem;
  font-size: 1rem;
  font-weight: 600;
}

.course-desc {
  margin: 0;
  font-size: 0.875rem;
  color: #6b7280;
}

.toggle-icon {
  color: #6b7280;
  font-size: 0.875rem;
}

.course-body {
  padding: 1rem;
  border-top: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.course-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.create-btn {
  padding: 0.5rem 0.875rem;
  border: none;
  border-radius: 0.5rem;
  background: #2563eb;
  color: #ffffff;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}

.report-btn {
  padding: 0.5rem 0.875rem;
  border: 1px solid #2563eb;
  border-radius: 0.5rem;
  background: #ffffff;
  color: #2563eb;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}

.create-form,
.edit-form {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  padding: 0.875rem;
  background: #f9fafb;
  border-radius: 0.5rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.field.checkbox {
  flex-direction: row;
  align-items: center;
  gap: 0.5rem;
}

.field-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: #374151;
}

.field-input {
  padding: 0.5rem 0.625rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  font-size: 0.9375rem;
}

.form-actions {
  display: flex;
  gap: 0.5rem;
}

.submit-btn {
  padding: 0.5rem 0.875rem;
  border: none;
  border-radius: 0.375rem;
  background: #2563eb;
  color: #ffffff;
  font-size: 0.875rem;
  cursor: pointer;
}

.submit-btn:disabled {
  background: #93c5fd;
}

.cancel-btn {
  padding: 0.5rem 0.875rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  background: #ffffff;
  font-size: 0.875rem;
  cursor: pointer;
}

.form-error {
  color: #b91c1c;
  font-size: 0.875rem;
}

.room-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.room-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem;
  background: #f9fafb;
  border-radius: 0.5rem;
}

.room-item.inactive {
  opacity: 0.7;
}

.room-info {
  flex: 1;
  min-width: 0;
}

.room-title-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.room-name {
  font-weight: 600;
  font-size: 0.9375rem;
}

.room-status {
  font-size: 0.75rem;
  padding: 0.125rem 0.375rem;
  border-radius: 9999px;
  background: #dcfce7;
  color: #166534;
}

.room-item.inactive .room-status {
  background: #e5e7eb;
  color: #374151;
}

.room-welcome {
  margin: 0 0 0.375rem;
  font-size: 0.8125rem;
  color: #4b5563;
  line-height: 1.4;
}

.room-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: #6b7280;
}

.room-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  flex-shrink: 0;
  max-width: 12rem;
  justify-content: flex-end;
}

.action-btn {
  padding: 0.375rem 0.625rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  background: #ffffff;
  font-size: 0.8125rem;
  cursor: pointer;
}

.action-btn.danger {
  color: #b91c1c;
  border-color: #fecaca;
}

.empty-rooms {
  padding: 0.75rem;
  text-align: center;
  color: #6b7280;
  font-size: 0.875rem;
  background: #f9fafb;
  border-radius: 0.5rem;
}

.qrcode-modal {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  z-index: 50;
}

.qrcode-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 1.5rem;
  background: #ffffff;
  border-radius: 0.75rem;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
}

.qrcode-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.qrcode-slug {
  margin: 0;
  font-size: 0.875rem;
  color: #6b7280;
}

.qrcode-actions {
  display: flex;
  gap: 0.5rem;
}

.copy-hint {
  margin: 0;
  font-size: 0.8125rem;
  color: #166534;
}
</style>
