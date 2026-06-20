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
import { computed, nextTick, ref, watch } from "vue";
import { renderMarkdown } from "../utils/markdown";
import { useTheme } from "../composables/useTheme.js";

const props = defineProps({
  content: { type: String, default: "" },
  mermaidSource: { type: String, default: "" },
});

const { theme } = useTheme();
const mermaidRoot = ref(null);
const html = computed(() => renderMarkdown(props.content));

let mermaidModule = null;

async function renderMermaid() {
  if (!props.mermaidSource || !mermaidRoot.value) {
    return;
  }

  const isLight = theme.value === "light";

  if (!mermaidModule) {
    mermaidModule = await import("mermaid");
  }

  mermaidModule.default.initialize({
    startOnLoad: false,
    theme: isLight ? "default" : "dark",
    securityLevel: "strict",
  });

  await nextTick();
  mermaidRoot.value.innerHTML = props.mermaidSource;
  mermaidRoot.value.classList.add("mermaid");
  mermaidRoot.value.removeAttribute("data-processed");
  await mermaidModule.default.run({ nodes: [mermaidRoot.value] });
}

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
