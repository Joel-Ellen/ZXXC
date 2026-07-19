let markdownRendererPromise = null;

async function loadMarkdownRenderer() {
  if (!markdownRendererPromise) {
    markdownRendererPromise = Promise.all([
      import("dompurify"),
      import("marked"),
      import("marked-highlight"),
      import("highlight.js/lib/common"),
    ]).then(([domPurifyModule, markedModule, markedHighlightModule, hljsModule]) => {
      const DOMPurify = domPurifyModule.default;
      const { marked } = markedModule;
      const { markedHighlight } = markedHighlightModule;
      const hljs = hljsModule.default;

      marked.use(
        markedHighlight({
          langPrefix: "hljs language-",
          highlight(code, lang) {
            const language = hljs.getLanguage(lang) ? lang : "plaintext";
            return hljs.highlight(code, { language }).value;
          },
        }),
      );

      marked.setOptions({
        gfm: true,
        breaks: true,
      });

      return { DOMPurify, marked };
    });
  }

  return markdownRendererPromise;
}

export function prefetchMarkdownRuntime() {
  void loadMarkdownRenderer();
}

export async function renderMarkdownRuntime(source = "") {
  if (!source) {
    return "";
  }

  const { DOMPurify, marked } = await loadMarkdownRenderer();
  const html = await marked.parse(source);

  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
  });
}
