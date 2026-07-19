<template>
  <article class="concept-learning" :aria-labelledby="headingId">
    <header class="concept-learning__header">
      <div class="concept-learning__intro">
        <p class="concept-learning__eyebrow">概念学习地图</p>
        <h2 :id="headingId">{{ title }}</h2>
        <p class="concept-learning__summary">{{ summary }}</p>
      </div>

      <dl class="concept-learning__stats" aria-label="概念图概览">
        <div>
          <dt>关系节点</dt>
          <dd>{{ visualNodeCount }}</dd>
        </div>
        <div>
          <dt>学习视角</dt>
          <dd>{{ activeGroups.length }}</dd>
        </div>
        <div>
          <dt>学习目标</dt>
          <dd>{{ objectives.length }}</dd>
        </div>
      </dl>
    </header>

    <section class="concept-learning__definition" aria-labelledby="concept-definition-label">
      <span id="concept-definition-label" class="concept-learning__definition-label">一句话定义</span>
      <p>{{ definition }}</p>
    </section>

    <div class="concept-learning__views" role="tablist" aria-label="概念图视图">
      <button
        v-for="view in views"
        :id="`${headingId}-${view.id}-tab`"
        :key="view.id"
        type="button"
        role="tab"
        class="concept-learning__view focus-ring"
        :class="{ 'concept-learning__view--active': activeView === view.id }"
        :aria-selected="activeView === view.id"
        :aria-controls="`${headingId}-${view.id}-panel`"
        @click="activeView = view.id"
      >
        {{ view.label }}
      </button>
    </div>

    <section
      v-if="activeView === 'map'"
      :id="`${headingId}-map-panel`"
      class="concept-learning__panel"
      role="tabpanel"
      :aria-labelledby="`${headingId}-map-tab`"
      tabindex="0"
    >
      <div class="concept-map__toolbar">
        <div class="concept-map__legend" aria-label="关系类型图例">
          <span class="concept-map__legend-label">关系类型</span>
          <span v-for="legend in legends" :key="legend.id" class="concept-map__legend-item">
            <i class="concept-map__swatch" :class="`concept-map__swatch--${legend.tone}`" aria-hidden="true" />
            {{ legend.label }}
          </span>
        </div>
        <p class="concept-map__hint">先检查条件，再追踪机制，最后用反例验证适用边界。</p>
      </div>

      <div class="concept-map__layout">
        <div class="concept-map__flow" role="group" aria-label="概念关系路径">
          <section v-if="entryGroup" class="concept-map__stage concept-map__stage--entry">
            <div class="concept-map__stage-heading">
              <span class="concept-map__stage-number">01</span>
              <div>
                <strong>{{ entryGroup.label }}</strong>
                <small>{{ entryGroup.relation }}</small>
              </div>
            </div>
            <div class="concept-map__node-row">
              <button
                v-for="node in entryGroup.nodes"
                :key="node.id"
                type="button"
                class="concept-map__node focus-ring"
                :class="[`concept-map__node--${node.tone}`, { 'concept-map__node--selected': selectedNodeId === node.id }]"
                :aria-pressed="selectedNodeId === node.id"
                :aria-label="`${node.relation}：${node.detail}`"
                @click="selectNode(node.id)"
              >
                <span class="concept-map__node-type">{{ node.kindLabel }}</span>
                <span class="concept-map__node-label">{{ node.label }}</span>
              </button>
            </div>
          </section>

          <div v-if="entryGroup" class="concept-map__connector" aria-hidden="true">
            <span>支撑</span>
          </div>

          <button
            type="button"
            class="concept-map__core focus-ring"
            :class="{ 'concept-map__core--selected': selectedNodeId === coreNode.id }"
            :aria-pressed="selectedNodeId === coreNode.id"
            :aria-label="`核心概念：${coreNode.detail}`"
            @click="selectNode(coreNode.id)"
          >
            <span class="concept-map__core-kicker">核心概念</span>
            <strong>{{ coreNode.label }}</strong>
            <span>{{ coreNode.detail }}</span>
          </button>

          <div class="concept-map__connector" aria-hidden="true">
            <span>展开关系</span>
          </div>

          <div class="concept-map__branch-grid">
            <section
              v-for="(group, index) in branchGroups"
              :key="group.id"
              class="concept-map__branch"
              :class="`concept-map__branch--${group.tone}`"
            >
              <header class="concept-map__branch-heading">
                <span class="concept-map__stage-number">{{ String(index + 2).padStart(2, '0') }}</span>
                <div>
                  <strong>{{ group.label }}</strong>
                  <small>{{ group.relation }}</small>
                </div>
              </header>
              <div class="concept-map__branch-nodes">
                <button
                  v-for="node in group.nodes"
                  :key="node.id"
                  type="button"
                  class="concept-map__node focus-ring"
                  :class="[`concept-map__node--${node.tone}`, { 'concept-map__node--selected': selectedNodeId === node.id }]"
                  :aria-pressed="selectedNodeId === node.id"
                  :aria-label="`${node.relation}：${node.detail}`"
                  @click="selectNode(node.id)"
                >
                  <span class="concept-map__node-type">{{ node.kindLabel }}</span>
                  <span class="concept-map__node-label">{{ node.label }}</span>
                </button>
              </div>
            </section>
          </div>
        </div>

        <aside class="concept-map__detail" aria-live="polite" aria-atomic="true">
          <div class="concept-map__detail-kicker">
            <i class="concept-map__swatch" :class="`concept-map__swatch--${selectedNode.tone}`" aria-hidden="true" />
            {{ selectedNode.relation }}
          </div>
          <h3>{{ selectedNode.label }}</h3>
          <p>{{ selectedNode.detail }}</p>
          <div class="concept-map__detail-action">
            <span>建议动作</span>
            <p>{{ selectedNode.action }}</p>
          </div>
          <p class="concept-map__detail-count">{{ selectedNodeIndex + 1 }} / {{ visualNodeCount }} 个节点</p>
        </aside>
      </div>
    </section>

    <section
      v-else-if="activeView === 'topology'"
      :id="`${headingId}-topology-panel`"
      class="concept-learning__panel concept-learning__topology"
      role="tabpanel"
      :aria-labelledby="`${headingId}-topology-tab`"
      tabindex="0"
    >
      <div class="concept-learning__panel-heading">
        <div>
          <p class="concept-learning__eyebrow">关系拓扑</p>
          <h3>看清哪些条件会导向哪些结果</h3>
        </div>
        <p>先沿前提追溯成立条件，再比较不同分支导向的结果与边界。</p>
      </div>
      <MarkdownContent
        v-if="mermaidSource"
        class="concept-learning__mermaid"
        :content="''"
        :mermaid-source="mermaidSource"
      />
      <div v-else class="concept-learning__empty">当前卡片还没有可渲染的关系拓扑。</div>
    </section>

    <section
      v-else
      :id="`${headingId}-outline-panel`"
      class="concept-learning__panel concept-learning__outline"
      role="tabpanel"
      :aria-labelledby="`${headingId}-outline-tab`"
      tabindex="0"
    >
      <div v-if="objectives.length" class="concept-outline__block">
        <div class="concept-learning__panel-heading">
          <div>
            <p class="concept-learning__eyebrow">学习目标</p>
            <h3>学完后能够做什么</h3>
          </div>
        </div>
        <ol class="concept-outline__objectives">
          <li v-for="(objective, index) in objectives" :key="`objective-${index}`">
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <p>{{ objective }}</p>
          </li>
        </ol>
      </div>

      <div v-if="sections.length" class="concept-outline__block">
        <div class="concept-learning__panel-heading">
          <div>
            <p class="concept-learning__eyebrow">分段理解</p>
            <h3>把概念拆成可复述的片段</h3>
          </div>
        </div>
        <div class="concept-outline__sections">
          <section v-for="(section, index) in sections" :key="`section-${index}`">
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <div>
              <h4>{{ section.heading }}</h4>
              <p>{{ section.body }}</p>
            </div>
          </section>
        </div>
      </div>

      <div class="concept-outline__lenses">
        <section v-for="lens in outlineLenses" :key="lens.id" class="concept-outline__lens">
          <div class="concept-outline__lens-heading">
            <i class="concept-map__swatch" :class="`concept-map__swatch--${lens.tone}`" aria-hidden="true" />
            <h3>{{ lens.label }}</h3>
          </div>
          <ul v-if="lens.items.length">
            <li v-for="(item, index) in lens.items" :key="`${lens.id}-${index}`">{{ item }}</li>
          </ul>
          <p v-else class="concept-learning__empty">暂无内容</p>
        </section>
      </div>
    </section>
  </article>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import MarkdownContent from "./MarkdownContent.vue";

