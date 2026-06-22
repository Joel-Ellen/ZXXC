<template>
  <div class="space-y-4">
    <div class="markdown-body" v-html="html" />
    <div
      v-if="mermaidSource"
      ref="mermaidRoot"
      class="glass-panel overflow-hidden rounded-2xl p-4"
    />
  </div>
</template>

<script setup>
import { ref, watch } from "vue";
import { useTheme } from "../composables/useTheme.js";
import { hasRichMarkdownContent, renderPlainTextHtml } from "../utils/markdownPreview.js";

const props = defineProps({
  content: { type: String, default: "" },
  mermaidSource: { type: String, default: "" },
});

const { theme } = useTheme();
const mermaidRoot = ref(null);
const html = ref("");

let markdownRuntimePromise = null;
let mermaidRuntimePromise = null;

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
  if (!props.mermaidSource || !mermaidRoot.value) {
    return;
  }

  const { renderMermaidDiagram } = await loadMermaidRuntime();
  await renderMermaidDiagram({
    source: props.mermaidSource,
    element: mermaidRoot.value,
    isLight: theme.value === "light",
  });
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
</script>
