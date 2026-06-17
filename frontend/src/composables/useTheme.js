import { ref, watch } from "vue";

const STORAGE_KEY = "eduagent-theme";
const VALID_THEMES = ["dark", "light"];

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

const theme = ref(getInitialTheme());

export function useTheme() {
  function applyTheme(next) {
    if (!VALID_THEMES.includes(next)) {
      return;
    }
    theme.value = next;
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", next);
      window.localStorage.setItem(STORAGE_KEY, next);
    }
  }

  function toggleTheme() {
    applyTheme(theme.value === "dark" ? "light" : "dark");
  }

  // Apply immediately on import (client-side)
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", theme.value);
  }

  // Keep reactive for any future changes
  watch(theme, (next) => {
    applyTheme(next);
  });

  return {
    theme,
    isDark: () => theme.value === "dark",
    isLight: () => theme.value === "light",
    setTheme: applyTheme,
    toggleTheme,
  };
}
