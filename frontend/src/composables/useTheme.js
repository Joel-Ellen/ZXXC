import { ref, watch } from "vue";

const STORAGE_KEY = "eduagent-theme";
const VALID_THEMES = ["dark", "light"];
const theme = ref("dark");
let isThemeInitialized = false;

function getInitialTheme() {
  if (typeof window === "undefined") {
    return "dark";
  }
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored && VALID_THEMES.includes(stored)) {
    return stored;
  }
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
    return "light";
  }
  return "dark";
}

function persistTheme(next) {
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", next);
  }

  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, next);
  }
}

function ensureThemeInitialized() {
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
  ensureThemeInitialized();

  function applyTheme(next) {
    if (!VALID_THEMES.includes(next)) {
      return;
    }

    if (theme.value === next) {
      persistTheme(next);
      return;
    }

    theme.value = next;
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
