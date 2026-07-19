<template>
  <div class="mindmap-viewer">
    <div class="mindmap-header" v-if="title">
      <h3>{{ title }}</h3>
      <span class="mindmap-topic">{{ topic }}</span>
    </div>

    <div class="mindmap-canvas" ref="canvasRef">
      <VueFlow
        v-model:nodes="nodes"
        v-model:edges="edges"
        :default-viewport="{ x: 50, y: 200, zoom: 0.85 }"
        :min-zoom="0.2"
        :max-zoom="2"
        :nodes-draggable="true"
        :nodes-connectable="false"
        :elements-selectable="true"
        fit-view-on-init
        class="mindmap-flow"
      >
        <Background :gap="20" />
        <Controls position="bottom-right" />

        <!-- Custom node template -->
        <template #node-custom="nodeProps">
          <div
            class="mindmap-node"
            :class="'depth-' + (nodeProps.data.depth || 0)"
            :style="{ borderColor: nodeProps.data.color || '#1E5E4D' }"
          >
            <div class="node-label">{{ nodeProps.data.label }}</div>
            <div class="node-children-count" v-if="nodeProps.data.childrenCount > 0">
              {{ nodeProps.data.childrenCount }} 子节点
            </div>
          </div>
        </template>
      </VueFlow>
    </div>

    <!-- Mermaid code preview (collapsible) -->
    <details class="mermaid-preview" v-if="mermaidCode">
      <summary>Mermaid 源码</summary>
      <pre><code>{{ mermaidCode }}</code></pre>
    </details>

    <div class="mindmap-footer" v-if="tips">
      <small>
        <svg class="inline-block mr-1 align-text-bottom" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0018 8 6 6 0 006 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 018.91 14"/></svg>
        {{ tips }}</small>
    </div>
  </div>
</template>

<script setup>
/**
 * MindMapViewer — 思维导图可视化组件
 *
 * 接收后端 StructuredMindMap 格式的 content prop：
 *   { content_type: "structured", content_subtype: "mindmap", root: MindMapNode, mermaid_code, ... }
 *
 * 使用 @vue-flow/core 渲染为可拖拽、可缩放的节点树。
 */
import { ref, computed, watch } from 'vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

const props = defineProps({
  content: { type: Object, required: true },
})

// Convenience accessors
const title = computed(() => props.content?.title || '')
const topic = computed(() => props.content?.topic || '')
const mermaidCode = computed(() => props.content?.mermaid_code || '')
const tips = computed(() => props.content?.usage_tips || '')

const canvasRef = ref(null)

// Vue Flow reactive state
const nodes = ref([])
const edges = ref([])

// ── Color palette for different depth levels ──
const DEPTH_COLORS = [
  '#1E5E4D', // Pine Green (root)
  '#2E8C8A', // Stone Green (level 1)
  '#7FBFA6', // Celadon Green (level 2)
  '#B8D6A7', // Moss Green (level 3)
  '#C8A858', // Xiangye Yellow (level 4)
  '#5BA69E', // Teal (level 5)
]

// ── Layout constants ──
const H_SPACING = 240   // Horizontal spacing per depth level
const V_SPACING = 60     // Vertical spacing between sibling nodes

/**
 * Walk the recursive MindMapNode tree and compute positions.
 * Returns { nodes, edges } arrays ready for Vue Flow.
 */
