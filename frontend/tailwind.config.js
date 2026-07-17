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
        /* ── Learning-type semantic colors ── */
        learning: {
          concept: "var(--learning-concept)",
          conceptSoft: "var(--learning-concept-soft)",
          conceptDark: "var(--learning-concept-dark)",
          code: "var(--learning-code)",
          codeSoft: "var(--learning-code-soft)",
          codeDark: "var(--learning-code-dark)",
          practice: "var(--learning-practice)",
          practiceSoft: "var(--learning-practice-soft)",
          practiceDark: "var(--learning-practice-dark)",
          quiz: "var(--learning-quiz)",
          quizSoft: "var(--learning-quiz-soft)",
          quizDark: "var(--learning-quiz-dark)",
          video: "var(--learning-video)",
          videoSoft: "var(--learning-video-soft)",
          videoDark: "var(--learning-video-dark)",
          home: "var(--learning-home)",
          homeSoft: "var(--learning-home-soft)",
          homeDark: "var(--learning-home-dark)",
          path: "var(--learning-path)",
          pathSoft: "var(--learning-path-soft)",
          all: "var(--learning-all)",
          allSoft: "var(--learning-all-soft)",
        },
      },
      fontFamily: {
        sans: ["Inter", "PingFang SC", "HarmonyOS Sans SC", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
      boxShadow: {
        aurora: "0 0 28px rgba(184, 214, 167, 0.14)",
        glass: "var(--shadow-glass)",
        glow: "var(--shadow-glow)",
        card: "var(--shadow-card)",
        "glow-primary": "0 0 28px rgba(30, 94, 77, 0.18)",
        "glow-secondary": "0 0 28px rgba(230, 215, 177, 0.20)",
        "glow-tertiary": "0 0 28px rgba(127, 191, 166, 0.14)",
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
          from: { opacity: "0", transform: "translateY(24px) scale(0.96)", filter: "blur(6px)" },
          to:   { opacity: "1", transform: "translateY(0) scale(1)",       filter: "blur(0)" },
        },
        fadeIn: {
          from: { opacity: "0" },
          to:   { opacity: "1" },
        },
        slideUp: {
          from: { opacity: "0", transform: "translateY(14px)", filter: "blur(2px)" },
          to:   { opacity: "1", transform: "translateY(0)",    filter: "blur(0)" },
        },
        slideDown: {
          from: { opacity: "0", transform: "translateY(-10px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        slideInRight: {
          from: { opacity: "0", transform: "translateX(20px)", filter: "blur(2px)" },
          to:   { opacity: "1", transform: "translateX(0)",    filter: "blur(0)" },
        },
        slideInLeft: {
          from: { opacity: "0", transform: "translateX(-14px)" },
          to:   { opacity: "1", transform: "translateX(0)" },
        },
        spinSlow: {
          from: { transform: "rotate(0deg)" },
          to:   { transform: "rotate(360deg)" },
        },
        cursorBlink: {
          "0%, 100%": { opacity: "1" },
          "45%, 55%": { opacity: "0" },
        },
        floatY: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%":       { transform: "translateY(-7px)" },
        },
        progressFill: {
          from: { width: "0%" },
          to:   { width: "var(--progress-target, 100%)" },
        },
        ripple: {
          from: { transform: "scale(0)", opacity: "0.5" },
          to:   { transform: "scale(2.8)", opacity: "0" },
        },
        subtlePulse: {
          "0%, 100%": { opacity: "1" },
          "50%":       { opacity: "0.65" },
        },
        scoreIn: {
          from: { opacity: "0", transform: "scale(0.6)", filter: "blur(4px)" },
          to:   { opacity: "1", transform: "scale(1)",   filter: "blur(0)" },
        },
      },
      animation: {
        shimmer:         "shimmer 1.8s linear infinite",
        halo:            "pulseHalo 2.4s ease-in-out infinite",
        breathe:         "breathe 2.2s ease-in-out infinite",
        cardIn:          "cardIn 700ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        fadeIn:          "fadeIn 280ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        slideUp:         "slideUp 380ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        slideDown:       "slideDown 280ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "slide-in-right":"slideInRight 320ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "slide-in-left": "slideInLeft 280ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "spin-slow":     "spinSlow 8s linear infinite",
        cursorBlink:     "cursorBlink 1.1s ease-in-out infinite",
        floatY:          "floatY 3.2s ease-in-out infinite",
        progressFill:    "progressFill 600ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        ripple:          "ripple 500ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        subtlePulse:     "subtlePulse 1.8s ease-in-out infinite",
        scoreIn:         "scoreIn 420ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
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
