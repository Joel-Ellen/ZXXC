export const CODE_LANGUAGE = "c";
export const CODE_LANGUAGE_LABEL = "C";

// Code examples are intentionally limited to C across the learner-facing
// practice and presentation surfaces. Keep this normalization at the edge so
// stale cached cards cannot change the editor or execution contract.
export function normalizeCodeLanguage(_value) {
  return CODE_LANGUAGE;
}

export function resolveStructuredPayload(card) {
  const direct = card?.structured_payload;
  if (
    direct
    && typeof direct === "object"
    && !Array.isArray(direct)
    && Object.keys(direct).length
  ) {
    return direct;
  }

  const metadata = card?.metadata;
  if (metadata && typeof metadata === "object" && !Array.isArray(metadata)) {
    const nested = metadata.structured_payload;
    if (
      nested
      && typeof nested === "object"
      && !Array.isArray(nested)
      && Object.keys(nested).length
    ) {
      return nested;
    }
    if (Object.keys(metadata).length) return metadata;
  }

  return direct && typeof direct === "object" && !Array.isArray(direct) ? direct : {};
}

const CODE_FENCE_RE = /```([A-Za-z0-9_+.-]*)\s*\r?\n([\s\S]*?)```/g;

function isCDeclaredLanguage(value) {
  const language = String(value || "").trim().toLowerCase();
  return !language || language === "c" || language === "c11";
}

function looksLikeCSource(value) {
  const source = String(value || "").trim();
  if (!source) return false;
  if (/^\s*(?:def|class|import|from)\b|\b(?:print|None|True|False)\s*[(:]/m.test(source)) {
    return false;
  }
  return /#\s*include\b|\b(?:void|int|char|size_t|struct|enum|typedef)\s+[A-Za-z_]\w*|[;{}]/.test(source);
}

function extractCFromMarkdown(markdown) {
  const source = String(markdown || "");
  const blocks = [...source.matchAll(CODE_FENCE_RE)];
  if (blocks.length) {
    const block = blocks.find(
      (match) => isCDeclaredLanguage(match[1]) && looksLikeCSource(match[2]),
    );
    return block ? block[2].trim() : "";
  }
  return looksLikeCSource(source) ? source.trim() : "";
}

export function extractCCode(card) {
  if (!card || typeof card !== "object") return "";
  const payload = resolveStructuredPayload(card);
  if (!isCDeclaredLanguage(payload.language)) return "";
  if (typeof payload.code === "string" && looksLikeCSource(payload.code)) {
    return payload.code.trim();
  }
  return extractCFromMarkdown(card.body_markdown || card.content || "");
}

// Retained for callers that need a neutral C editing scaffold. It deliberately
// omits main(): executable exercises are linked against a server-owned harness.
export const DEFAULT_C_STARTER_CODE = `#include <stddef.h>

/* 请实现题目要求的 C 函数。 */
`;