function buildTreeLayout(root, yOffset = { current: 0 }) {
  const flowNodes = []
  const flowEdges = []
  function layoutNode(node, d, parentId = null) {
    const children = node.children || []
    const childrenCount = children.length

    // If this is a leaf, it occupies one vertical slot
    // If it has children, center it among them
    let nodeY
    if (children.length === 0) {
      nodeY = yOffset.current
      yOffset.current += V_SPACING
    } else {
      // Layout children first to know their total height
      const childStartY = yOffset.current
      for (const child of children) {
        layoutNode(child, d + 1, node.id)
      }
      const childEndY = yOffset.current
      // Center parent between first and last child
      nodeY = (childStartY + childEndY - V_SPACING) / 2
    }

    const nodeColor = DEPTH_COLORS[Math.min(d, DEPTH_COLORS.length - 1)]

    flowNodes.push({
      id: node.id,
      type: 'custom',
      position: { x: d * H_SPACING, y: nodeY },
      data: {
        label: node.label,
        depth: d,
        color: nodeColor,
        childrenCount,
      },
      draggable: true,
    })

    // Create edge from parent
    if (parentId) {
      flowEdges.push({
        id: `${parentId}->${node.id}`,
        source: parentId,
        target: node.id,
        type: 'smoothstep',
        animated: false,
        style: {
          stroke: nodeColor,
          strokeWidth: Math.max(1, 3 - d * 0.5),
        },
      })
    }

    // Recurse into children
    for (const child of children) {
      layoutNode(child, d + 1, node.id)
    }
  }

  if (root && root.label) {
    layoutNode(root, 0)
  }

  return { nodes: flowNodes, edges: flowEdges }
}

// Watch root node changes and rebuild the layout
watch(
  () => props.content?.root,
  (newRoot) => {
    if (newRoot && newRoot.label) {
      const { nodes: n, edges: e } = buildTreeLayout(newRoot, { current: 0 })
      nodes.value = n
      edges.value = e
    }
  },
  { immediate: true, deep: true }
)
</script>

<style scoped>
.mindmap-viewer {
  border: 1px solid var(--border-light, #e0e0e0);
  border-radius: var(--radius-lg, 12px);
  overflow: hidden;
  background: #fafbfc;
}

.mindmap-header {
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-light, #e0e0e0);
  background: #fff;
}
.mindmap-header h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary, #1a1a2e);
}
.mindmap-topic {
  font-size: 12px;
  color: var(--text-muted, #888);
  margin-left: 8px;
}

.mindmap-canvas {
  width: 100%;
  height: 520px;
}
.mindmap-flow {
  width: 100%;
  height: 100%;
}

/* ── Custom node styling ── */
.mindmap-node {
  background: #fff;
  border: 2px solid #1E5E4D;
  border-radius: 10px;
  padding: 10px 16px;
  min-width: 120px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  transition: box-shadow 0.2s, transform 0.2s;
  cursor: grab;
}
.mindmap-node:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.14);
  transform: translateY(-2px);
}
.mindmap-node:active {
  cursor: grabbing;
}

.node-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  line-height: 1.4;
  word-break: break-word;
}

.node-children-count {
  font-size: 10px;
  color: var(--text-muted, #999);
  margin-top: 4px;
}

/* Depth-specific styling */
.depth-0 {
  border-width: 3px;
  padding: 14px 22px;
  min-width: 150px;
}
.depth-0 .node-label {
  font-size: 15px;
}
.depth-2 .node-label,
.depth-3 .node-label {
  font-size: 12px;
}

/* ── Mermaid preview ── */
.mermaid-preview {
  border-top: 1px solid var(--border-light, #e0e0e0);
  padding: 0;
}
.mermaid-preview summary {
  padding: 10px 18px;
  font-size: 13px;
  color: var(--text-muted, #888);
  cursor: pointer;
  user-select: none;
  background: #fff;
}
.mermaid-preview summary:hover {
  color: var(--primary, #1E5E4D);
}
.mermaid-preview pre {
  margin: 0;
  padding: 14px 18px;
  background: #1e1e2e;
  color: #cdd6f4;
  font-size: 12px;
  overflow-x: auto;
  border-radius: 0 0 var(--radius-lg, 12px) var(--radius-lg, 12px);
}

/* ── Footer ── */
.mindmap-footer {
  padding: 10px 18px;
  border-top: 1px solid var(--border-light, #e0e0e0);
  background: #fff;
}
.mindmap-footer small {
  color: var(--text-muted, #888);
}
</style>