const props = defineProps({
  card: { type: Object, required: true },
  nodeTitle: { type: String, default: "" },
});

const activeView = ref("map");
const selectedNodeId = ref("core");

const views = [
  { id: "map", label: "学习地图" },
  { id: "topology", label: "关系拓扑" },
  { id: "outline", label: "学习提纲" },
];

const legends = [
  { id: "foundation", label: "基础", tone: "info" },
  { id: "condition", label: "条件", tone: "primary" },
  { id: "process", label: "机制", tone: "success" },
  { id: "boundary", label: "边界", tone: "warning" },
  { id: "transfer", label: "迁移", tone: "secondary" },
];

const metadata = computed(() => props.card?.structured_payload || props.card?.metadata || {});

const legacyBody = computed(() => {
  const value = String(props.card?.body_markdown || props.card?.content || "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/[#*_>`]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return /[\u3400-\u9fff]/.test(value) ? value : "";
});

function listValue(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);
}

function compactText(value, limit = 72) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${Array.from(text).slice(0, limit - 1).join("")}…`;
}

const title = computed(() => metadata.value.title || props.card?.title || props.nodeTitle || "当前概念");
const summary = computed(() => metadata.value.summary || metadata.value.definition || legacyBody.value || "先建立概念之间的关系，再进入细节和练习。");
const definition = computed(() => metadata.value.definition || legacyBody.value || summary.value);
const mermaidSource = computed(() => String(metadata.value.mermaid_source || ""));
const objectives = computed(() => listValue(metadata.value.learning_objectives));
const bullets = computed(() => listValue(metadata.value.bullets));
const sections = computed(() => (Array.isArray(metadata.value.sections) ? metadata.value.sections : [])
  .filter((section) => section && String(section.heading || section.body || "").trim())
  .map((section) => ({
    heading: String(section.heading || "概念片段").trim(),
    body: String(section.body || "").trim(),
  })));

function makeNode(id, kindLabel, relation, value, tone, action) {
  const detail = String(value || "").trim();
  return {
    id,
    kindLabel,
    relation,
    tone,
    detail,
    label: compactText(detail),
    action,
  };
}

const coreNode = computed(() => makeNode(
  "core",
  "核心",
  "核心概念",
  definition.value,
  "primary",
  "不用看原文，用自己的话说出它解决什么问题，以及它依赖哪些条件。",
));

const activeGroups = computed(() => {
  const values = metadata.value;
  const prerequisiteItems = listValue(values.prerequisites).slice(0, 2);
  const constraintItems = listValue(values.constraints).slice(0, 2);
  const mechanismItems = listValue(values.mechanism).slice(0, 2);
  const applicationItems = [
    ...sections.value.slice(0, 1).map((section) => `${section.heading}：${section.body}`),
    ...bullets.value.slice(0, 1),
  ].slice(0, 2);
  const boundaryItems = listValue(values.counterexamples).slice(0, 2);
  const misconceptionItems = listValue(values.common_misconceptions).slice(0, 1);
  const transferItems = listValue(values.transfer_questions).slice(0, 1);

  // Legacy cards may predate structured payloads. These are learning prompts,
  // not domain claims, so the map remains useful without inventing facts.
  if (!prerequisiteItems.length) prerequisiteItems.push("先确认该节点依赖的基础概念");
  if (!constraintItems.length) constraintItems.push("先说清输入、状态和成立条件");
  if (!mechanismItems.length) mechanismItems.push("按步骤追踪状态变化", "检查每一步是否保持核心约束");
  if (!applicationItems.length) applicationItems.push("在一个小例子中应用当前概念");
  if (!boundaryItems.length) boundaryItems.push("当输入违反前提时，方法不再保证结果");
  if (!misconceptionItems.length) misconceptionItems.push("把操作步骤当成概念本身");
  if (!transferItems.length) transferItems.push("找一个共享相同约束的新问题");

  const groups = [
    {
      id: "foundation",
      label: "前置基础",
      relation: "需要先懂",
      tone: "info",
      nodes: prerequisiteItems.map((item, index) => makeNode(`foundation-${index}`, "基础", "需要先懂", item, "info", "先回忆这个基础概念，并说明它与当前主题的连接点。")),
    },
    {
      id: "condition",
      label: "成立条件",
      relation: "只有当",
      tone: "primary",
      nodes: constraintItems.map((item, index) => makeNode(`condition-${index}`, "条件", "只有当", item, "primary", "把这条条件改写成一个可以检查的是/否问题。")),
    },
    {
      id: "process",
      label: "运行机制",
      relation: "通过",
      tone: "success",
      nodes: mechanismItems.map((item, index) => makeNode(`process-${index}`, "机制", "通过", item, "success", "按顺序跟踪状态变化，指出每一步保持了什么不变量。")),
    },
    {
      id: "application",
      label: "典型应用",
      relation: "用来解释",
      tone: "secondary",
      nodes: applicationItems.map((item, index) => makeNode(`application-${index}`, "应用", "用来解释", item, "secondary", "找一个不同于原例的问题，判断它是否共享同一个核心约束。")),
    },
    {
      id: "boundary",
      label: "边界与反例",
      relation: "不适用于",
      tone: "warning",
      nodes: boundaryItems.map((item, index) => makeNode(`boundary-${index}`, "边界", "不适用于", item, "warning", "构造一个最小反例，说明是哪条前提被破坏了。")),
    },
    {
      id: "misconception",
      label: "易错辨析",
      relation: "不要混淆",
      tone: "tertiary",
      nodes: misconceptionItems.map((item, index) => makeNode(`misconception-${index}`, "误区", "不要混淆", item, "tertiary", "把错误说法和正确说法并排比较，并指出差异来自哪条约束。")),
    },
    {
      id: "transfer",
      label: "迁移挑战",
      relation: "迁移到",
      tone: "secondary",
      nodes: transferItems.map((item, index) => makeNode(`transfer-${index}`, "迁移", "迁移到", item, "secondary", "先预测新问题的结构，再验证它是否满足当前概念的条件。")),
    },
  ];

  return groups.filter((group) => group.nodes.length);
});

const entryGroup = computed(() => activeGroups.value.find((group) => group.id === "foundation") || null);
const branchGroups = computed(() => activeGroups.value.filter((group) => group.id !== "foundation"));
const visualNodes = computed(() => [coreNode.value, ...activeGroups.value.flatMap((group) => group.nodes)]);
const visualNodeCount = computed(() => visualNodes.value.length);
const selectedNode = computed(() => visualNodes.value.find((node) => node.id === selectedNodeId.value) || coreNode.value);
const selectedNodeIndex = computed(() => Math.max(0, visualNodes.value.findIndex((node) => node.id === selectedNode.value.id)));

const outlineLenses = computed(() => [
  { id: "constraints", label: "成立条件", tone: "primary", items: listValue(metadata.value.constraints) },
  { id: "prerequisites", label: "前置知识", tone: "info", items: listValue(metadata.value.prerequisites) },
  { id: "misconceptions", label: "常见误区", tone: "tertiary", items: listValue(metadata.value.common_misconceptions) },
  { id: "boundaries", label: "边界与反例", tone: "warning", items: listValue(metadata.value.counterexamples) },
  { id: "transfer", label: "迁移问题", tone: "secondary", items: listValue(metadata.value.transfer_questions) },
  { id: "review", label: "复习提示", tone: "success", items: listValue(metadata.value.review_prompts) },
]);

const headingId = computed(() => `concept-learning-${String(props.card?.resource_id || props.nodeTitle || "current").replace(/[^a-zA-Z0-9_-]/g, "-")}`);

function selectNode(nodeId) {
  selectedNodeId.value = nodeId;
}

watch(
  () => props.card?.resource_id,
  () => {
    activeView.value = "map";
    selectedNodeId.value = "core";
  },
);
</script>

<style scoped>
.concept-learning {
  min-width: 0;
  color: var(--text-secondary);
}

.concept-learning__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 2rem;
}

.concept-learning__intro {
  min-width: 0;
  max-width: 70ch;
}

.concept-learning__eyebrow {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1.3;
  text-transform: uppercase;
}

.concept-learning h2,
.concept-learning h3,
.concept-learning h4,
.concept-learning p {
  overflow-wrap: anywhere;
}

.concept-learning__intro h2 {
  margin: 0.35rem 0 0;
  color: var(--text-primary);
  font-size: 1.55rem;
  font-weight: 850;
  line-height: 1.2;
}

.concept-learning__summary {
  max-width: 70ch;
  margin: 0.75rem 0 0;
  color: var(--text-secondary);
  font-size: 0.95rem;
  line-height: 1.75;
}

.concept-learning__stats {
  display: flex;
  flex-shrink: 0;
  gap: 1.15rem;
  margin: 0;
}

.concept-learning__stats div {
  min-width: 4.2rem;
  padding-left: 1rem;
  border-left: 1px solid var(--border-subtle);
}

.concept-learning__stats dt {
  color: var(--text-muted);
  font-size: 0.68rem;
  font-weight: 750;
  line-height: 1.3;
}

.concept-learning__stats dd {
  margin: 0.3rem 0 0;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 800;
}

.concept-learning__definition {
  display: grid;
  grid-template-columns: minmax(6rem, 0.2fr) minmax(0, 1fr);
  gap: 1rem;
  align-items: baseline;
  margin-top: 1.5rem;
  padding: 1rem 0;
  border-block: 1px solid var(--border-subtle);
}

.concept-learning__definition-label {
  color: var(--color-primary-dark);
  font-size: 0.72rem;
  font-weight: 800;
}

.concept-learning__definition p {
  margin: 0;
  color: var(--text-primary);
  font-size: 0.95rem;
  font-weight: 650;
  line-height: 1.7;
}

.concept-learning__views {
  display: flex;
  gap: 0.25rem;
  margin-top: 1.25rem;
  border-bottom: 1px solid var(--border-subtle);
}

.concept-learning__view {
  min-height: 2.75rem;
  border-bottom: 2px solid transparent;
  padding: 0.45rem 0.9rem;
  color: var(--text-muted);
  font-size: 0.76rem;
  font-weight: 800;
  transition: color 180ms ease, border-color 180ms ease, background-color 180ms ease;
}

.concept-learning__view:hover {
  color: var(--text-primary);
  background: var(--space-elevated);
}

.concept-learning__view--active {
  border-bottom-color: var(--color-primary);
  color: var(--color-primary-dark);
}

.concept-learning__panel {
  min-width: 0;
  padding-top: 1.25rem;
  outline: none;
}

.concept-learning__panel:focus-visible {
  border-radius: var(--radius-sm);
  box-shadow: 0 0 0 3px var(--color-primary-soft);
}

.concept-map__toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.85rem;
}

.concept-map__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem 0.9rem;
  align-items: center;
}

.concept-map__legend-label {
  color: var(--text-muted);
  font-size: 0.68rem;
  font-weight: 800;
}

.concept-map__legend-item,
.concept-map__detail-kicker {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--text-muted);
  font-size: 0.68rem;
  font-weight: 750;
}

.concept-map__swatch {
  display: inline-block;
  width: 0.55rem;
  height: 0.55rem;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--color-primary);
}

.concept-map__swatch--info { background: var(--color-info); }
.concept-map__swatch--primary { background: var(--color-primary); }
.concept-map__swatch--success { background: var(--color-success); }
.concept-map__swatch--warning { background: var(--color-warning); }
.concept-map__swatch--secondary { background: var(--color-secondary); }
.concept-map__swatch--tertiary { background: var(--color-tertiary); }

.concept-map__hint {
  flex: 0 1 30ch;
  margin: 0;
  color: var(--text-muted);
  font-size: 0.72rem;
  line-height: 1.5;
  text-align: right;
}

.concept-map__layout {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(15rem, 0.75fr);
  gap: 1rem;
  align-items: start;
}

.concept-map__flow {
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--space-elevated) 58%, transparent);
  padding: clamp(0.9rem, 2vw, 1.25rem);
}

.concept-map__stage-heading,
.concept-map__branch-heading {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  margin-bottom: 0.6rem;
}

.concept-map__stage-number {
  display: inline-flex;
  width: 1.55rem;
  height: 1.55rem;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-subtle);
  border-radius: 50%;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.59rem;
  font-weight: 800;
}

.concept-map__stage-heading strong,
.concept-map__branch-heading strong {
  display: block;
  color: var(--text-primary);
  font-size: 0.78rem;
  line-height: 1.35;
}

.concept-map__stage-heading small,
.concept-map__branch-heading small {
  display: block;
  margin-top: 0.12rem;
  color: var(--text-muted);
  font-size: 0.67rem;
  line-height: 1.4;
}

.concept-map__node-row,
.concept-map__branch-nodes {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 8.5rem), 1fr));
  gap: 0.55rem;
}

.concept-map__node {
  display: flex;
  min-width: 0;
  min-height: 4.1rem;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 0.25rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--card-bg);
  padding: 0.65rem 0.72rem;
  text-align: left;
  transition: border-color 180ms ease, background-color 180ms ease, transform 180ms ease;
}

.concept-map__node:hover {
  border-color: var(--border-strong);
  background: var(--card-bg-hover);
  transform: translateY(-1px);
}

.concept-map__node--selected {
  border-color: var(--node-color, var(--color-primary));
  background: color-mix(in srgb, var(--node-color, var(--color-primary)) 10%, var(--card-bg));
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--node-color, var(--color-primary)) 18%, transparent);
}

.concept-map__node--info { --node-color: var(--color-info); }
.concept-map__node--primary { --node-color: var(--color-primary); }
.concept-map__node--success { --node-color: var(--color-success); }
.concept-map__node--warning { --node-color: var(--color-warning); }
.concept-map__node--secondary { --node-color: var(--color-secondary); }
.concept-map__node--tertiary { --node-color: var(--color-tertiary); }

.concept-map__node-type {
  color: var(--node-color, var(--text-muted));
  font-size: 0.62rem;
  font-weight: 800;
  line-height: 1.2;
}

.concept-map__node-label {
  display: -webkit-box;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 0.78rem;
  font-weight: 700;
  line-height: 1.45;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.concept-map__connector {
  position: relative;
  display: flex;
  height: 2rem;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 0.62rem;
  font-weight: 800;
}

.concept-map__connector::before {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 1px;
  background: var(--border-strong);
  content: "";
}

.concept-map__connector span {
  z-index: 1;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--space-elevated);
  padding: 0.12rem 0.45rem;
}

.concept-map__core {
  display: grid;
  width: min(100%, 25rem);
  min-height: 7.5rem;
  margin: 0 auto;
  align-content: center;
  gap: 0.38rem;
  border: 2px solid var(--color-primary);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-primary-soft) 65%, var(--card-bg));
  padding: 1rem 1.15rem;
  text-align: center;
  transition: box-shadow 180ms ease, transform 180ms ease;
}

.concept-map__core:hover,
.concept-map__core--selected {
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary) 16%, transparent);
  transform: translateY(-1px);
}

.concept-map__core-kicker {
  color: var(--color-primary-dark);
  font-size: 0.66rem;
  font-weight: 850;
}

.concept-map__core strong {
  color: var(--text-primary);
  font-size: 1rem;
  line-height: 1.35;
}

.concept-map__core > span:last-child {
  display: -webkit-box;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 0.72rem;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.concept-map__branch-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
}

.concept-map__branch {
  min-width: 0;
  border-top: 2px solid var(--branch-color, var(--color-primary));
  padding-top: 0.7rem;
}

.concept-map__branch--primary { --branch-color: var(--color-primary); }
.concept-map__branch--success { --branch-color: var(--color-success); }
.concept-map__branch--secondary { --branch-color: var(--color-secondary); }
.concept-map__branch--warning { --branch-color: var(--color-warning); }
.concept-map__branch--tertiary { --branch-color: var(--color-tertiary); }

.concept-map__detail {
  position: sticky;
  top: 0.75rem;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--card-bg);
  padding: 1rem;
}

.concept-map__detail-kicker {
  color: var(--color-primary-dark);
}

.concept-map__detail h3 {
  margin: 0.7rem 0 0;
  color: var(--text-primary);
  font-size: 1rem;
  line-height: 1.4;
}

.concept-map__detail > p {
  margin: 0.7rem 0 0;
  color: var(--text-secondary);
  font-size: 0.84rem;
  line-height: 1.75;
}

.concept-map__detail-action {
  margin-top: 1rem;
  border-top: 1px solid var(--border-subtle);
  padding-top: 0.85rem;
}

.concept-map__detail-action span {
  color: var(--text-muted);
  font-size: 0.68rem;
  font-weight: 800;
}

.concept-map__detail-action p {
  margin: 0.35rem 0 0;
  color: var(--text-primary);
  font-size: 0.78rem;
  line-height: 1.65;
}

.concept-map__detail-count {
  margin-top: 1rem !important;
  color: var(--text-muted) !important;
  font-family: var(--font-mono);
  font-size: 0.64rem !important;
}

.concept-learning__panel-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.concept-learning__panel-heading h3 {
  margin: 0.25rem 0 0;
  color: var(--text-primary);
  font-size: 1.05rem;
  line-height: 1.35;
}

.concept-learning__panel-heading > p {
  max-width: 34ch;
  margin: 0;
  color: var(--text-muted);
  font-size: 0.73rem;
  line-height: 1.6;
  text-align: right;
}

.concept-learning__topology {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--space-elevated) 55%, transparent);
  padding: clamp(0.9rem, 2vw, 1.25rem);
}

.concept-learning__mermaid {
  min-width: 0;
  overflow-x: auto;
}

.concept-learning__mermaid :deep(.glass-panel) {
  min-width: 38rem;
  border-radius: var(--radius-sm);
  background: var(--card-bg);
  padding: 0.75rem;
}

.concept-learning__empty {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.78rem;
  line-height: 1.6;
}

.concept-outline__block {
  border-bottom: 1px solid var(--border-subtle);
  padding-bottom: 1.5rem;
}

.concept-outline__block + .concept-outline__block {
  margin-top: 1.5rem;
}

.concept-outline__objectives {
  display: grid;
  gap: 0.7rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.concept-outline__objectives li {
  display: grid;
  grid-template-columns: 2rem minmax(0, 1fr);
  gap: 0.7rem;
  align-items: start;
  border-top: 1px solid var(--border-subtle);
  padding-top: 0.7rem;
}

.concept-outline__objectives li:first-child {
  border-top: 0;
  padding-top: 0;
}

.concept-outline__objectives li > span,
.concept-outline__sections > section > span {
  color: var(--color-primary-dark);
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 800;
}

.concept-outline__objectives p,
.concept-outline__sections p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.82rem;
  line-height: 1.7;
}

.concept-outline__sections {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.concept-outline__sections > section {
  display: grid;
  grid-template-columns: 2rem minmax(0, 1fr);
  gap: 0.65rem;
  border-top: 1px solid var(--border-subtle);
  padding-top: 0.7rem;
}

.concept-outline__sections h4 {
  margin: 0;
  color: var(--text-primary);
  font-size: 0.82rem;
  line-height: 1.4;
}

.concept-outline__sections p {
  margin-top: 0.3rem;
}

.concept-outline__lenses {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1.25rem;
  margin-top: 1.5rem;
}

.concept-outline__lens {
  min-width: 0;
  border-top: 2px solid var(--border-strong);
  padding-top: 0.65rem;
}

.concept-outline__lens-heading {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}

.concept-outline__lens h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 0.8rem;
  line-height: 1.4;
}

.concept-outline__lens ul {
  display: grid;
  gap: 0.45rem;
  margin: 0.65rem 0 0;
  padding-left: 1rem;
}

.concept-outline__lens li {
  color: var(--text-secondary);
  font-size: 0.76rem;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

@media (max-width: 900px) {
  .concept-map__layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .concept-map__detail {
    position: static;
  }

  .concept-outline__lenses {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .concept-learning__header,
  .concept-map__toolbar,
  .concept-learning__panel-heading {
    display: grid;
    gap: 0.75rem;
  }

  .concept-learning__stats {
    width: 100%;
    justify-content: space-between;
  }

  .concept-learning__stats div {
    flex: 1;
  }

  .concept-learning__definition {
    grid-template-columns: 1fr;
    gap: 0.35rem;
  }

  .concept-map__hint,
  .concept-learning__panel-heading > p {
    max-width: none;
    text-align: left;
  }

  .concept-map__branch-grid,
  .concept-outline__sections,
  .concept-outline__lenses {
    grid-template-columns: minmax(0, 1fr);
  }

  .concept-learning__mermaid :deep(.glass-panel) {
    min-width: 32rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .concept-learning__view,
  .concept-map__node,
  .concept-map__core {
    transition: none;
  }
}
</style>
