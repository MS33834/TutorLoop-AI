<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user.js'
import { apiFetch } from '../api/client.js'
import MasteryRadar from '../components/MasteryRadar.vue'
import { Line, Pie } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js'
import { normalizePercent, formatPercent, formatDate, formatShortDate } from '../utils/format.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, ArcElement, Title, Tooltip, Legend)

const props = defineProps({
  courseId: { type: String, required: true }
})

const router = useRouter()
const user = useUserStore()
const loading = ref(false)
const error = ref('')
const report = ref(null)
const timeline = ref(null)
const timelineLoading = ref(false)
const timelineError = ref('')

onMounted(() => {
  loadReport()
})

watch(() => props.courseId, () => {
  loadReport()
})

watch(() => user.isLoggedIn, () => {
  loadReport()
})

async function loadTimeline() {
  timelineLoading.value = true
  timelineError.value = ''
  try {
    const data = await apiFetch(
      `/api/users/me/timeline?course_id=${encodeURIComponent(props.courseId)}&days=30`
    )
    timeline.value = data
  } catch (err) {
    timelineError.value = err.message || '时序数据加载失败'
    timeline.value = null
  } finally {
    timelineLoading.value = false
  }
}

const masteredItems = computed(() => {
  if (!report.value?.mastery_items) return []
  return report.value.mastery_items
    .filter((i) => normalizePercent(i?.p_known) >= normalizePercent(i?.threshold))
    .sort((a, b) => normalizePercent(b.p_known) - normalizePercent(a.p_known))
    .slice(0, 3)
})

const nextActions = computed(() => {
  if (!report.value) return []
  const actions = []
  const s = report.value.summary || {}
  if (typeof s.accuracy === 'number' && normalizePercent(s.accuracy) < 60) {
    actions.push({
      icon: '📘',
      text: '正确率偏低，建议先回顾基础知识，再尝试更难的问题。',
      primary: true
    })
  }
  if (typeof s.mastery_rate === 'number' && normalizePercent(s.mastery_rate) < 50) {
    actions.push({
      icon: '🎯',
      text: '整体掌握度不足，优先完成系统推荐的薄弱知识点。',
      primary: true
    })
  }
  if (typeof s.recent_7d_interactions === 'number' && s.recent_7d_interactions === 0) {
    actions.push({
      icon: '📅',
      text: '最近 7 天没有学习记录，保持每日小步学习效果更佳。'
    })
  }
  const weakest = report.value.weak_nodes?.[0]
  if (weakest) {
    actions.push({
      icon: '🔍',
      text: `重点突破：${weakest.name}（差距 ${formatPercent(weakest.gap)}）`,
      primary: true
    })
  }
  actions.push({
    icon: '💬',
    text: '针对薄弱知识点多次提问与反馈，帮助系统更精准地调整推荐。'
  })
  return actions.slice(0, 4)
})

async function goToRoom() {
  // course_id 不是 room slug，需要先查询该课程对应的房间再跳转。
  const courseId = report.value?.course_id
  if (!courseId) return
  try {
    const rooms = await apiFetch(`/api/courses/${encodeURIComponent(courseId)}/rooms`)
    const slug = Array.isArray(rooms) && rooms.length ? rooms[0].slug : null
    if (slug) {
      router.push(`/room/${slug}`)
    } else {
      // 该课程暂无房间，回到首页让学生通过房间号进入。
      router.push('/')
    }
  } catch {
    // 查询房间失败，降级跳转首页。
    router.push('/')
  }
}

const heatmapData = computed(() => {
  if (!timeline.value?.daily_activity) return []
  return timeline.value.daily_activity
})

const heatmapMax = computed(() => {
  if (!heatmapData.value.length) return 1
  return Math.max(1, ...heatmapData.value.map((d) => d.count || 0))
})

// PRD 要求"视频时间轴上的停留与回看分布"。若后端 timeline 返回 video_heatmap
// 则展示该区域；否则仅保留日历热力图（学习活跃度），视频时间轴热力图待后端支持。
const videoHeatmap = computed(() => {
  const data = timeline.value?.video_heatmap
  if (!Array.isArray(data) || !data.length) return []
  return data
})

const videoHeatmapMax = computed(() => {
  if (!videoHeatmap.value.length) return 1
  return Math.max(1, ...videoHeatmap.value.map((d) => d.count || d.value || 0))
})

