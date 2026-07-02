<script setup>
import { computed, ref, onErrorCaptured } from 'vue'
import { Radar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend
} from 'chart.js'
import { normalizePercent } from '../utils/format.js'

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend)

const props = defineProps({
  items: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['node-click'])

const chartError = ref(false)
const showAll = ref(false)

onErrorCaptured((err) => {
  // eslint-disable-next-line no-console
  console.warn('雷达图渲染失败，切换到文本列表', err)
  chartError.value = true
  // Return false to stop the error from bubbling up to the ErrorBoundary,
  // otherwise the whole page is replaced by the error screen and this
  // component's own fallback list never becomes visible.
  return false
})

// 根据掌握度（0-1）为雷达节点设置颜色：绿=已掌握、橙=学习中、红=未掌握。
function pointColor(pKnown) {
  const ratio = typeof pKnown === 'number' && pKnown <= 1 ? pKnown : (pKnown || 0) / 100
  if (ratio >= 0.8) return '#22c55e' // 绿色 - 已掌握
  if (ratio >= 0.5) return '#f59e0b' // 橙色 - 学习中
  return '#ef4444' // 红色 - 未掌握
}

function itemKey(item, index) {
  return item?.node_id || item?.name || `item-${index}`
}

// 全量（已归一化、过滤）列表，供"显示全部"时使用。
const allItems = computed(() => {
  return (props.items || [])
    .filter((item) => item && typeof item === 'object')
    .map((item, index) => ({
      ...item,
      _key: itemKey(item, index),
      pKnownPercent: normalizePercent(item.p_known ?? item.pKnownPercent),
      thresholdPercent: normalizePercent(item.threshold ?? item.thresholdPercent)
    }))
    .filter((item) => item.name)
})

const displayItems = computed(() => {
  const list = allItems.value

  if (list.length <= 8 || showAll.value) return list

  // 按紧迫度排序：未掌握且差距大的优先，然后其他
  const urgent = list
    .filter((i) => i.pKnownPercent < i.thresholdPercent)
    .sort((a, b) => a.pKnownPercent - b.pKnownPercent)
  const rest = list
    .filter((i) => i.pKnownPercent >= i.thresholdPercent)
    .sort((a, b) => a.pKnownPercent - b.pKnownPercent)

  return urgent.concat(rest).slice(0, 8)
})

const hasMore = computed(() => allItems.value.length > 8)

const chartData = computed(() => {
  return {
    labels: displayItems.value.map((i) => i.name),
    datasets: [
      {
        label: '掌握度',
        data: displayItems.value.map((i) => i.pKnownPercent),
        backgroundColor: 'rgba(37, 99, 235, 0.2)',
        borderColor: '#2563eb',
        // 节点按掌握度着色：绿(已掌握)/橙(学习中)/红(未掌握)
        pointBackgroundColor: displayItems.value.map((i) => pointColor(i.p_known ?? i.pKnownPercent / 100)),
        pointBorderColor: '#ffffff',
        pointHoverBackgroundColor: '#ffffff',
        pointHoverBorderColor: '#2563eb',
        pointRadius: displayItems.value.length > 12 ? 3 : 4,
        borderWidth: 2
      },
      {
        label: '阈值',
        data: displayItems.value.map((i) => i.thresholdPercent),
        backgroundColor: 'transparent',
        borderColor: '#ef4444',
        pointBackgroundColor: '#ef4444',
        pointBorderColor: '#ffffff',
        borderWidth: 2,
        borderDash: [6, 4]
      }
    ]
  }
})

function handleChartClick(event, elements, chart) {
  if (!elements?.length) return
  const index = elements[0].index
  const item = displayItems.value[index]
  if (item) emit('node-click', item)
}

function handleItemClick(item) {
  emit('node-click', item)
}

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  onClick: handleChartClick,
  plugins: {
    legend: {
      position: 'bottom',
      labels: {
        boxWidth: 12,
        font: { size: 12 }
      }
    },
    tooltip: {
      callbacks: {
        label: (context) => `${context.dataset.label}: ${context.raw}%`
      }
    }
  },
  scales: {
    r: {
      min: 0,
      max: 100,
      ticks: {
        stepSize: 20,
        backdropColor: 'transparent',
        font: { size: 10 }
      },
      pointLabels: {
        font: { size: displayItems.value.length > 6 ? 10 : 12 },
        maxRotation: 45,
        minRotation: 0
      }
    }
  }
}))
</script>

<template>
  <div class="mastery-radar">
    <div class="radar-header">
      <h3 class="title">掌握度雷达</h3>
      <button
        v-if="hasMore"
        class="toggle-btn"
        type="button"
        @click="showAll = !showAll"
      >
        {{ showAll ? '收起' : '显示全部' }}
      </button>
    </div>

    <div v-if="!displayItems.length" class="fallback">
      <p>还没有掌握度数据，多提问几次就能看到你的进步曲线</p>
    </div>

    <div v-else-if="chartError" class="fallback-list">
      <p class="fallback-hint">图表暂时无法显示，已为你切换为文字列表</p>
      <ul>
        <li
          v-for="item in displayItems"
          :key="item._key"
          class="clickable"
          @click="handleItemClick(item)"
        >
          <span class="name">{{ item.name }}</span>
          <span class="value" :class="{ weak: item.pKnownPercent < item.thresholdPercent }">
            {{ item.pKnownPercent }}% / 阈值 {{ item.thresholdPercent }}%
          </span>
        </li>
      </ul>
    </div>

    <div v-else class="chart-wrapper" role="img" aria-label="掌握度雷达图">
      <Radar :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>

<style scoped>
.mastery-radar {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  padding: 0.75rem;
}

.radar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.title {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
  color: #111827;
}

.toggle-btn {
  padding: 0.25rem 0.625rem;
  border: 1px solid #2563eb;
  border-radius: 9999px;
  background: #ffffff;
  color: #2563eb;
  font-size: 0.75rem;
  cursor: pointer;
}

.toggle-btn:hover {
  background: #eff6ff;
}

.chart-wrapper {
  position: relative;
  height: 14rem;
}

.fallback,
.fallback-list {
  color: #6b7280;
  font-size: 0.875rem;
}

.fallback-list ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

.fallback-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.375rem 0;
  border-bottom: 1px solid #f3f4f6;
}

.fallback-list li.clickable {
  cursor: pointer;
}

.fallback-list li.clickable:hover {
  background: #f9fafb;
}

.fallback-list li:last-child {
  border-bottom: none;
}

.fallback-hint {
  margin: 0 0 0.5rem;
  color: #b45309;
}

.name {
  color: #374151;
}

.value {
  color: #2563eb;
  font-weight: 500;
}

.value.weak {
  color: #ef4444;
}
</style>
