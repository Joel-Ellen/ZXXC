/**
 * useContentRenderer — 统一内容渲染调度器
 *
 * 根据后端返回的 content_type 字段自动选择渲染策略：
 *   - "markdown"   → marked + highlight.js 代码高亮
 *   - "structured" → 根据 content_subtype 路由到专用组件
 *
 * 用法：
 *   const { renderAs, markdownHtml, componentName } = useContentRenderer(content)
 *
 * 全局可用：
 *   import { renderMarkdown, renderContentToHtml, renderChatMessage } from '...'
 */

import { computed } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'

// ============================================================
// highlight.js — 按需注册语言（减小打包体积）
// ============================================================
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import css from 'highlight.js/lib/languages/css'
import xml from 'highlight.js/lib/languages/xml'      // HTML
import sql from 'highlight.js/lib/languages/sql'
import markdown from 'highlight.js/lib/languages/markdown'
import yaml from 'highlight.js/lib/languages/yaml'
import java from 'highlight.js/lib/languages/java'
import cpp from 'highlight.js/lib/languages/cpp'
import rust from 'highlight.js/lib/languages/rust'
import go from 'highlight.js/lib/languages/go'
import typescript from 'highlight.js/lib/languages/typescript'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('json', json)
hljs.registerLanguage('css', css)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)
hljs.registerLanguage('java', java)
hljs.registerLanguage('cpp', cpp)
hljs.registerLanguage('c++', cpp)
hljs.registerLanguage('rust', rust)
hljs.registerLanguage('go', go)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)

// ============================================================
// Configure marked with highlight.js
// ============================================================
const renderer = new marked.Renderer()

renderer.code = function ({ text, lang }) {
  // Attempt to highlight
  const language = hljs.getLanguage(lang || '') ? lang : 'plaintext'
  try {
    const highlighted = hljs.highlight(text, { language }).value
    return `<pre><code class="hljs language-${language}">${highlighted}</code></pre>`
  } catch {
    // Fallback: escape HTML and wrap anyway
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    return `<pre><code class="hljs">${escaped}</code></pre>`
  }
}

marked.setOptions({
  breaks: true,
  gfm: true,
  renderer,
})

// ============================================================
// Public API: renderMarkdown
// ============================================================

/**
 * Render a raw Markdown string to HTML with syntax highlighting.
 * Use this as the single source of truth for markdown→HTML everywhere.
 *
 * @param {string} md - Raw Markdown string
 * @returns {string} HTML string
 */
export function renderMarkdown(md) {
  if (!md) return ''
  return marked.parse(md)
}

// ============================================================
// useContentRenderer composable
// ============================================================

/**
 * @param {object} contentItem — The `content` field from API response
 * @returns {{ renderAs, contentSubtype, markdownHtml, structured, metadata, title, componentName }}
 */
export function useContentRenderer(contentItem) {
  const renderAs = computed(() => {
    if (!contentItem) return 'empty'
    return contentItem.content_type || 'unknown'
  })

  const contentSubtype = computed(() => {
    return contentItem?.content_subtype || ''
  })

  const markdownHtml = computed(() => {
    if (!contentItem) return ''
    const source =
      contentItem.markdown ||
      contentItem.markdown_body ||
      contentItem.overview_markdown ||
      ''
    return renderMarkdown(source)
  })

  const structured = computed(() => {
    if (!contentItem || contentItem.content_type !== 'structured') return null
    return contentItem
  })

  const metadata = computed(() => {
    return contentItem?.metadata || {}
  })

  const title = computed(() => {
    return contentItem?.title || ''
  })

  /**
   * Determine which Vue component to use for dynamic rendering.
   * Use with <component :is="componentName" :content="content" />
   */
  const componentName = computed(() => {
    if (renderAs.value === 'markdown') return 'MarkdownViewer'
    if (renderAs.value === 'structured') {
      const map = {
        mindmap: 'MindMapViewer',
        quiz: 'QuizViewer',
        learning_path: 'LearningPathViewer',
        tutoring: 'TutoringViewer',
        evaluation_report: 'EvaluationReportViewer',
        profile_update: 'ProfileDimensions',
        knowledge_analysis: 'KnowledgeGraphViewer',
      }
      return map[contentSubtype.value] || 'GenericStructuredViewer'
    }
    return 'RawJsonViewer'
  })

  return {
    renderAs,
    contentSubtype,
    markdownHtml,
    structured,
    metadata,
    title,
    componentName,
  }
}

// ============================================================
// Standalone helpers (non-reactive, for use outside components)
// ============================================================

/**
 * Quick-render any API content item as HTML.
 * @param {object|string} contentItem
 * @returns {string} HTML string
 */
export function renderContentToHtml(contentItem) {
  if (!contentItem) return ''
  if (typeof contentItem === 'string') return renderMarkdown(contentItem)
  const source =
    contentItem.markdown ||
    contentItem.markdown_body ||
    contentItem.overview_markdown ||
    ''
  return renderMarkdown(source)
}

/**
 * Render a chat message — used in tutoring/profile chat bubbles.
 * @param {string} text
 * @returns {string} HTML string
 */
export function renderChatMessage(text) {
  if (!text) return ''
  return renderMarkdown(text)
}