function videoHeatmapColor(count) {
  const ratio = Math.min(count / videoHeatmapMax.value, 1)
  const alpha = 0.15 + ratio * 0.85
  return `rgba(245, 158, 11, ${alpha})`
}

// 提问类型分布：若后端返回 question_distribution 则用饼图展示。
const questionDistributionData = computed(() => {
  const dist = report.value?.question_distribution
  if (!Array.isArray(dist) || !dist.length) return null
  return {
    labels: dist.map((d) => d.label || d.type || d.name),
    datasets: [
      {
        data: dist.map((d) => d.count ?? d.value ?? 0),
        backgroundColor: [
          '#2563eb',
          '#7c3aed',
          '#f59e0b',
          '#10b981',
          '#ef4444',
          '#06b6d4',
          '#ec4899'
        ],
        borderWidth: 1
      }
    ]
  }
})

const questionDistributionOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 12 } } }
  }
}

function heatmapColor(count) {
  const ratio = Math.min(count / heatmapMax.value, 1)
  const alpha = 0.15 + ratio * 0.85
  return `rgba(37, 99, 235, ${alpha})`
}

const masteryChartData = computed(() => {
  const items = timeline.value?.mastery_curve || report.value?.mastery_items || []
  if (!items.length) return null
  const labels = items.map((i) => i.name)
  return {
    labels,
    datasets: [
      {
        label: '掌握度',
        data: items.map((i) => normalizePercent(i.p_known)),
        borderColor: '#2563eb',
        backgroundColor: 'rgba(37, 99, 235, 0.2)',
        tension: 0.3,
        fill: true
      },
      {
        label: '阈值',
        data: items.map((i) => normalizePercent(i.threshold)),
        borderColor: '#ef4444',
        borderDash: [6, 4],
        tension: 0.3,
        fill: false
      }
    ]
  }
})

const masteryChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'bottom' }
  },
  scales: {
    y: { min: 0, max: 100 }
  }
}

const buildCacheKey = (courseId, userId) => `tutorloop-report-${userId || 'anon'}-${courseId}`

function cacheReport(data) {
  try {
    localStorage.setItem(buildCacheKey(props.courseId, user.userId), JSON.stringify({
      savedAt: new Date().toISOString(),
      data
    }))
  } catch (err) {
    // Silently ignore storage errors (e.g. private mode, quota exceeded).
  }
}

function loadCachedReport() {
  try {
    const raw = localStorage.getItem(buildCacheKey(props.courseId, user.userId))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed.data || null
  } catch (err) {
    return null
  }
}

// 请求版本号：防止 courseId 快速切换时旧请求覆盖新请求的结果（竞态）。
let loadReportVersion = 0

// 示例报告（/report/demo）：未登录用户也可预览报告样式，使用静态示例数据，
// 避免向后端发送带身份的请求。
function loadDemoReport() {
  report.value = {
    course_id: 'demo',
    course_title: '示例学习报告',
    generated_at: new Date().toISOString(),
    summary: {
      average_mastery: 0.62,
      mastered_nodes: 4,
      total_nodes: 8,
      accuracy: 0.71,
      total_watch_minutes: 86,
      interaction_count: 53,
      recent_7d_interactions: 12,
      total_help_count: 6,
      mastery_rate: 0.5
    },
    mastery_items: [
      { node_id: 'd1', name: '二元一次方程', p_known: 0.85, threshold: 0.8 },
      { node_id: 'd2', name: '代入消元法', p_known: 0.72, threshold: 0.8 },
      { node_id: 'd3', name: '加减消元法', p_known: 0.64, threshold: 0.8 },
      { node_id: 'd4', name: '应用题建模', p_known: 0.41, threshold: 0.8 },
      { node_id: 'd5', name: '图像法求解', p_known: 0.55, threshold: 0.8 },
      { node_id: 'd6', name: '方程组解的情况', p_known: 0.33, threshold: 0.8 }
    ],
    weak_nodes: [
      { node_id: 'd4', name: '应用题建模', gap: 0.39 },
      { node_id: 'd6', name: '方程组解的情况', gap: 0.47 },
      { node_id: 'd5', name: '图像法求解', gap: 0.25 }
    ],
    question_distribution: [
      { label: '概念理解', count: 18 },
      { label: '解题求助', count: 12 },
      { label: '错题回顾', count: 9 },
      { label: '截图提问', count: 14 }
    ]
  }
  timeline.value = {
    daily_activity: [
      { date: '2026-06-26', count: 4, watch_minutes: 12 },
      { date: '2026-06-27', count: 7, watch_minutes: 20 },
      { date: '2026-06-28', count: 2, watch_minutes: 6 },
      { date: '2026-06-29', count: 9, watch_minutes: 25 },
      { date: '2026-06-30', count: 5, watch_minutes: 15 },
      { date: '2026-07-01', count: 12, watch_minutes: 8 }
    ],
    mastery_curve: report.value.mastery_items
  }
  loading.value = false
  error.value = ''
}

