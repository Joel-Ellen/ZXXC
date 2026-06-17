<template>
  <div
    class="pointer-events-none fixed inset-0 overflow-hidden"
    :class="{ 'motion-reduce': reduceMotion }"
    aria-hidden="true"
  >
    <!-- Deep base -->
    <div class="absolute inset-0 bg-space-bg transition-colors duration-500" />

    <!-- Aurora gradient mesh -->
    <div class="aurora-mesh absolute inset-0 opacity-60" />

    <!-- Slow drifting orbs -->
    <div class="orb orb-1" />
    <div class="orb orb-2" />
    <div class="orb orb-3" />
    <div class="orb orb-4" />

    <!-- Subtle starfield -->
    <div class="starfield absolute inset-0 opacity-40" />

    <!-- Top light sheen -->
    <div class="sheen absolute inset-x-0 top-0 h-[60vh] opacity-30" />

    <!-- Noise texture overlay for depth -->
    <div class="noise-overlay absolute inset-0 opacity-[0.035]" />
  </div>
</template>

<script setup>
defineProps({
  reduceMotion: { type: Boolean, default: false },
});
</script>

<style scoped>
/* ── Aurora gradient mesh ── */
.aurora-mesh {
  background:
    radial-gradient(ellipse at 20% 20%, var(--aurora-mesh-1) 0%, transparent 45%),
    radial-gradient(ellipse at 80% 30%, var(--aurora-mesh-2) 0%, transparent 45%),
    radial-gradient(ellipse at 50% 80%, var(--aurora-mesh-3) 0%, transparent 40%),
    radial-gradient(ellipse at 10% 90%, var(--aurora-mesh-4) 0%, transparent 40%);
  filter: blur(60px);
  animation: aurora-drift 24s ease-in-out infinite alternate;
}

/* ── Floating orbs ── */
.orb {
  position: absolute;
  border-radius: 9999px;
  filter: blur(80px);
  opacity: 0.55;
  will-change: transform;
}

.orb-1 {
  width: 40vw;
  height: 40vw;
  top: -10vw;
  left: -10vw;
  background: radial-gradient(circle, var(--aurora-orb-1), transparent 70%);
  animation: float-1 22s ease-in-out infinite alternate;
}

.orb-2 {
  width: 35vw;
  height: 35vw;
  top: 15vh;
  right: -8vw;
  background: radial-gradient(circle, var(--aurora-orb-2), transparent 70%);
  animation: float-2 26s ease-in-out infinite alternate;
}

.orb-3 {
  width: 28vw;
  height: 28vw;
  bottom: -6vw;
  left: 25vw;
  background: radial-gradient(circle, var(--aurora-orb-3), transparent 70%);
  animation: float-3 20s ease-in-out infinite alternate;
}

.orb-4 {
  width: 24vw;
  height: 24vw;
  bottom: 20vh;
  right: 15vw;
  background: radial-gradient(circle, var(--aurora-orb-4), transparent 70%);
  animation: float-4 28s ease-in-out infinite alternate;
}

/* ── Starfield via CSS dots ── */
.starfield {
  background-image:
    radial-gradient(circle at 12% 22%, var(--text-muted) 0.5px, transparent 1px),
    radial-gradient(circle at 38% 46%, var(--text-muted) 0.5px, transparent 1px),
    radial-gradient(circle at 62% 18%, var(--text-muted) 0.5px, transparent 1px),
    radial-gradient(circle at 84% 72%, var(--text-muted) 0.5px, transparent 1px),
    radial-gradient(circle at 28% 78%, var(--text-muted) 0.5px, transparent 1px),
    radial-gradient(circle at 73% 52%, var(--text-muted) 0.5px, transparent 1px),
    radial-gradient(circle at 5% 58%, var(--text-muted) 0.5px, transparent 1px),
    radial-gradient(circle at 55% 92%, var(--text-muted) 0.5px, transparent 1px),
    radial-gradient(circle at 91% 12%, var(--text-muted) 0.5px, transparent 1px),
    radial-gradient(circle at 46% 34%, var(--text-muted) 0.5px, transparent 1px);
  background-size: 420px 420px;
  animation: star-twinkle 10s ease-in-out infinite alternate;
}

/* ── Top sheen ── */
.sheen {
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.04) 0%,
    rgba(255, 255, 255, 0.01) 40%,
    transparent 100%
  );
  pointer-events: none;
}

/* ── Noise texture ── */
.noise-overlay {
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 400 400' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

/* ── Keyframes ── */
@keyframes aurora-drift {
  0% { transform: scale(1) translate(0, 0); }
  50% { transform: scale(1.08) translate(-2%, 1%); }
  100% { transform: scale(1.04) translate(2%, -1%); }
}

@keyframes float-1 {
  0% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(8vw, 10vh) scale(1.1); }
}

@keyframes float-2 {
  0% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(-6vw, 8vh) scale(1.08); }
}

@keyframes float-3 {
  0% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(5vw, -8vh) scale(1.12); }
}

@keyframes float-4 {
  0% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(-4vw, -6vh) scale(1.06); }
}

@keyframes star-twinkle {
  0% { opacity: 0.25; }
  100% { opacity: 0.55; }
}

/* ── Reduced motion ── */
.motion-reduce .aurora-mesh,
.motion-reduce .orb,
.motion-reduce .starfield {
  animation: none;
}

@media (prefers-reduced-motion: reduce) {
  .aurora-mesh,
  .orb,
  .starfield {
    animation: none;
  }
}
</style>
