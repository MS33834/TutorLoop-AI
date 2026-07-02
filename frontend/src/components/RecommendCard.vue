<script setup>
import { computed } from 'vue'

const props = defineProps({
  recommendation: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['jump', 'view-node'])

const nodeName = computed(() => {
  if (typeof props.recommendation?.node === 'string') return props.recommendation.node
  return props.recommendation?.node?.name || '推荐知识点'
})

const reasonText = computed(() => {
  return props.recommendation?.reason || '系统根据你的掌握度推荐了下一步学习内容。'
})

const hasTarget = computed(() => {
  return typeof props.recommendation?.timestamp_seconds === 'number'
})

// 无视频时间戳但有知识点时，降级为"查看知识点详情"。
const hasNode = computed(() => {
  const rec = props.recommendation
  if (!rec) return false
  if (rec.node && typeof rec.node === 'object') return Boolean(rec.node.id || rec.node.name)
  return Boolean(rec.node_id || rec.node)
})

function jump() {
  if (typeof props.recommendation?.timestamp_seconds === 'number') {
    emit('jump', props.recommendation.timestamp_seconds)
  }
}

function viewNode() {
  const rec = props.recommendation
  if (!rec) return
  const node = (rec.node && typeof rec.node === 'object') ? rec.node : null
  emit('view-node', {
    node_id: node?.id || rec.node_id || null,
    name: node?.name || (typeof rec.node === 'string' ? rec.node : nodeName.value)
  })
}
</script>

<template>
  <div class="recommend-card">
    <h3 class="title">下一步推荐</h3>
    <p class="node">{{ nodeName }}</p>
    <p class="reason">{{ reasonText }}</p>
    <button
      v-if="hasTarget"
      class="jump-btn"
      type="button"
      @click="jump"
    >
      学习这个知识点
    </button>
    <button
      v-else-if="hasNode"
      class="jump-btn secondary"
      type="button"
      @click="viewNode"
    >
      查看知识点详情
    </button>
  </div>
</template>

<style scoped>
.recommend-card {
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

.node {
  margin: 0 0 0.375rem;
  font-size: 1rem;
  font-weight: 600;
  color: #2563eb;
}

.reason {
  margin: 0 0 0.75rem;
  font-size: 0.875rem;
  color: #4b5563;
  line-height: 1.5;
}

.jump-btn {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: none;
  border-radius: 0.625rem;
  background: #10b981;
  color: #ffffff;
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
}

.jump-btn:active {
  background: #059669;
}

.jump-btn.secondary {
  background: #2563eb;
}

.jump-btn.secondary:active {
  background: #1d4ed8;
}
</style>