async function loadReport() {
  // 示例报告无需登录，直接展示静态数据供访客预览。
  if (props.courseId === 'demo') {
    loading.value = true
    error.value = ''
    // 让 loading 态短暂展示，避免界面闪烁。
    setTimeout(loadDemoReport, 0)
    return
  }
  if (!user.isLoggedIn) {
    error.value = '请先登录'
    report.value = null
    return
  }
  if (!props.courseId) {
    error.value = '缺少课程 ID'
    report.value = null
    return
  }
  const myVersion = ++loadReportVersion
  loading.value = true
  error.value = ''
  try {
    const data = await apiFetch(
      `/api/users/me/report?course_id=${encodeURIComponent(props.courseId)}`
    )
    // 旧请求返回时丢弃，避免覆盖更新的 courseId 结果。
    if (myVersion !== loadReportVersion) return
    report.value = data
    cacheReport(report.value)
    // Load timeline independently so a timeline failure does not mask the report.
    loadTimeline()
  } catch (err) {
    if (myVersion !== loadReportVersion) return
    error.value = err.message || '报告暂时无法加载，稍后再来看看'
    const cached = loadCachedReport()
    if (cached) {
      report.value = cached
      error.value = '已显示本地缓存的报告，数据可能不是最新的。'
    } else {
      report.value = null
    }
  } finally {
    if (myVersion === loadReportVersion) {
      loading.value = false
    }
  }
}

function exportReport() {
  const printWindow = window.open('', '_blank')
  if (!printWindow) {
    alert('请允许弹窗，以便导出报告。')
    return
  }

  // Escape dynamic text before injecting into HTML to prevent XSS via
  // attacker-controlled node names / course titles.
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]))

  const title = esc(report.value?.course_title || '学习报告')
  const items = (report.value?.mastery_items || [])
    .map((item) => `
      <tr>
        <td>${esc(item.name)}</td>
        <td>${formatPercent(item.p_known)}</td>
        <td>${formatPercent(item.threshold)}</td>
      </tr>
    `).join('')

  const html = `
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8">
      <title>${title}</title>
      <style>
        body { font-family: system-ui, -apple-system, sans-serif; color: #111827; padding: 2rem; }
        h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
        .meta { color: #6b7280; margin-bottom: 1.5rem; }
        .summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1.5rem; }
        .card { border: 1px solid #e5e7eb; border-radius: 0.75rem; padding: 1rem; text-align: center; }
        .card .value { font-size: 1.25rem; font-weight: 700; }
        .card .label { color: #6b7280; font-size: 0.875rem; }
        table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
        th, td { border-bottom: 1px solid #e5e7eb; padding: 0.625rem; text-align: left; }
        th { color: #6b7280; font-weight: 500; }
      </style>
    </head>
    <body>
      <h1>${title}</h1>
      <p class="meta">生成时间：${formatDate(report.value?.generated_at)}</p>
      <div class="summary">
        <div class="card"><div class="value">${formatPercent(report.value?.summary?.average_mastery)}</div><div class="label">平均掌握度</div></div>
        <div class="card"><div class="value">${formatPercent(report.value?.summary?.accuracy)}</div><div class="label">正确率</div></div>
        <div class="card"><div class="value">${report.value?.summary?.interaction_count ?? 0}</div><div class="label">交互次数</div></div>
      </div>
      <h2>掌握度明细</h2>
      <table>
        <thead><tr><th>知识点</th><th>掌握度</th><th>阈值</th></tr></thead>
        <tbody>${items}</tbody>
      </table>
    </body>
    </html>
  `
  printWindow.document.write(html)
  printWindow.document.close()
  printWindow.focus()
  printWindow.print()
}
</script>

