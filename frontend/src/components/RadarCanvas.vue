<template>
  <div class="rounded-[22px] border border-white/[0.035] bg-[linear-gradient(180deg,rgba(255,255,255,0.025),rgba(255,255,255,0.01))] p-4 shadow-[inset_0_1px_8px_rgba(0,0,0,0.34)]">
    <div class="mb-3 flex items-center justify-between">
      <div>
        <p class="text-[10px] font-black uppercase tracking-[0.16em] text-[#4A4F68]">Signal Radar</p>
        <p class="mt-1 text-xs font-light text-[#4A4F68]">Current capability distribution across the tutoring loop.</p>
      </div>
    </div>
    <canvas ref="canvasRef" width="320" height="320" class="mx-auto block max-w-full" />
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";

const props = defineProps({
  values: { type: Array, default: () => [0.5, 0.5, 0.5, 0.5, 0.5] },
  highContrast: { type: Boolean, default: false },
});

const canvasRef = ref(null);
const labels = ["Concept", "Engineering", "Reasoning", "Recovery", "Timing"];

function draw() {
  if (!canvasRef.value) {
    return;
  }

  const ctx = canvasRef.value.getContext("2d");
  const width = canvasRef.value.width;
  const height = canvasRef.value.height;
  const cx = width / 2;
  const cy = height / 2;
  const radius = 112;
  const levels = [0.25, 0.5, 0.75, 1];
  const accent = props.highContrast ? "#00E5FF" : "#00F2FE";
  const accentAlt = props.highContrast ? "#9D4EDD" : "#7F00FF";

  ctx.clearRect(0, 0, width, height);

  levels.forEach((level) => {
    ctx.beginPath();
    for (let i = 0; i < labels.length; i += 1) {
      const angle = (Math.PI * 2 * i) / labels.length - Math.PI / 2;
      const x = cx + radius * level * Math.cos(angle);
      const y = cy + radius * level * Math.sin(angle);
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.closePath();
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.stroke();
  });

  labels.forEach((label, index) => {
    const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2;
    const x = cx + radius * Math.cos(angle);
    const y = cy + radius * Math.sin(angle);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(x, y);
    ctx.strokeStyle = "rgba(255,255,255,0.09)";
    ctx.stroke();
    ctx.fillStyle = "#6E748B";
    ctx.font = "11px Inter, PingFang SC, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(label, cx + (radius + 24) * Math.cos(angle), cy + (radius + 24) * Math.sin(angle));
  });

  ctx.beginPath();
  props.values.forEach((value, index) => {
    const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2;
    const x = cx + radius * (value || 0.5) * Math.cos(angle);
    const y = cy + radius * (value || 0.5) * Math.sin(angle);
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.closePath();
  ctx.fillStyle = `${accent}20`;
  ctx.fill();
  ctx.strokeStyle = accentAlt;
  ctx.lineWidth = 2.2;
  ctx.stroke();

  props.values.forEach((value, index) => {
    const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2;
    const x = cx + radius * (value || 0.5) * Math.cos(angle);
    const y = cy + radius * (value || 0.5) * Math.sin(angle);
    ctx.beginPath();
    ctx.arc(x, y, 4.5, 0, Math.PI * 2);
    ctx.fillStyle = accent;
    ctx.fill();
    ctx.strokeStyle = "#07080B";
    ctx.lineWidth = 2;
    ctx.stroke();
  });
}

onMounted(draw);
watch(() => props.values, draw, { deep: true });
watch(() => props.highContrast, draw);
</script>
