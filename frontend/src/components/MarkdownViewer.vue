<template>
  <div class="markdown-viewer">
    <div class="markdown-header" v-if="title">
      <h3>{{ title }}</h3>
      <span class="md-badge" v-if="metadata?.difficulty">{{ metadata.difficulty }}</span>
      <span class="md-badge" v-if="metadata?.course_name">{{ metadata.course_name }}</span>
    </div>

    <div
      class="markdown-body"
      v-html="htmlContent"
    />

    <div class="markdown-footer" v-if="metadata && Object.keys(metadata).length">
      <small v-if="metadata?.usage?.total_tokens">
        Tokens: {{ metadata.usage.total_tokens }}
      </small>
    </div>
  </div>
</template>

<script setup>
/**
 * MarkdownViewer — Markdown 渲染组件
 *
 * 接收 content prop：
 *   { content_type: "markdown", markdown: "# ...", title, metadata }
 *
 * 或结构化 tutor/learning_path 中：
 *   { markdown_body: "...", overview_markdown: "...", ... }
 */
import { computed } from 'vue'
import { renderMarkdown } from '../composables/useContentRenderer'

const props = defineProps({
  content: { type: Object, required: true },
})

const title = computed(() => props.content?.title || '')
const metadata = computed(() => props.content?.metadata || {})

const htmlContent = computed(() => {
  const source =
    props.content?.markdown ||
    props.content?.markdown_body ||
    props.content?.overview_markdown ||
    ''
  return renderMarkdown(source)
})
</script>

<style scoped>
.markdown-viewer {
  background: #fff;
  border: 1px solid var(--border-light, #e0e0e0);
  border-radius: var(--radius-lg, 12px);
  overflow: hidden;
}

.markdown-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-light, #e0e0e0);
  background: #fafbfc;
}
.markdown-header h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary, #1a1a2e);
}

.md-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--primary-alpha, rgba(124,179,66,0.12));
  color: var(--primary-dark, #558b2f);
}

/* ── Markdown body ── */
.markdown-body {
  padding: 20px 24px;
  font-size: 14px;
  line-height: 1.75;
  color: var(--text-primary, #1a1a2e);
}

/* Headings */
.markdown-body :deep(h1) { font-size: 24px; font-weight: 700; margin: 24px 0 12px; border-bottom: 1px solid #eee; padding-bottom: 6px; }
.markdown-body :deep(h2) { font-size: 20px; font-weight: 600; margin: 20px 0 10px; }
.markdown-body :deep(h3) { font-size: 16px; font-weight: 600; margin: 16px 0 8px; }
.markdown-body :deep(h4) { font-size: 14px; font-weight: 600; margin: 12px 0 6px; }

/* Paragraphs & lists */
.markdown-body :deep(p) { margin: 0 0 12px; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 24px; margin: 0 0 12px; }
.markdown-body :deep(li) { margin-bottom: 4px; }

/* Links */
.markdown-body :deep(a) { color: var(--primary, #7CB342); text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }

/* Blockquotes */
.markdown-body :deep(blockquote) {
  margin: 0 0 12px;
  padding: 8px 16px;
  border-left: 4px solid var(--primary, #7CB342);
  background: var(--primary-alpha, rgba(124,179,66,0.06));
  border-radius: 0 4px 4px 0;
}
.markdown-body :deep(blockquote p) { margin: 4px 0; }

/* Tables */
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
}
.markdown-body :deep(th) {
  background: #f5f5f5;
  font-weight: 600;
  padding: 8px 12px;
  border: 1px solid #ddd;
  text-align: left;
}
.markdown-body :deep(td) {
  padding: 8px 12px;
  border: 1px solid #ddd;
}

/* ── Code blocks ── */
.markdown-body :deep(pre) {
  margin: 12px 0;
  border-radius: 8px;
  overflow-x: auto;
}
.markdown-body :deep(pre code) {
  display: block;
  padding: 14px 18px;
  font-size: 13px;
  line-height: 1.55;
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
}

/* Inline code */
.markdown-body :deep(code:not(pre code)) {
  background: #f0f0f0;
  color: #e91e63;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.9em;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

/* Images */
.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 6px;
  margin: 8px 0;
}

/* Horizontal rules */
.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid #eee;
  margin: 20px 0;
}

/* ── Footer ── */
.markdown-footer {
  padding: 10px 18px;
  border-top: 1px solid var(--border-light, #e0e0e0);
  background: #fafbfc;
}
.markdown-footer small {
  color: var(--text-muted, #888);
}
</style>
