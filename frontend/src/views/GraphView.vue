<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import cytoscape from 'cytoscape'
import {
  getCourseGraph,
  createKnowledgeNode,
  updateKnowledgeNode,
  deleteKnowledgeNode,
  createKnowledgeEdge,
  deleteKnowledgeEdge
} from '../api/graph.js'

const props = defineProps({
  courseId: { type: String, required: true }
})

const container = ref(null)
let cy = null

const graph = ref(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const successMsg = ref('')

const selectedNode = ref(null)
const selectedEdge = ref(null)
const panelMode = ref('none') // 'none' | 'node' | 'edge'

const nodeForm = ref({
  id: '',
  name: '',
  description: '',
  threshold: 0.8
})

const edgeForm = ref({
  source_id: '',
  target_id: '',
  relation: 'prerequisite'
})

onMounted(() => {
  loadGraph()
})

onUnmounted(() => {
  if (cy) {
    cy.destroy()
    cy = null
  }
})

watch(() => props.courseId, loadGraph)

async function loadGraph() {
  loading.value = true
  error.value = ''
  successMsg.value = ''
  try {
    graph.value = await getCourseGraph(props.courseId)
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
        description: node.description || '',
        threshold: node.threshold ?? 0.8
      }
    })
  })

  edges.forEach((edge) => {
    elements.push({
      data: {
        id: String(edge.id),
        source: String(edge.from || edge.source),
        target: String(edge.to || edge.target),
        relation: edge.relation || 'prerequisite'
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
          'curve-style': 'bezier',
          'label': 'data(relation)',
          'font-size': '10px',
          'color': '#6b7280'
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
    selectedNode.value = e.target.data()
    selectedEdge.value = null
    panelMode.value = 'none'
  })

  cy.on('tap', 'edge', (e) => {
    selectedEdge.value = e.target.data()
    selectedNode.value = null
    panelMode.value = 'none'
  })

  cy.on('tap', (e) => {
    if (e.target === cy) {
      selectedNode.value = null
      selectedEdge.value = null
      panelMode.value = 'none'
    }
  })
}

function startCreateNode() {
  selectedNode.value = null
  if (cy) cy.$(':selected').unselect()
  nodeForm.value = { id: '', name: '', description: '', threshold: 0.8 }
  panelMode.value = 'node'
}

function startEditNode() {
  if (!selectedNode.value) return
  nodeForm.value = {
    id: selectedNode.value.id,
    name: selectedNode.value.label || '',
    description: selectedNode.value.description || '',
    threshold: selectedNode.value.threshold ?? 0.8
  }
  panelMode.value = 'node'
}

function startCreateEdge() {
  selectedEdge.value = null
  if (cy) cy.$(':selected').unselect()
  edgeForm.value = { source_id: selectedNode.value?.id || '', target_id: '', relation: 'prerequisite' }
  panelMode.value = 'edge'
}

function cancelPanel() {
  panelMode.value = 'none'
}

async function saveNode() {
  saving.value = true
  error.value = ''
  successMsg.value = ''
  try {
    const payload = {
      name: nodeForm.value.name.trim(),
      description: nodeForm.value.description.trim() || undefined,
      threshold: Number(nodeForm.value.threshold)
    }
    if (nodeForm.value.id) {
      await updateKnowledgeNode(nodeForm.value.id, payload)
    } else {
      await createKnowledgeNode(props.courseId, payload)
    }
    panelMode.value = 'none'
    successMsg.value = '知识点已保存'
    await loadGraph()
  } catch (err) {
    error.value = err.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function removeNode() {
  if (!selectedNode.value) return
  if (!confirm(`确定删除知识点「${selectedNode.value.label}」吗？相关掌握度记录也会被清除。`)) return
  saving.value = true
  error.value = ''
  try {
    await deleteKnowledgeNode(selectedNode.value.id)
    selectedNode.value = null
    panelMode.value = 'none'
    successMsg.value = '知识点已删除'
    await loadGraph()
  } catch (err) {
    error.value = err.message || '删除失败'
  } finally {
    saving.value = false
  }
}

async function saveEdge() {
  saving.value = true
  error.value = ''
  successMsg.value = ''
  try {
    await createKnowledgeEdge(props.courseId, {
      source_id: edgeForm.value.source_id,
      target_id: edgeForm.value.target_id,
      relation: edgeForm.value.relation || 'prerequisite'
    })
    panelMode.value = 'none'
    successMsg.value = '先修关系已添加'
    await loadGraph()
  } catch (err) {
    error.value = err.message || '添加边失败'
  } finally {
    saving.value = false
  }
}

async function removeEdge() {
  if (!selectedEdge.value) return
  if (!confirm('确定删除这条先修关系吗？')) return
  saving.value = true
  error.value = ''
  try {
    await deleteKnowledgeEdge(selectedEdge.value.id)
    selectedEdge.value = null
    panelMode.value = 'none'
    successMsg.value = '先修关系已删除'
    await loadGraph()
  } catch (err) {
    error.value = err.message || '删除失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="graph">
    <div class="header">
      <h2 class="page-title">知识图谱 · 编辑模式</h2>
      <div class="toolbar">
        <button class="tool-btn primary" type="button" @click="startCreateNode">+ 添加节点</button>
        <button class="tool-btn" type="button" :disabled="!selectedNode" @click="startEditNode">编辑节点</button>
        <button class="tool-btn danger" type="button" :disabled="!selectedNode" @click="removeNode">删除节点</button>
        <button class="tool-btn" type="button" :disabled="!graph?.nodes?.length" @click="startCreateEdge">添加先修边</button>
        <button class="tool-btn danger" type="button" :disabled="!selectedEdge" @click="removeEdge">删除选中边</button>
        <button class="tool-btn" type="button" @click="loadGraph">刷新</button>
      </div>
    </div>

    <div v-if="loading" class="status">正在展开知识图谱…</div>
    <div v-if="error" class="status error">{{ error }}</div>
    <div v-if="successMsg" class="status success">{{ successMsg }}</div>

    <div ref="container" class="graph-container" />

    <div v-if="panelMode === 'node'" class="editor-panel">
      <h3 class="panel-title">{{ nodeForm.id ? '编辑知识点' : '添加知识点' }}</h3>
      <label class="field">
        <span class="field-label">名称</span>
        <input v-model="nodeForm.name" class="field-input" type="text" />
      </label>
      <label class="field">
        <span class="field-label">描述</span>
        <textarea v-model="nodeForm.description" class="field-input" rows="2" />
      </label>
      <label class="field">
        <span class="field-label">掌握阈值（0-1）</span>
        <input v-model="nodeForm.threshold" class="field-input" type="number" min="0" max="1" step="0.05" />
      </label>
      <div class="panel-actions">
        <button class="submit-btn" type="button" :disabled="saving" @click="saveNode">
          {{ saving ? '保存中…' : '保存' }}
        </button>
        <button class="cancel-btn" type="button" @click="cancelPanel">取消</button>
      </div>
    </div>

    <div v-else-if="panelMode === 'edge'" class="editor-panel">
      <h3 class="panel-title">添加先修关系</h3>
      <label class="field">
        <span class="field-label">起点（先修）</span>
        <select v-model="edgeForm.source_id" class="field-input">
          <option value="">请选择</option>
          <option v-for="node in graph?.nodes" :key="node.id" :value="node.id">{{ node.name }}</option>
        </select>
      </label>
      <label class="field">
        <span class="field-label">终点（后学）</span>
        <select v-model="edgeForm.target_id" class="field-input">
          <option value="">请选择</option>
          <option v-for="node in graph?.nodes" :key="node.id" :value="node.id">{{ node.name }}</option>
        </select>
      </label>
      <label class="field">
        <span class="field-label">关系</span>
        <input v-model="edgeForm.relation" class="field-input" type="text" />
      </label>
      <div class="panel-actions">
        <button class="submit-btn" type="button" :disabled="saving" @click="saveEdge">
          {{ saving ? '保存中…' : '保存' }}
        </button>
        <button class="cancel-btn" type="button" @click="cancelPanel">取消</button>
      </div>
    </div>

    <div v-else-if="selectedNode" class="node-info">
      <h3 class="node-name">{{ selectedNode.label }}</h3>
      <p class="node-desc">{{ selectedNode.description || '这个知识点还没有描述' }}</p>
      <p class="node-meta">掌握阈值：{{ selectedNode.threshold ?? 0.8 }}</p>
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

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.75rem;
}

.page-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.toolbar {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.tool-btn {
  padding: 0.5rem 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  background: #ffffff;
  font-size: 0.875rem;
  cursor: pointer;
}

.tool-btn:disabled {
  color: #9ca3af;
  cursor: not-allowed;
}

.tool-btn.primary {
  background: #2563eb;
  border-color: #2563eb;
  color: #ffffff;
}

.tool-btn.danger {
  color: #b91c1c;
  border-color: #fecaca;
}

.status {
  flex-shrink: 0;
  padding: 0.75rem;
  text-align: center;
  color: #6b7280;
  margin-bottom: 0.5rem;
  border-radius: 0.5rem;
}

.status.error {
  color: #b91c1c;
  background: #fee2e2;
}

.status.success {
  color: #166534;
  background: #dcfce7;
}

.graph-container {
  flex: 1;
  min-height: 0;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
}

.editor-panel {
  flex-shrink: 0;
  margin-top: 0.75rem;
  padding: 0.875rem;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.panel-title {
  margin: 0 0 0.25rem;
  font-size: 1rem;
  font-weight: 600;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.field-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: #374151;
}

.field-input {
  padding: 0.5rem 0.625rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  font-size: 0.9375rem;
}

.panel-actions {
  display: flex;
  gap: 0.5rem;
}

.submit-btn {
  padding: 0.5rem 0.875rem;
  border: none;
  border-radius: 0.375rem;
  background: #2563eb;
  color: #ffffff;
  font-size: 0.875rem;
  cursor: pointer;
}

.submit-btn:disabled {
  background: #93c5fd;
}

.cancel-btn {
  padding: 0.5rem 0.875rem;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  background: #ffffff;
  font-size: 0.875rem;
  cursor: pointer;
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

.node-meta {
  margin: 0.375rem 0 0;
  font-size: 0.8125rem;
  color: #6b7280;
}
</style>
