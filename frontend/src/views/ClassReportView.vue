<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  Title,
  Tooltip,
  Legend,
  BarElement,
  CategoryScale,
  LinearScale
} from 'chart.js'
import { getClassReport } from '../api/reports.js'

ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale)

const props = defineProps({
  courseId: { type: String, required: true }
})

const router = useRouter()
const loading = ref(false)
const error = ref('')
const report = ref(null)
const pageSize = ref(20)
const currentSkip = ref(0)

onMounted(() => {
  loadReport()
})

async function loadReport(skip = 0) {
  loading.value = true
  error.value = ''
  currentSkip.value = skip
  try {
    report.value = await getClassReport(props.courseId, { skip, limit: pageSize.value })
  } catch (err) {
    error.value = err.message || '加载班级报告失败'
    report.value = null
  } finally {
    loading.value = false
  }
}

const totalPages = computed(() => {
  const total = report.value?.pagination?.total || 0
  return Math.ceil(total / pageSize.value) || 1
})

const currentPage = computed(() => Math.floor(currentSkip.value / pageSize.value) + 1)

function goToPage(page) {
  const newSkip = (page - 1) * pageSize.value
  loadReport(Math.max(0, newSkip))
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  let num = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(num)) return '-'
  if (num >= 0 && num <= 1) num = Math.round(num * 100)
  return `${Math.round(Math.min(100, Math.max(0, num)))}%`
}

function formatDate(value) {
  if (!value) return '-'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('zh-CN')
}

const activityChartData = computed(() => {
  const trend = report.value?.activity_trend || []
  return {
    labels: trend.map((d) => d.date.slice(5)),
    datasets: [
      {
        label: '交互次数',
        data: trend.map((d) => d.count),
        backgroundColor: '#2563eb',
        borderRadius: 4
      }
    ]
  }
})

const activityChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        title: (ctx) => `${ctx[0].label}`
      }
    }
  },
  scales: {
    y: { beginAtZero: true, ticks: { precision: 0 } },
    x: { grid: { display: false } }
  }
}
</script>

