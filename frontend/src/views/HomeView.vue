<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '../api/client.js'

const router = useRouter()
const courses = ref([])
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  loading.value = true
  try {
    courses.value = await apiFetch('/api/courses')
  } catch (err) {
    error.value = err.message || '加载课程失败'
  } finally {
    loading.value = false
  }
})

function goToRoom(course) {
  const slug = course.default_room_slug || String(course.id)
  router.push(`/room/${slug}`)
}

function goToGraph(course) {
  router.push(`/graph/${course.id}`)
}
</script>

<template>
  <div class="home">
    <h2 class="page-title">课程列表</h2>

    <div v-if="loading" class="status">加载中…</div>
    <div v-else-if="error" class="status error">{{ error }}</div>

    <div class="course-grid">
      <div v-for="course in courses" :key="course.id" class="course-card">
        <h3 class="course-title">{{ course.title }}</h3>
        <p class="course-desc">{{ course.description || '暂无描述' }}</p>
        <div class="course-actions">
          <button class="btn primary" type="button" @click="goToRoom(course)">学习</button>
          <button class="btn" type="button" @click="goToGraph(course)">查看图谱</button>
        </div>
      </div>
    </div>

    <div v-if="!loading && !courses.length && !error" class="empty">
      暂无课程，老师可以先去上传。
    </div>
  </div>
</template>

<style scoped>
.home {
  padding: 1rem;
  max-width: 64rem;
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
}

.status.error {
  color: #b91c1c;
  background: #fee2e2;
  border-radius: 0.5rem;
}

.course-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
}

.course-card {
  padding: 1rem;
  background: #ffffff;
  border-radius: 0.75rem;
  border: 1px solid #e5e7eb;
}

.course-title {
  margin: 0 0 0.5rem;
  font-size: 1.0625rem;
  font-weight: 600;
}

.course-desc {
  margin: 0 0 1rem;
  font-size: 0.875rem;
  color: #4b5563;
  line-height: 1.5;
  min-height: 2.625rem;
}

.course-actions {
  display: flex;
  gap: 0.5rem;
}

.btn {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  background: #ffffff;
  font-size: 0.9375rem;
  cursor: pointer;
}

.btn.primary {
  background: #2563eb;
  color: #ffffff;
  border-color: #2563eb;
}

.empty {
  padding: 2rem;
  text-align: center;
  color: #6b7280;
}
</style>
