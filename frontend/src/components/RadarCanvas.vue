<template>
  <div class="rounded-[22px] border border-subtle bg-card p-5 shadow-card">
    <div class="mb-4 flex items-center justify-between">
      <div>
        <p class="text-[13px] font-bold tracking-wide text-text-secondary">能力信号雷达</p>
        <p class="mt-1 text-sm font-light leading-7 text-text-muted">当前辅导循环中的能力分布。</p>
      </div>
    </div>
    <canvas ref="canvasRef" width="360" height="360" class="mx-auto block max-w-full" />
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";

const props = defineProps({
  values: { type: Array, default: () => [0.5, 0.5, 0.5, 0.5, 0.5] },
  highContrast: { type: Boolean, default: false },
});

const canvasRef = ref(null);
const labels = ["概念理解", "代码工程", "逻辑推理", "错题恢复", "时间管理"];
const dimensionColors = [
  "--color-primary",
  "--color-secondary",
  "--color-tertiary",
  "--color-success",
  "--color-info",
];

function getColor(varName) {
  if (!canvasRef.value) return "#5A7A6F";
  const value = getComputedStyle(canvasRef.value).getPropertyValue(varName).trim();
  return value || "#5A7A6F";
}

function draw() {
  if (!canvasRef.value) {
    return;
  }

  const computedStyle = getComputedStyle(canvasRef.value);
  const mutedColor = computedStyle.getPropertyValue("--text-muted").trim() || "#5A7A6F";
  const gridColor = computedStyle.getPropertyValue("--border-strong").trim() || "rgba(127,127,127,0.15)";
  const bgColor = computedStyle.getPropertyValue("--space-bg").trim() || "#05060A";

  const ctx = canvasRef.value.getContext("2d");
  const width = canvasRef.value.width;
  const height = canvasRef.value.height;
  const cx = width / 2;
  const cy = height / 2;
  const radius = 124;
  const levels = [0.25, 0.5, 0.75, 1];

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
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    ctx.stroke();
  });

  labels.forEach((label, index) => {
    const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2;
    const x = cx + radius * Math.cos(angle);
    const y = cy + radius * Math.sin(angle);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(x, y);
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = mutedColor;
    ctx.font = "13px Inter, PingFang SC, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, cx + (radius + 30) * Math.cos(angle), cy + (radius + 30) * Math.sin(angle));
  });

  const fillColors = dimensionColors.map((varName) => getColor(varName));
  const avgColor = getColor("--color-primary");

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
  ctx.fillStyle = props.highContrast ? `${avgColor}35` : `${avgColor}22`;
  ctx.fill();
  ctx.strokeStyle = avgColor;
  ctx.lineWidth = 2.4;
  ctx.stroke();

  props.values.forEach((value, index) => {
    const angle = (Math.PI * 2 * index) / labels.length - Math.PI / 2;
    const x = cx + radius * (value || 0.5) * Math.cos(angle);
    const y = cy + radius * (value || 0.5) * Math.sin(angle);
    const color = fillColors[index % fillColors.length];

    ctx.beginPath();
    ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = bgColor;
    ctx.lineWidth = 2.5;
    ctx.stroke();
  });
}

onMounted(draw);
watch(() => props.values, draw, { deep: true });
watch(() => props.highContrast, draw);
</script>
