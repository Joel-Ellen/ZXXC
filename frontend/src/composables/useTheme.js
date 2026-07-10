import { ref, watch } from "vue";

const STORAGE_KEY = "eduagent-theme";
const VALID_THEMES = ["dark", "light"];
const theme = ref("dark");
let isThemeInitialized = false;

function getStoredTheme() {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && VALID_THEMES.includes(stored)) {
      return stored;
    }
  } catch {
    return null;
  }

  return null;
}

function getSystemTheme() {
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  return "dark";
}

function normalizeTheme(next) {
  return VALID_THEMES.includes(next) ? next : null;
}

function getInitialTheme() {
  const stored = getStoredTheme();
  if (stored) {
    return stored;
  }

  return getSystemTheme();
}

function persistTheme(next) {
  const normalized = normalizeTheme(next) || "dark";

  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", normalized);
    document.documentElement.style.removeProperty("color-scheme");
  }

  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, normalized);
    } catch {
      // Storage can be unavailable in private or embedded browsing contexts.
    }
  }
}

export function initTheme() {
  if (isThemeInitialized) {
    return;
  }

  theme.value = getInitialTheme();
  persistTheme(theme.value);

  watch(theme, (next) => {
    persistTheme(next);
  });

  isThemeInitialized = true;
}

export function useTheme() {
  initTheme();

  function applyTheme(next) {
    const normalized = normalizeTheme(next);
    if (!normalized) {
      return;
    }

    if (theme.value === normalized) {
      persistTheme(normalized);
      return;
    }

    theme.value = normalized;
  }

  function toggleTheme() {
    applyTheme(theme.value === "dark" ? "light" : "dark");
  }

  return {
    theme,
    isDark: () => theme.value === "dark",
    isLight: () => theme.value === "light",
    setTheme: applyTheme,
    toggleTheme,
  };
}
