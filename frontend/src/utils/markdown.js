import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({
  gfm: true,
  breaks: true,
});

export function renderMarkdown(source = "") {
  const html = marked.parse(source);
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
  });
}
