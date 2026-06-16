/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js}"],
  theme: {
    extend: {
      colors: {
        space: {
          bg: "#0A0B10",
          surface: "#121420",
          line: "rgba(240,240,245,0.08)",
          elevated: "rgba(18,20,32,0.86)",
        },
        aurora: {
          mint: "#00F2FE",
          purple: "#7F00FF",
          crimson: "#FF3366",
          mintContrast: "#00E5FF",
          purpleContrast: "#9D4EDD",
        },
        text: {
          primary: "#F0F0F5",
          secondary: "#B0B5C0",
          muted: "#7B8294",
        },
      },
      fontFamily: {
        sans: ["Inter", "PingFang SC", "HarmonyOS Sans SC", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
      boxShadow: {
        aurora: "0 0 28px rgba(127, 0, 255, 0.18)",
        glass: "0 20px 50px rgba(3, 6, 18, 0.34)",
      },
      keyframes: {
        shimmer: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(220%)" },
        },
        pulseHalo: {
          "0%, 100%": { opacity: "0.35", transform: "scale(1)" },
          "50%": { opacity: "0.75", transform: "scale(1.06)" },
        },
        cardIn: {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.8s linear infinite",
        halo: "pulseHalo 2.4s ease-in-out infinite",
        cardIn: "cardIn 320ms cubic-bezier(0.16, 1, 0.3, 1)",
      },
      backdropBlur: {
        aurora: "12px",
      },
    },
  },
  plugins: [],
};