<template>
  <div class="report">
    <div v-if="loading" class="status skeleton-wrapper">
      <div class="skeleton title"></div>
      <div class="skeleton-grid">
        <div v-for="n in 6" :key="n" class="skeleton card"></div>
      </div>
    </div>

    <div v-else-if="error" class="status error">
      <p>{{ error }}</p>
      <button class="retry-btn" type="button" @click="loadReport">重试</button>
    </div>

    <template v-else-if="report">
      <header class="header">
        <div class="header-main">
          <h1 class="title">{{ report.course_title || '学习报告' }}</h1>
          <p class="subtitle">生成时间：{{ formatDate(report.generated_at) }}</p>
        </div>
        <div class="header-actions">
          <button class="action-btn" type="button" @click="goToRoom">继续学习</button>
          <button class="action-btn secondary" type="button" @click="exportReport">导出报告</button>
        </div>
      </header>

      <section class="overview">
        <div class="ring-card">
          <div class="ring" :style="{ '--pct': normalizePercent(report.summary?.average_mastery) }">
            <span class="ring-value">{{ formatPercent(report.summary?.average_mastery) }}</span>
          </div>
          <p class="ring-label">平均掌握度</p>
        </div>
        <div class="summary-grid">
          <div class="card">
            <p class="label">已掌握 / 总节点</p>
            <p class="value">{{ report.summary?.mastered_nodes ?? 0 }} / {{ report.summary?.total_nodes ?? 0 }}</p>
          </div>
          <div class="card">
            <p class="label">正确率</p>
            <p class="value">{{ formatPercent(report.summary?.accuracy) }}</p>
          </div>
          <div class="card">
            <p class="label">观看时长</p>
            <p class="value">{{ report.summary?.total_watch_minutes ?? 0 }} 分钟</p>
          </div>
          <div class="card">
            <p class="label">交互次数</p>
            <p class="value">{{ report.summary?.interaction_count ?? 0 }}</p>
          </div>
          <div class="card">
            <p class="label">近 7 天活跃</p>
            <p class="value">{{ report.summary?.recent_7d_interactions ?? 0 }}</p>
          </div>
          <div class="card">
            <p class="label">求助次数</p>
            <p class="value">{{ report.summary?.total_help_count ?? 0 }}</p>
          </div>
        </div>
      </section>

      <section class="section">
        <h2 class="section-title">学习活跃度热力图（近 30 天）</h2>
        <div v-if="timelineLoading" class="timeline-loading">加载时序数据…</div>
        <div v-else-if="timelineError" class="timeline-error">{{ timelineError }}</div>
        <div v-else-if="heatmapData.length" class="heatmap">
          <div
            v-for="day in heatmapData"
            :key="day.date"
            class="heatmap-cell"
            :style="{ background: heatmapColor(day.count) }"
            :title="`${day.date}：${day.count} 次交互，观看 ${Math.round(day.watch_minutes)} 分钟`"
          >
            <span class="heatmap-date">{{ formatShortDate(day.date) }}</span>
            <span class="heatmap-count">{{ day.count }}</span>
          </div>
        </div>
        <p v-else class="empty">暂无活跃度数据</p>
        <!-- PRD 要求"视频时间轴上的停留与回看分布"，当前日历热力图展示的是日活；
             视频时间轴热力图待后端 timeline.video_heatmap 支持后在此展示。 -->
        <p v-if="!videoHeatmap.length" class="heatmap-hint">
          视频时间轴停留与回看分布将在后端支持后展示。
        </p>
      </section>

      <section v-if="videoHeatmap.length" class="section">
        <h2 class="section-title">视频观看热力图（时间轴停留分布）</h2>
        <div class="heatmap video-heatmap">
          <div
            v-for="(seg, idx) in videoHeatmap"
            :key="seg.start ?? seg.time ?? idx"
            class="heatmap-cell"
            :style="{ background: videoHeatmapColor(seg.count ?? seg.value ?? 0) }"
            :title="`${seg.start ?? seg.time ?? ''}：${seg.count ?? seg.value ?? 0} 次停留/回看`"
          >
            <span class="heatmap-count">{{ seg.count ?? seg.value ?? 0 }}</span>
          </div>
        </div>
      </section>

      <section v-if="questionDistributionData" class="section">
        <h2 class="section-title">提问类型分布</h2>
        <div class="mastery-chart-wrapper">
          <Pie :data="questionDistributionData" :options="questionDistributionOptions" />
        </div>
      </section>

      <section class="section">
        <h2 class="section-title">掌握度曲线</h2>
        <div v-if="masteryChartData" class="mastery-chart-wrapper">
          <Line :data="masteryChartData" :options="masteryChartOptions" />
        </div>
        <p v-else class="empty">暂无掌握度曲线数据</p>
      </section>

      <section class="section">
        <h2 class="section-title">掌握度雷达</h2>
        <MasteryRadar :items="report.mastery_items" />
      </section>

      <section class="section">
        <h2 class="section-title">掌握度分布</h2>
        <div class="distribution">
          <div
            v-for="item in (report.mastery_items || []).slice(0, 10)"
            :key="item.node_id || item.name"
            class="dist-row"
          >
            <span class="dist-name">{{ item.name }}</span>
            <div class="dist-bar-bg">
              <div
                class="dist-bar-fill"
                :style="{ width: formatPercent(item.p_known) }"
                :class="{ mastered: normalizePercent(item.p_known) >= normalizePercent(item.threshold) }"
              />
            </div>
            <span class="dist-value">{{ formatPercent(item.p_known) }}</span>
          </div>
        </div>
      </section>

      <div class="two-col">
        <section class="section">
          <h2 class="section-title">薄弱知识点 Top10</h2>
          <ul v-if="report.weak_nodes?.length" class="weak-list">
            <li v-for="node in report.weak_nodes" :key="node.node_id || node.name" class="weak-item">
              <span class="weak-name">{{ node.name }}</span>
              <span class="weak-gap">差距 {{ formatPercent(node.gap) }}</span>
            </li>
          </ul>
          <p v-else class="empty">暂无薄弱知识点，继续保持！</p>
        </section>

        <section class="section">
          <h2 class="section-title">强项 Top3</h2>
          <ul v-if="masteredItems.length" class="strength-list">
            <li v-for="item in masteredItems" :key="item.node_id || item.name" class="strength-item">
              <span class="strength-name">{{ item.name }}</span>
              <span class="strength-value">{{ formatPercent(item.p_known) }}</span>
            </li>
          </ul>
          <p v-else class="empty">还没有掌握的知识点，继续加油！</p>
        </section>
      </div>

      <section class="section tips">
        <h2 class="section-title">下一步行动</h2>
        <ul class="tip-list">
          <li
            v-for="(action, idx) in nextActions"
            :key="idx"
            class="tip-item"
            :class="{ primary: action.primary }"
          >
            <span class="tip-icon">{{ action.icon }}</span>
            <span class="tip-text">{{ action.text }}</span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.report {
  max-width: 56rem;
  margin: 0 auto;
  padding: 1rem;
}

