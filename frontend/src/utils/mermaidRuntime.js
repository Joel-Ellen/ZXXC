let mermaidModulePromise = null;
const MERMAID_RUNTIME_PATH = "__vendor/mermaid/mermaid.core.mjs";

async function loadMermaidModule() {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import(
      /* @vite-ignore */
      getMermaidRuntimeUrl()
    ).then((module) => module.default ?? module);
  }

  return mermaidModulePromise;
}

function getMermaidRuntimeUrl() {
  if (typeof window === "undefined") {
    return `/${MERMAID_RUNTIME_PATH}`;
  }

  const baseUrl = import.meta.env.BASE_URL || "/";
  return new URL(MERMAID_RUNTIME_PATH, new URL(baseUrl, window.location.origin)).href;
}

function normalizeMermaidSource(source = "") {
  return String(source)
    .replace(/^```mermaid\s*/i, "")
    .replace(/```$/i, "")
    .trim();
}

function createDiagramId(prefix = "mermaid") {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function getMermaidApi(isLight) {
  const mermaidModule = await loadMermaidModule();

  mermaidModule.initialize({
    startOnLoad: false,
    theme: isLight ? "default" : "dark",
    securityLevel: "strict",
  });

  return mermaidModule;
}

export async function renderMermaidDiagram({ source = "", element, isLight = false }) {
  const normalizedSource = normalizeMermaidSource(source);
  if (!normalizedSource || !element) {
    return;
  }

  const mermaid = await getMermaidApi(isLight);

  await nextMicrotask();
  element.innerHTML = normalizedSource;
  element.classList.add("mermaid");
  element.removeAttribute("data-processed");
  await mermaid.run({ nodes: [element] });
}

export async function renderMermaidSvg({ source = "", isLight = false, id } = {}) {
  const normalizedSource = normalizeMermaidSource(source);
  if (!normalizedSource) {
    return "";
  }

  const mermaid = await getMermaidApi(isLight);
  const diagramId = id || createDiagramId("mermaid-svg");
  const { svg } = await mermaid.render(diagramId, normalizedSource);
  return svg;
}

function nextMicrotask() {
  return Promise.resolve();
}
