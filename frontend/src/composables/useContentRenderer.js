/**
 * useContentRenderer — 统一内容渲染调度器
 *
 * 根据后端返回的 content_type 字段自动选择渲染策略：
 *   - "markdown"   → 懒加载 Markdown 运行时
 *   - "structured" → 根据 content_subtype 路由到专用组件
 *
 * 用法：
 *   const { renderAs, markdownHtml, componentName } = useContentRenderer(content)
 *
 * 全局可用：
 *   import { renderMarkdown, renderContentToHtml, renderChatMessage } from '...'
 */

import { computed } from 'vue'

const runtime = await Promise.all([
  import('dompurify'),
  import('marked'),
])

const DOMPurify = runtime[0].default
const marked = runtime[1].marked ?? runtime[1].default ?? runtime[1]

marked.setOptions({
  breaks: true,
  gfm: true,
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
  const html = marked.parse(md)
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
  })
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