.status {
  text-align: center;
  padding: 2rem;
  color: var(--tl-text-muted);
}

.status.error {
  color: #b91c1c;
  background: #fee2e2;
  border-radius: var(--tl-radius);
}

.retry-btn {
  margin-top: 0.75rem;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: var(--tl-radius-sm);
  background: var(--tl-primary);
  color: var(--tl-surface);
  cursor: pointer;
}

.skeleton-wrapper {
  padding: 1rem 0;
}

.skeleton {
  background: linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 50%, #f3f4f6 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: var(--tl-radius);
}

.skeleton.title {
  height: 2rem;
  width: 60%;
  margin-bottom: 1rem;
}

.skeleton-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
  gap: 0.75rem;
}

.skeleton.card {
  height: 5rem;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.title {
  margin: 0;
  font-size: 1.375rem;
  font-weight: 700;
  color: var(--tl-text);
}

.subtitle {
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
  color: var(--tl-text-muted);
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.action-btn {
  padding: 0.5rem 1rem;
  border: 1px solid var(--tl-primary);
  border-radius: var(--tl-radius-sm);
  background: var(--tl-primary);
  color: var(--tl-surface);
  font-size: 0.875rem;
  cursor: pointer;
}

.action-btn.secondary {
  background: var(--tl-surface);
  color: var(--tl-primary);
}

.overview {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 1rem;
  align-items: stretch;
  margin-bottom: 1.25rem;
}

.ring-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius);
  min-width: 9rem;
}

