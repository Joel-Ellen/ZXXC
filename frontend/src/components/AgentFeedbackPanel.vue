<template>
  <section class="flex min-h-0 flex-col gap-4">
    <div class="workspace-shell-card rounded-2xl px-4 py-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">智能体反馈</p>
          <h3 class="mt-2 text-lg font-black tracking-tight text-text-primary">当前节点反馈面板</h3>
          <p class="mt-2 text-sm leading-6 text-text-secondary">
            {{ summaryText }}
          </p>
        </div>
        <div class="workspace-shell-card-soft rounded-2xl px-4 py-3 text-right">
          <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">诊断状态</p>
          <p class="mt-2 text-lg font-black text-text-primary">{{ diagnosticTitle }}</p>
          <p class="mt-1 text-[11px] leading-5 text-text-muted">{{ diagnosticDetail }}</p>
        </div>
      </div>
    </div>

    <div v-if="feedbackItems.length" class="space-y-3">
      <article
        v-for="item in feedbackItems"
        :key="`${item.agent}-${item.stage}`"
        class="workspace-shell-card rounded-2xl px-4 py-4"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">{{ stageLabel(item) }}</span>
              <span
                class="rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.1em]"
                :class="statusClass(item.status)"
              >
                {{ statusLabel(item.status) }}
              </span>
            </div>
            <p class="mt-2 text-sm font-semibold text-text-primary">{{ item.headline || agentLabel(item.agent) }}</p>
            <p v-if="item.summary" class="mt-2 text-sm leading-6 text-text-secondary">{{ item.summary }}</p>
          </div>
        </div>

        <div v-if="structuredEntries(item).length" class="mt-4 grid gap-2 sm:grid-cols-2">
          <div
            v-for="entry in structuredEntries(item)"
            :key="`${item.agent}-${entry.key}`"
            class="workspace-shell-card-soft rounded-2xl px-3 py-3"
          >
            <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">{{ entry.label }}</p>
            <p class="mt-2 text-sm font-semibold text-text-primary break-words">{{ entry.value }}</p>
          </div>
        </div>

        <MarkdownContent
          v-if="item.details_md"
          class="mt-4"
          :content="item.details_md"
          :mermaid-source="item.artifacts?.mermaid_src || ''"
        />
      </article>
    </div>

    <div v-else class="workspace-shell-card rounded-2xl px-4 py-4">
      <p class="text-sm leading-6 text-text-muted">
        当前还没有可展示的结构化反馈。完成一次节点加载、诊断或辅导后，这里会同步显示各智能体的完整输出。
      </p>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import MarkdownContent from "./MarkdownContent.vue";

const props = defineProps({
  feedbackItems: { type: Array, default: () => [] },
  lastDiagnostic: { type: Object, default: null },
  currentNodeTitle: { type: String, default: "" },
});

const summaryText = computed(() => {
  if (props.lastDiagnostic) {
    return `当前节点 ${props.currentNodeTitle || "未命名节点"} 的诊断、推进结论和资源装配反馈已经汇总到这里，方便你按顺序复盘。`;
  }
  return `当前节点 ${props.currentNodeTitle || "未命名节点"} 的学习反馈会在加载资源、提交诊断和发起辅导后持续更新。`;
});

const diagnosticTitle = computed(() => {
  if (!props.lastDiagnostic) return "等待诊断";
  return props.lastDiagnostic.advancedToNextNode ? "已推进" : "继续补强";
});

const diagnosticDetail = computed(() => {
  if (!props.lastDiagnostic) return "尚未提交本轮诊断";
  const beforePercent = Math.round((props.lastDiagnostic.masteryBefore ?? 0) * 100);
  const afterPercent = Math.round((props.lastDiagnostic.masteryAfter ?? 0) * 100);
  return `${beforePercent}% -> ${afterPercent}%`;
});

function statusClass(status) {
  switch (status) {
    case "success":
      return "bg-success-soft text-success";
    case "warning":
      return "bg-warning-soft text-warning";
    case "error":
      return "bg-error-soft text-error";
    case "skipped":
      return "bg-card-hover text-text-muted";
    default:
      return "bg-primary-soft text-primary";
  }
}

const STATUS_LABELS = {
  success: "已完成",
  warning: "需关注",
  error: "执行失败",
  skipped: "已跳过",
  info: "处理中",
};

const STAGE_LABELS = {
  tutor_question: "辅导问答",
  official_orchestration: "统一学习编排",
};

const AGENT_LABELS = {
  Tutor: "智能辅导",
  Evaluator: "学习评估智能体",
  Profiler: "画像分析智能体",
  Planner: "路径规划智能体",
  Assessment: "综合评估智能体",
  Validator: "内容校验智能体",
};

const FIELD_LABELS = {
  query: "学生问题",
  context_type: "辅导模式",
  node_id: "学习节点",
  resource_id: "学习资源",
};

const FIELD_VALUE_LABELS = {
  concept: "概念讲解",
  problem_solving: "问题求解",
  code_debug: "代码调试",
  exam_prep: "考试复习",
  general: "综合辅导",
  success: "已完成",
  warning: "需关注",
  error: "执行失败",
  skipped: "已跳过",
};

function statusLabel(status) {
  return STATUS_LABELS[status] || "处理中";
}

function agentLabel(agent) {
  return AGENT_LABELS[agent] || (/[㐀-鿿]/u.test(String(agent || "")) ? agent : "学习智能体");
}

function stageLabel(item) {
  const stage = item?.stage || "";
  if (STAGE_LABELS[stage]) return STAGE_LABELS[stage];
  if (/[㐀-鿿]/u.test(stage)) return stage;
  return agentLabel(item?.agent);
}

function structuredValue(key, value) {
  if (typeof value === "number") return String(value);
  if (FIELD_VALUE_LABELS[value]) return FIELD_VALUE_LABELS[value];
  if (["query", "学生问题"].includes(key)) return value;
  const text = String(value || "");
  if (/[㐀-鿿]/u.test(text) || /^[A-Z0-9_.:/+-]{1,64}$/u.test(text)) return text;
  return "已记录";
}

function structuredEntries(item) {
  const data = item?.structured_data || {};
  return Object.entries(data)
    .filter(([, value]) => value !== null && value !== undefined && value !== "" && !Array.isArray(value) && typeof value !== "object")
    .slice(0, 6)
    .map(([key, value]) => ({
      key,
      label: FIELD_LABELS[key] || (/[㐀-鿿]/u.test(key) ? key : "补充信息"),
      value: structuredValue(key, value),
    }));
}
</script>
