let markdownRendererPromise = null;

async function loadMarkdownRenderer() {
  if (!markdownRendererPromise) {
    markdownRendererPromise = Promise.all([
      import("dompurify"),
      import("marked"),
    ]).then(([domPurifyModule, markedModule]) => {
      const DOMPurify = domPurifyModule.default;
      const marked = markedModule.marked ?? markedModule.default ?? markedModule;

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
