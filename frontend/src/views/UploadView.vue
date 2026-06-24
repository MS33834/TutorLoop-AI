<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '../api/client.js'

const router = useRouter()

const title = ref('')
const description = ref('')
const videoFile = ref(null)
const materialFiles = ref([])
const status = ref('')
const error = ref('')
const loading = ref(false)

function onFileChange(e) {
  videoFile.value = e.target.files[0] || null
}

function onMaterialChange(e) {
  materialFiles.value = Array.from(e.target.files || [])
}

function removeMaterial(index) {
  materialFiles.value.splice(index, 1)
}

async function uploadMaterials(courseId) {
  if (!materialFiles.value.length) return
  for (const file of materialFiles.value) {
    const formData = new FormData()
    formData.append('file', file)
    await apiFetch(`/api/courses/${courseId}/materials`, {
      method: 'POST',
      body: formData
    })
  }
}

function setStatus(message) {
  status.value = message
  error.value = ''
}

async function submit() {
  if (!title.value.trim()) {
    error.value = '请输入课程标题'
    return
  }

  loading.value = true
  error.value = ''
  status.value = ''

  try {
    setStatus('正在创建课程…')
    const course = await apiFetch('/api/courses', {
      method: 'POST',
      body: JSON.stringify({
        title: title.value.trim(),
        description: description.value.trim()
      })
    })

    const courseId = course.id

    let videoId = null
    if (videoFile.value) {
      setStatus('正在上传视频，请稍候…')
      const formData = new FormData()
      formData.append('file', videoFile.value)
      const uploadResult = await apiFetch(`/api/courses/${courseId}/videos`, {
        method: 'POST',
        body: formData
      })
      videoId = uploadResult.video_id || null
    }

    setStatus('正在上传课程资料…')
    await uploadMaterials(courseId)

    setStatus('正在分析视频并构建知识图谱…')
    await apiFetch(`/api/courses/${courseId}/build-graph`, {
      method: 'POST',
      body: JSON.stringify({ video_id: videoId })
    })

    setStatus('课程创建完成，即将返回首页…')
    setTimeout(() => {
      router.push('/')
    }, 1200)
  } catch (err) {
    error.value = err.message || '上传没能完成，请检查视频后重试'
    status.value = ''
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="upload">
    <h2 class="page-title">上传课程</h2>

    <form class="upload-form" @submit.prevent="submit">
      <label class="field">
        <span class="label">课程标题</span>
        <input v-model="title" class="input" type="text" placeholder="例如：初一数学 二元一次方程" required />
      </label>

      <label class="field">
        <span class="label">课程描述</span>
        <textarea v-model="description" class="input textarea" rows="3" placeholder="简单介绍课程内容…" />
      </label>

      <label class="field">
        <span class="label">视频文件</span>
        <input class="file-input" type="file" accept="video/*" @change="onFileChange" />
        <span v-if="videoFile" class="file-name">已选择：{{ videoFile.name }}</span>
      </label>

      <label class="field">
        <span class="label">课程资料（PDF / 图片，可选）</span>
        <input
          class="file-input"
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          multiple
          @change="onMaterialChange"
        />
        <ul v-if="materialFiles.length" class="material-list">
          <li v-for="(file, idx) in materialFiles" :key="idx" class="material-item">
            <span class="material-name">{{ file.name }}</span>
            <button
              class="remove-material"
              type="button"
              :disabled="loading"
              @click="removeMaterial(idx)"
            >
              移除
            </button>
          </li>
        </ul>
        <span v-else class="file-hint">可上传课件 PDF 或参考图片辅助 AI 答疑</span>
      </label>

      <button class="submit-btn" type="submit" :disabled="loading">
        {{ loading ? '正在创建…' : '创建课程并构建图谱' }}
      </button>

      <div v-if="status" class="message status-msg">{{ status }}</div>
      <div v-if="error" class="message error-msg">{{ error }}</div>
    </form>
  </div>
</template>

<style scoped>
.upload {
  padding: 1rem;
  max-width: 32rem;
  margin: 0 auto;
}

.page-title {
  margin: 0 0 1rem;
  font-size: 1.25rem;
  font-weight: 600;
}

.upload-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
  background: #ffffff;
  border-radius: 0.75rem;
  border: 1px solid #e5e7eb;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.label {
  font-size: 0.9375rem;
  font-weight: 500;
}

.input {
  padding: 0.625rem 0.875rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  font-size: 0.9375rem;
  outline: none;
}

.input:focus {
  border-color: #2563eb;
}

.textarea {
  resize: vertical;
}

.file-input {
  font-size: 0.9375rem;
}

.file-name {
  font-size: 0.875rem;
  color: #4b5563;
}

.file-hint {
  font-size: 0.8125rem;
  color: #6b7280;
}

.material-list {
  margin: 0.375rem 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.material-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.375rem 0.5rem;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
}

.material-name {
  font-size: 0.875rem;
  color: #374151;
  word-break: break-all;
}

.remove-material {
  flex-shrink: 0;
  padding: 0.25rem 0.5rem;
  border: none;
  border-radius: 0.25rem;
  background: #fee2e2;
  color: #b91c1c;
  font-size: 0.75rem;
  cursor: pointer;
}

.remove-material:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.submit-btn {
  padding: 0.75rem;
  border: none;
  border-radius: 0.5rem;
  background: #2563eb;
  color: #ffffff;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
}

.submit-btn:disabled {
  background: #93c5fd;
  cursor: not-allowed;
}

.message {
  padding: 0.625rem 0.875rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  text-align: center;
}

.status-msg {
  background: #eff6ff;
  color: #1e40af;
}

.error-msg {
  background: #fee2e2;
  color: #b91c1c;
}
</style>