.ring {
  width: 7rem;
  height: 7rem;
  border-radius: 50%;
  background: conic-gradient(
    var(--tl-primary) calc(var(--pct, 0) * 1%),
    #e5e7eb 0
  );
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.ring::before {
  content: '';
  position: absolute;
  width: 5.5rem;
  height: 5.5rem;
  border-radius: 50%;
  background: var(--tl-surface);
}

.ring-value {
  position: relative;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--tl-primary);
}

.ring-label {
  margin: 0.75rem 0 0;
  font-size: 0.8125rem;
  color: var(--tl-text-muted);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
  gap: 0.75rem;
}

.card {
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius);
  padding: 0.875rem;
  text-align: center;
}

.label {
  margin: 0 0 0.375rem;
  font-size: 0.8125rem;
  color: var(--tl-text-muted);
}

.value {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--tl-text);
}

.section {
  margin-bottom: 1.25rem;
}

.section-title {
  margin: 0 0 0.75rem;
  font-size: 1.0625rem;
  font-weight: 600;
  color: var(--tl-text);
}

.distribution {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.dist-row {
  display: grid;
  grid-template-columns: 7rem 1fr 3rem;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.875rem;
}

.dist-name {
  color: var(--tl-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dist-bar-bg {
  height: 0.625rem;
  background: #e5e7eb;
  border-radius: 9999px;
  overflow: hidden;
}

.dist-bar-fill {
  height: 100%;
  background: var(--tl-warning);
  border-radius: 9999px;
  transition: width 0.4s ease;
}

.dist-bar-fill.mastered {
  background: var(--tl-success);
}

.dist-value {
  color: var(--tl-text-muted);
  text-align: right;
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

@media (max-width: 640px) {
  .overview {
    grid-template-columns: 1fr;
  }
  .two-col {
    grid-template-columns: 1fr;
  }
}

.weak-list,
.strength-list {
  list-style: none;
  margin: 0;
  padding: 0;
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius);
  overflow: hidden;
}

.weak-item,
.strength-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #f3f4f6;
}

.weak-item:last-child,
.strength-item:last-child {
  border-bottom: none;
}

.weak-name,
.strength-name {
  color: var(--tl-text-secondary);
  font-size: 0.9375rem;
}

.weak-gap {
  color: var(--tl-danger);
  font-size: 0.875rem;
  font-weight: 500;
}

.strength-value {
  color: var(--tl-success);
  font-size: 0.875rem;
  font-weight: 500;
}

.empty {
  color: var(--tl-text-muted);
  font-size: 0.9375rem;
  text-align: center;
  padding: 1rem;
}

.tips {
  background: #eff6ff;
  border: 1px solid #dbeafe;
  border-radius: var(--tl-radius);
  padding: 1rem;
}

.tip-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tip-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.625rem 0.75rem;
  background: var(--tl-surface);
  border-radius: var(--tl-radius-sm);
  color: var(--tl-text-secondary);
  font-size: 0.9375rem;
  line-height: 1.5;
}

.tip-item.primary {
  border-left: 3px solid var(--tl-primary);
  color: #1e40af;
}

.tip-icon {
  flex-shrink: 0;
}

.tip-text {
  flex: 1;
}

.timeline-loading,
.timeline-error {
  padding: 1rem;
  text-align: center;
  font-size: 0.9375rem;
  color: var(--tl-text-muted);
}

.timeline-error {
  color: #b91c1c;
  background: #fee2e2;
  border-radius: var(--tl-radius);
}

.heatmap {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(2.25rem, 1fr));
  gap: 0.375rem;
}

.heatmap-cell {
  aspect-ratio: 1;
  border-radius: 0.375rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 0.6875rem;
  color: #1f2937;
  min-height: 2.25rem;
}

.heatmap-date {
  font-size: 0.625rem;
  opacity: 0.8;
}

.heatmap-count {
  font-weight: 600;
}

.heatmap-hint {
  margin: 0.5rem 0 0;
  font-size: 0.8125rem;
  color: var(--tl-text-muted);
  text-align: center;
}

.mastery-chart-wrapper {
  position: relative;
  height: 16rem;
}
</style>
