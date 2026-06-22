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

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend)

const props = defineProps({
  items: {
    type: Array,
    default: () => []
  }
})

const chartError = ref(false)

onErrorCaptured((err) => {
  // eslint-disable-next-line no-console
  console.warn('雷达图渲染失败，切换到文本列表', err)
  chartError.value = true
  return true
})

function normalizePercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return 0
  if (typeof value !== 'number') {
    const parsed = Number(value)
    if (Number.isNaN(parsed)) return 0
    value = parsed
  }
  // 兼容后端返回的 0-1 小数和 0-100 百分数
  if (value >= 0 && value <= 1) return Math.round(value * 100)
  return Math.round(Math.min(100, Math.max(0, value)))
}

function itemKey(item, index) {
  return item?.node_id || item?.name || `item-${index}`
}

const displayItems = computed(() => {
  const list = (props.items || [])
    .filter((item) => item && typeof item === 'object')
    .map((item, index) => ({
      ...item,
      _key: itemKey(item, index),
      pKnownPercent: normalizePercent(item.p_known ?? item.pKnownPercent),
      thresholdPercent: normalizePercent(item.threshold ?? item.thresholdPercent)
    }))
    .filter((item) => item.name)

  if (list.length <= 8) return list

  // 按紧迫度排序：未掌握且差距大的优先，然后其他
  const urgent = list
    .filter((i) => i.pKnownPercent < i.thresholdPercent)
    .sort((a, b) => a.pKnownPercent - b.pKnownPercent)
  const rest = list
    .filter((i) => i.pKnownPercent >= i.thresholdPercent)
    .sort((a, b) => a.pKnownPercent - b.pKnownPercent)

  return urgent.concat(rest).slice(0, 8)
})

const chartData = computed(() => {
  return {
    labels: displayItems.value.map((i) => i.name),
    datasets: [
      {
        label: '掌握度',
        data: displayItems.value.map((i) => i.pKnownPercent),
        backgroundColor: 'rgba(37, 99, 235, 0.2)',
        borderColor: '#2563eb',
        pointBackgroundColor: '#2563eb',
        pointBorderColor: '#ffffff',
        pointHoverBackgroundColor: '#ffffff',
        pointHoverBorderColor: '#2563eb',
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

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
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
    <h3 class="title">掌握度雷达</h3>

    <div v-if="!displayItems.length" class="fallback">
      <p>暂无掌握度数据</p>
    </div>

    <div v-else-if="chartError" class="fallback-list">
      <p class="fallback-hint">图表渲染失败，已切换为文本列表</p>
      <ul>
        <li v-for="item in displayItems" :key="item._key">
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

.title {
  margin: 0 0 0.5rem;
  font-size: 0.9375rem;
  font-weight: 600;
  color: #111827;
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
