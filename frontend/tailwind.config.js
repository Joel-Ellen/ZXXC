/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js}"],
  theme: {
    extend: {
      colors: {
        /* ── Surfaces ── */
        space: {
          bg: "var(--space-bg)",
          surface: "var(--space-surface)",
          panel: "var(--space-panel)",
          line: "var(--space-line)",
          elevated: "var(--space-elevated)",
        },
        /* ── Text ── */
        text: {
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          muted: "var(--text-muted)",
        },
        /* ── Legacy aurora accents ── */
        aurora: {
          mint: "var(--aurora-mint)",
          purple: "var(--aurora-purple)",
          crimson: "var(--aurora-crimson)",
          mintContrast: "var(--aurora-mint-contrast)",
          purpleContrast: "var(--aurora-purple-contrast)",
        },
        /* ── Semantic color system ── */
        primary: {
          DEFAULT: "var(--color-primary)",
          light: "var(--color-primary-light)",
          dark: "var(--color-primary-dark)",
          soft: "var(--color-primary-soft)",
          text: "var(--color-primary-text)",
        },
        secondary: {
          DEFAULT: "var(--color-secondary)",
          light: "var(--color-secondary-light)",
          dark: "var(--color-secondary-dark)",
          soft: "var(--color-secondary-soft)",
          text: "var(--color-secondary-text)",
        },
        tertiary: {
          DEFAULT: "var(--color-tertiary)",
          light: "var(--color-tertiary-light)",
          dark: "var(--color-tertiary-dark)",
          soft: "var(--color-tertiary-soft)",
          text: "var(--color-tertiary-text)",
        },
        success: {
          DEFAULT: "var(--color-success)",
          light: "var(--color-success-light)",
          dark: "var(--color-success-dark)",
          soft: "var(--color-success-soft)",
          text: "var(--color-success-text)",
        },
        warning: {
          DEFAULT: "var(--color-warning)",
          light: "var(--color-warning-light)",
          dark: "var(--color-warning-dark)",
          soft: "var(--color-warning-soft)",
          text: "var(--color-warning-text)",
        },
        error: {
          DEFAULT: "var(--color-error)",
          light: "var(--color-error-light)",
          dark: "var(--color-error-dark)",
          soft: "var(--color-error-soft)",
          text: "var(--color-error-text)",
        },
        info: {
          DEFAULT: "var(--color-info)",
          light: "var(--color-info-light)",
          dark: "var(--color-info-dark)",
          soft: "var(--color-info-soft)",
          text: "var(--color-info-text)",
        },
      },
      fontFamily: {
        sans: ["Inter", "PingFang SC", "HarmonyOS Sans SC", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
      boxShadow: {
        aurora: "0 0 28px rgba(124, 201, 191, 0.18)",
        glass: "var(--shadow-glass)",
        glow: "var(--shadow-glow)",
        card: "var(--shadow-card)",
        "glow-primary": "0 0 28px rgba(34, 211, 238, 0.20)",
        "glow-secondary": "0 0 28px rgba(168, 85, 247, 0.20)",
        "glow-tertiary": "0 0 28px rgba(251, 113, 133, 0.18)",
      },
      borderRadius: {
        "4xl": "2rem",
        "5xl": "2.5rem",
      },
      keyframes: {
        shimmer: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(220%)" },
        },
        pulseHalo: {
          "0%, 100%": { opacity: "0.35", transform: "scale(1)" },
          "50%": { opacity: "0.85", transform: "scale(1.08)" },
        },
        breathe: {
          "0%, 100%": { opacity: "0.45", transform: "scale(0.95)" },
          "50%": { opacity: "1", transform: "scale(1.05)" },
        },
        cardIn: {
          from: { opacity: "0", transform: "translateY(12px) scale(0.985)" },
          to: { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        slideUp: {
          from: { opacity: "0", transform: "translateY(16px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        slideInRight: {
          from: { opacity: "0", transform: "translateX(20px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        spinSlow: {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.8s linear infinite",
        halo: "pulseHalo 2.4s ease-in-out infinite",
        breathe: "breathe 2.2s ease-in-out infinite",
        cardIn: "cardIn 320ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        fadeIn: "fadeIn 300ms ease-out forwards",
        slideUp: "slideUp 400ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "slide-in-right": "slideInRight 320ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "spin-slow": "spinSlow 8s linear infinite",
      },
      backdropBlur: {
        aurora: "12px",
      },
      transitionTimingFunction: {
        snap: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};
