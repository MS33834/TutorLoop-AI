<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user.js'
import { apiFetch } from '../api/client.js'
import MasteryRadar from '../components/MasteryRadar.vue'

const props = defineProps({
  courseId: { type: String, required: true }
})

const router = useRouter()
const user = useUserStore()
const loading = ref(false)
const error = ref('')
const report = ref(null)

onMounted(() => {
  loadReport()
})

watch(() => props.courseId, () => {
  loadReport()
})

watch(() => user.userId, () => {
  loadReport()
})

async function loadReport() {
  if (!user.userId) {
    error.value = '请先设置用户身份'
    report.value = null
    return
  }
  if (!props.courseId) {
    error.value = '缺少课程 ID'
    report.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    const data = await apiFetch(
      `/api/users/${user.userId}/report?course_id=${encodeURIComponent(props.courseId)}`
    )
    report.value = data
  } catch (err) {
    error.value = err.message || '报告加载失败'
    report.value = null
  } finally {
    loading.value = false
  }
}

function formatPercent(value) {
  if (typeof value !== 'number') return '0%'
  return `${Math.round(value * 100)}%`
}

const masteredItems = computed(() => {
  if (!report.value) return []
  return report.value.mastery_items
    .filter((i) => i.p_known >= i.threshold)
    .sort((a, b) => b.p_known - a.p_known)
    .slice(0, 3)
})

const nextActions = computed(() => {
  if (!report.value) return []
  const actions = []
  const s = report.value.summary
  if (s.accuracy < 0.6) {
    actions.push({
      icon: '📘',
      text: '正确率偏低，建议先回顾基础知识，再尝试更难的问题。',
      primary: true
    })
  }
  if (s.mastery_rate < 0.5) {
    actions.push({
      icon: '🎯',
      text: '整体掌握度不足，优先完成系统推荐的薄弱知识点。',
      primary: true
    })
  }
  if (s.recent_7d_interactions === 0) {
    actions.push({
      icon: '📅',
      text: '最近 7 天没有学习记录，保持每日小步学习效果更佳。'
    })
  }
  const weakest = report.value.weak_nodes[0]
  if (weakest) {
    actions.push({
      icon: '🔍',
      text: `重点突破：${weakest.name}（差距 ${formatPercent(weakest.gap)}）`,
      primary: true
    })
  }
  actions.push({
    icon: '💬',
    text: '针对薄弱知识点多次提问与反馈，帮助 AI 更精准地调整推荐。'
  })
  return actions.slice(0, 4)
})

function goToRoom() {
  if (report.value?.course_id) {
    router.push(`/room/${report.value.course_id}`)
  }
}

function exportReport() {
  alert('导出功能即将上线，可先截图分享当前报告。')
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
          <p class="subtitle">生成时间：{{ new Date(report.generated_at).toLocaleString() }}</p>
        </div>
        <div class="header-actions">
          <button class="action-btn" type="button" @click="goToRoom">继续学习</button>
          <button class="action-btn secondary" type="button" @click="exportReport">导出报告</button>
        </div>
      </header>

      <section class="overview">
        <div class="ring-card">
          <div class="ring" :style="{ '--pct': Math.round((report.summary.average_mastery || 0) * 100) }">
            <span class="ring-value">{{ formatPercent(report.summary.average_mastery) }}</span>
          </div>
          <p class="ring-label">平均掌握度</p>
        </div>
        <div class="summary-grid">
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
          <div class="card">
            <p class="label">求助次数</p>
            <p class="value">{{ report.summary.total_help_count }}</p>
          </div>
        </div>
      </section>

      <section class="section">
        <h2 class="section-title">掌握度雷达</h2>
        <MasteryRadar :items="report.mastery_items" />
      </section>

      <section class="section">
        <h2 class="section-title">掌握度分布</h2>
        <div class="distribution">
          <div
            v-for="item in report.mastery_items.slice(0, 10)"
            :key="item.node_id"
            class="dist-row"
          >
            <span class="dist-name">{{ item.name }}</span>
            <div class="dist-bar-bg">
              <div
                class="dist-bar-fill"
                :style="{ width: formatPercent(item.p_known) }"
                :class="{ mastered: item.p_known >= item.threshold }"
              />
            </div>
            <span class="dist-value">{{ formatPercent(item.p_known) }}</span>
          </div>
        </div>
      </section>

      <div class="two-col">
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

        <section class="section">
          <h2 class="section-title">强项 Top3</h2>
          <ul v-if="masteredItems.length" class="strength-list">
            <li v-for="item in masteredItems" :key="item.node_id" class="strength-item">
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
</style>