<template>
  <div class="class-report">
    <div v-if="loading" class="status">加载中…</div>
    <div v-else-if="error" class="status error">
      <p>{{ error }}</p>
      <button class="retry-btn" type="button" @click="loadReport">重试</button>
    </div>

    <template v-else-if="report">
      <header class="header">
        <div>
          <h1 class="title">班级学情看板</h1>
          <p class="subtitle">生成时间：{{ formatDate(report.generated_at) }}</p>
        </div>
        <button class="back-btn" type="button" @click="router.push('/dashboard')">
          返回后台
        </button>
      </header>

      <section class="summary">
        <div class="summary-card">
          <p class="label">参与学生</p>
          <p class="value">{{ report.summary?.total_students ?? 0 }}</p>
        </div>
        <div class="summary-card">
          <p class="label">总交互次数</p>
          <p class="value">{{ report.summary?.total_interactions ?? 0 }}</p>
        </div>
        <div class="summary-card">
          <p class="label">总观看时长</p>
          <p class="value">{{ report.summary?.total_watch_minutes ?? 0 }} 分钟</p>
        </div>
        <div class="summary-card">
          <p class="label">班级正确率</p>
          <p class="value">{{ formatPercent(report.summary?.accuracy) }}</p>
        </div>
        <div class="summary-card">
          <p class="label">平均掌握度</p>
          <p class="value">{{ formatPercent(report.summary?.class_avg_mastery) }}</p>
        </div>
        <div class="summary-card">
          <p class="label">求助总数</p>
          <p class="value">{{ report.summary?.total_help_count ?? 0 }}</p>
        </div>
      </section>

      <div class="two-col">
        <section class="panel">
          <h2 class="panel-title">近 7 天活跃趋势</h2>
          <div class="chart-wrapper">
            <Bar :data="activityChartData" :options="activityChartOptions" />
          </div>
        </section>

        <section class="panel">
          <h2 class="panel-title">薄弱知识点 Top10</h2>
          <ul v-if="report.weak_nodes?.length" class="weak-list">
            <li v-for="node in report.weak_nodes" :key="node.node_id" class="weak-item">
              <span class="weak-name">{{ node.name }}</span>
              <span class="weak-meta">
                平均 {{ formatPercent(node.avg_p_known) }} · {{ node.struggling_students }} 人未掌握
              </span>
            </li>
          </ul>
          <p v-else class="empty">暂无薄弱知识点，班级整体掌握良好。</p>
        </section>
      </div>

      <section class="panel">
        <h2 class="panel-title">学生明细</h2>
        <div v-if="report.students?.length" class="table-wrapper">
          <table class="student-table">
            <thead>
              <tr>
                <th>学生</th>
                <th>交互次数</th>
                <th>观看时长</th>
                <th>正确率</th>
                <th>平均掌握度</th>
                <th>最近活跃</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in report.students" :key="s.user_id">
                <td>{{ s.username }}</td>
                <td>{{ s.interaction_count }}</td>
                <td>{{ s.watch_minutes }} 分钟</td>
                <td>{{ formatPercent(s.accuracy) }}</td>
                <td>{{ formatPercent(s.avg_mastery) }}</td>
                <td>{{ formatDate(s.last_active_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="empty">还没有学生参与记录，分享房间号邀请学生开始学习吧。</p>

        <div v-if="report.pagination?.total > pageSize" class="pagination">
          <button
            type="button"
            class="page-btn"
            :disabled="currentPage <= 1"
            @click="goToPage(currentPage - 1)"
          >
            上一页
          </button>
          <span class="page-info">第 {{ currentPage }} / {{ totalPages }} 页</span>
          <button
            type="button"
            class="page-btn"
            :disabled="currentPage >= totalPages"
            @click="goToPage(currentPage + 1)"
          >
            下一页
          </button>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.class-report {
  max-width: 60rem;
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
  border-radius: 0.75rem;
}

.retry-btn {
  margin-top: 0.75rem;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 0.375rem;
  background: #2563eb;
  color: #ffffff;
  cursor: pointer;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.title {
  margin: 0;
  font-size: 1.375rem;
  font-weight: 700;
}

.subtitle {
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
  color: #6b7280;
}

.back-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  background: #ffffff;
  font-size: 0.875rem;
  cursor: pointer;
}

.summary {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.summary-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  padding: 1rem;
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
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

@media (max-width: 640px) {
  .two-col {
    grid-template-columns: 1fr;
  }
}

.panel {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  padding: 1rem;
}

.panel-title {
  margin: 0 0 0.75rem;
  font-size: 1rem;
  font-weight: 600;
}

.chart-wrapper {
  position: relative;
  height: 12rem;
}

.weak-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.weak-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.625rem 0.75rem;
  background: #fef2f2;
  border-radius: 0.5rem;
  font-size: 0.875rem;
}

.weak-name {
  color: #374151;
  font-weight: 500;
}

.weak-meta {
  color: #b91c1c;
  font-size: 0.8125rem;
  flex-shrink: 0;
}

.empty {
  margin: 0;
  padding: 1rem;
  text-align: center;
  color: #6b7280;
  font-size: 0.9375rem;
}

.table-wrapper {
  overflow-x: auto;
}

.student-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.student-table th,
.student-table td {
  padding: 0.625rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid #f3f4f6;
}

.student-table th {
  color: #6b7280;
  font-weight: 500;
  background: #f9fafb;
}

.student-table tbody tr:hover {
  background: #f9fafb;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  margin-top: 1rem;
}

.page-btn {
  padding: 0.375rem 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  background: #ffffff;
  font-size: 0.875rem;
  cursor: pointer;
}

.page-btn:disabled {
  color: #9ca3af;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.875rem;
  color: #6b7280;
}
</style>
