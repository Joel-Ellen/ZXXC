const RICH_MARKDOWN_PATTERN = /```|~~~|^\s{0,3}#{1,6}\s|^\s{0,3}>\s|^\s*[-*+]\s|^\s*\d+\.\s|!\[[^\]]*]\([^)]+\)|\[[^\]]+]\([^)]+\)|^\s*\|.+\|/m;

export function hasRichMarkdownContent(source = "", mermaidSource = "") {
  if (mermaidSource?.trim()) {
    return true;
  }

  return RICH_MARKDOWN_PATTERN.test(source);
}

export function escapeHtml(source = "") {
  return source
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function renderPlainTextHtml(source = "") {
  const normalized = source.replace(/\r/g, "").trim();
  if (!normalized) {
    return "";
  }

  return normalized
    .split(/\n{2,}/)
    .map((paragraph) => `<p>${escapeHtml(paragraph).replace(/\n/g, "<br />")}</p>`)
    .join("");
}

function stripMarkdownSyntax(source = "") {
  return source
    .replace(/```[^\n]*\n?([\s\S]*?)```/g, (_, code = "") => code)
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/^>\s?/gm, "")
    .replace(/!\[([^\]]*)]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)]\([^)]+\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\|/g, " ");
}

export function extractTextPreview(source = "", maxChars = 180) {
  const normalized = stripMarkdownSyntax(source)
    .replace(/\r/g, "")
    .replace(/\s+/g, " ")
    .trim();

  if (!normalized) {
    return "展开后查看完整内容。";
  }

  if (normalized.length <= maxChars) {
    return normalized;
  }

  return `${normalized.slice(0, maxChars).trimEnd()}…`;
}

export function extractCodePreview(source = "", maxLines = 8) {
  const match = source.match(/```[^\n]*\n?([\s\S]*?)```/);
  const rawCode = (match?.[1] ?? source).replace(/\r/g, "").trim();

  if (!rawCode) {
    return "展开后查看完整代码示例。";
  }

  return rawCode
    .split("\n")
    .filter((line, index, lines) => line.trim() || index < lines.length - 1)
    .slice(0, maxLines)
    .join("\n");
}
