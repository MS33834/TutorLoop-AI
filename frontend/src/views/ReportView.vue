<script setup>
import { ref, onMounted } from 'vue'
import { useUserStore } from '../stores/user.js'
import { apiFetch } from '../api/client.js'
import MasteryRadar from '../components/MasteryRadar.vue'

const props = defineProps({
  courseId: { type: String, required: true }
})

const user = useUserStore()
const loading = ref(false)
const error = ref('')
const report = ref(null)

onMounted(() => {
  loadReport()
})

async function loadReport() {
  if (!user.userId || !props.courseId) return
  loading.value = true
  error.value = ''
  try {
    const data = await apiFetch(
      `/api/users/${user.userId}/report?course_id=${encodeURIComponent(props.courseId)}`
    )
    report.value = data
  } catch (err) {
    error.value = err.message || '报告加载失败'
  } finally {
    loading.value = false
  }
}

function formatPercent(value) {
  if (typeof value !== 'number') return '0%'
  return `${Math.round(value * 100)}%`
}
</script>

<template>
  <div class="report">
    <div v-if="loading" class="status">加载报告中…</div>
    <div v-else-if="error" class="status error">{{ error }}</div>

    <template v-else-if="report">
      <header class="header">
        <h1 class="title">{{ report.course_title || '学习报告' }}</h1>
        <p class="subtitle">生成时间：{{ new Date(report.generated_at).toLocaleString() }}</p>
      </header>

      <section class="summary-grid">
        <div class="card">
          <p class="label">掌握度</p>
          <p class="value">{{ formatPercent(report.summary.average_mastery) }}</p>
        </div>
        <div class="card">
          <p class="label">已掌握 / 总节点</p>
          <p class="value">{{ report.summary.mastered_nodes }} / {{ report.summary.total_nodes }}</p>
        </div>
        <div class="card">
          <p class="label">正确率</p>
          <p class="value">{{ formatPercent(report.summary.accuracy) }}</p>
        </div>
        <div class="card">
          <p class="label">观看时长</p>
          <p class="value">{{ report.summary.total_watch_minutes }} 分钟</p>
        </div>
        <div class="card">
          <p class="label">交互次数</p>
          <p class="value">{{ report.summary.interaction_count }}</p>
        </div>
        <div class="card">
          <p class="label">近 7 天活跃</p>
          <p class="value">{{ report.summary.recent_7d_interactions }}</p>
        </div>
      </section>

      <section class="section">
        <h2 class="section-title">掌握度雷达</h2>
        <MasteryRadar :items="report.mastery_items" />
      </section>

      <section class="section">
        <h2 class="section-title">薄弱知识点 Top10</h2>
        <ul v-if="report.weak_nodes.length" class="weak-list">
          <li v-for="node in report.weak_nodes" :key="node.node_id" class="weak-item">
            <span class="weak-name">{{ node.name }}</span>
            <span class="weak-gap">差距 {{ formatPercent(node.gap) }}</span>
          </li>
        </ul>
        <p v-else class="empty">暂无薄弱知识点，继续保持！</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.report {
  max-width: 48rem;
  margin: 0 auto;
  padding: 1rem;
}

.status {
  text-align: center;
  padding: 2rem;
  color: #6b7280;
}

.status.error {
  color: #b91c1c;
  background: #fee2e2;
  border-radius: 0.5rem;
}

.header {
  margin-bottom: 1rem;
}

.title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: #111827;
}

.subtitle {
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
  color: #6b7280;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  padding: 0.875rem;
  text-align: center;
}

.label {
  margin: 0 0 0.375rem;
  font-size: 0.8125rem;
  color: #6b7280;
}

.value {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #111827;
}

.section {
  margin-bottom: 1.25rem;
}

.section-title {
  margin: 0 0 0.75rem;
  font-size: 1rem;
  font-weight: 600;
  color: #111827;
}

.weak-list {
  list-style: none;
  margin: 0;
  padding: 0;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  overflow: hidden;
}

.weak-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #f3f4f6;
}

.weak-item:last-child {
  border-bottom: none;
}

.weak-name {
  color: #374151;
  font-size: 0.9375rem;
}

.weak-gap {
  color: #ef4444;
  font-size: 0.875rem;
  font-weight: 500;
}

.empty {
  color: #6b7280;
  font-size: 0.9375rem;
  text-align: center;
  padding: 1rem;
}
</style>
