<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import cytoscape from 'cytoscape'
import { apiFetch } from '../api/client.js'

const props = defineProps({
  courseId: { type: String, required: true }
})

const container = ref(null)
let cy = null

const graph = ref(null)
const loading = ref(false)
const error = ref('')
const selectedNode = ref(null)

onMounted(() => {
  loadGraph()
})

onUnmounted(() => {
  if (cy) {
    cy.destroy()
    cy = null
  }
})

async function loadGraph() {
  loading.value = true
  error.value = ''
  try {
    graph.value = await apiFetch(`/api/courses/${props.courseId}/graph`)
    initGraph()
  } catch (err) {
    error.value = err.message || '加载图谱失败'
  } finally {
    loading.value = false
  }
}

function initGraph() {
  if (!container.value || !graph.value) return

  const elements = []
  const nodes = graph.value.nodes || []
  const edges = graph.value.edges || []

  nodes.forEach((node, index) => {
    elements.push({
      data: {
        id: String(node.id ?? index),
        label: node.name || node.label || `节点 ${index + 1}`,
        description: node.description || ''
      }
    })
  })

  edges.forEach((edge, index) => {
    elements.push({
      data: {
        id: `edge-${index}`,
        source: String(edge.from || edge.source),
        target: String(edge.to || edge.target)
      }
    })
  })

  if (cy) {
    cy.destroy()
  }

  cy = cytoscape({
    container: container.value,
    elements,
    style: [
      {
        selector: 'node',
        style: {
          'background-color': '#2563eb',
          'label': 'data(label)',
          'color': '#1a1a1a',
          'font-size': '12px',
          'text-valign': 'bottom',
          'text-halign': 'center',
          'text-margin-y': 6,
          'width': 36,
          'height': 36,
          'overlay-padding': 6
        }
      },
      {
        selector: 'edge',
        style: {
          'width': 2,
          'line-color': '#9ca3af',
          'target-arrow-color': '#9ca3af',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier'
        }
      },
      {
        selector: ':selected',
        style: {
          'background-color': '#1d4ed8',
          'line-color': '#2563eb',
          'target-arrow-color': '#2563eb'
        }
      }
    ],
    layout: {
      name: 'cose',
      padding: 16,
      animate: false,
      componentSpacing: 60,
      nodeRepulsion: 400000,
      idealEdgeLength: 80
    }
  })

  cy.on('tap', 'node', (e) => {
    const data = e.target.data()
    selectedNode.value = data
  })

  cy.on('tap', (e) => {
    if (e.target === cy) {
      selectedNode.value = null
    }
  })
}

watch(() => props.courseId, loadGraph)
</script>

<template>
  <div class="graph">
    <h2 class="page-title">知识图谱</h2>

    <div v-if="loading" class="status">加载中…</div>
    <div v-if="error" class="status error">{{ error }}</div>

    <div ref="container" class="graph-container" />

    <div v-if="selectedNode" class="node-info">
      <h3 class="node-name">{{ selectedNode.label }}</h3>
      <p class="node-desc">{{ selectedNode.description || '暂无描述' }}</p>
    </div>
  </div>
</template>

<style scoped>
.graph {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1rem;
  max-width: 64rem;
  margin: 0 auto;
  width: 100%;
}

.page-title {
  margin: 0 0 0.75rem;
  font-size: 1.25rem;
  font-weight: 600;
  flex-shrink: 0;
}

.status {
  flex-shrink: 0;
  padding: 0.75rem;
  text-align: center;
  color: #6b7280;
}

.status.error {
  color: #b91c1c;
  background: #fee2e2;
  border-radius: 0.5rem;
}

.graph-container {
  flex: 1;
  min-height: 0;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
}

.node-info {
  flex-shrink: 0;
  margin-top: 0.75rem;
  padding: 0.875rem;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
}

.node-name {
  margin: 0 0 0.375rem;
  font-size: 1rem;
  font-weight: 600;
}

.node-desc {
  margin: 0;
  font-size: 0.875rem;
  color: #4b5563;
  line-height: 1.5;
}
</style>
