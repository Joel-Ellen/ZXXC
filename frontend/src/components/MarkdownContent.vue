<template>
  <div class="space-y-4">
    <div class="markdown-body" v-html="html" />
    <div
      v-if="mermaidSource"
      class="glass-panel overflow-hidden rounded-lg p-4"
    >
      <div
        ref="mermaidRoot"
        class="mermaid-canvas"
        :aria-busy="mermaidRendering"
        :aria-hidden="Boolean(mermaidError)"
      />
      <p v-if="mermaidError" class="mermaid-error" role="status">
        {{ mermaidError }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { useTheme } from "../composables/useTheme.js";
import { hasRichMarkdownContent, renderPlainTextHtml } from "../utils/markdownPreview.js";

const props = defineProps({
  content: { type: String, default: "" },
  mermaidSource: { type: String, default: "" },
});

const { theme } = useTheme();
const mermaidRoot = ref(null);
const mermaidError = ref("");
const mermaidRendering = ref(false);
const html = ref("");

let markdownRuntimePromise = null;
let mermaidRuntimePromise = null;
let mermaidRenderQueued = false;
let mermaidRenderActive = false;

function loadMarkdownRuntime() {
  if (!markdownRuntimePromise) {
    markdownRuntimePromise = import("../utils/markdownRuntime.js");
  }
  return markdownRuntimePromise;
}

function loadMermaidRuntime() {
  if (!mermaidRuntimePromise) {
    mermaidRuntimePromise = import("../utils/mermaidRuntime.js");
  }
  return mermaidRuntimePromise;
}

async function renderHtml() {
  if (!props.content) {
    html.value = "";
    return;
  }

  if (!hasRichMarkdownContent(props.content, props.mermaidSource)) {
    html.value = renderPlainTextHtml(props.content);
    return;
  }

  const { renderMarkdownRuntime } = await loadMarkdownRuntime();
  html.value = await renderMarkdownRuntime(props.content);
}

async function renderMermaid() {
  mermaidRenderQueued = true;
  if (mermaidRenderActive) {
    return;
  }

  mermaidRenderActive = true;
  mermaidRendering.value = true;

  try {
    while (mermaidRenderQueued) {
      mermaidRenderQueued = false;
      const source = props.mermaidSource;
      const element = mermaidRoot.value;
      const isLight = theme.value === "light";

      if (!source || !element) {
        continue;
      }

      mermaidError.value = "";
      try {
        const { renderMermaidDiagram } = await loadMermaidRuntime();
        await renderMermaidDiagram({ source, element, isLight });
        element.setAttribute("role", "img");
        element.setAttribute("aria-label", "概念关系图");
      } catch (_error) {
        if (!mermaidRenderQueued && source === props.mermaidSource) {
          element.replaceChildren();
          element.removeAttribute("role");
          element.removeAttribute("aria-label");
          mermaidError.value = "关系图暂时无法渲染，结构化学习内容仍可正常查看。";
        }
      }
    }
  } finally {
    mermaidRenderActive = false;
    mermaidRendering.value = false;
  }
}

watch(
  () => props.content,
  () => {
    renderHtml();
  },
  { immediate: true },
);

watch(
  () => props.mermaidSource,
  () => {
    renderMermaid();
  },
  { immediate: true },
);

watch(theme, () => {
  renderMermaid();
});

onMounted(() => {
  renderMermaid();
});
</script>

<style scoped>
.mermaid-canvas {
  min-width: 0;
}

.mermaid-error {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.78rem;
  line-height: 1.6;
  text-align: center;
}
</style>
