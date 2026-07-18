<template>
  <AppPageFrame>
    <main class="px-4 py-6 sm:px-6 lg:px-8" :aria-busy="viewState === 'loading' ? 'true' : 'false'">
      <div class="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <header class="border-b border-subtle pb-6">
          <p class="text-xs font-semibold text-text-muted">复习中心</p>
          <div class="mt-2 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 class="text-2xl font-black text-text-primary">今天的补救任务</h1>
              <p class="mt-2 max-w-2xl text-sm leading-7 text-text-secondary">每一项均来自服务端已验证的学习结果，完成复测后才会关闭。</p>
            </div>
            <button
              type="button"
              class="workspace-shell-btn focus-ring min-h-[44px] px-4 py-2 text-sm font-semibold"
              :disabled="viewState === 'loading' || viewState === 'not_loaded' || viewState === 'missing_session'"
              @click="loadDashboard({ announce: true })"
            >
              {{ viewState === 'loading' ? '刷新中...' : '刷新队列' }}
            </button>
          </div>
        </header>

        <section v-if="viewState === 'not_loaded'" class="workspace-shell-card px-5 py-8 text-center sm:px-6" role="status">
          <h2 class="text-lg font-black text-text-primary">复习数据尚未加载</h2>
          <p class="mt-2 text-sm leading-6 text-text-secondary">正在确认当前课程和学习会话，完成后再显示真实复习记录。</p>
        </section>

        <section v-else-if="viewState === 'loading'" class="workspace-shell-card px-5 py-6 sm:px-6" role="status" aria-live="polite">
          <p class="text-sm font-semibold text-text-primary">正在从服务端同步复习队列</p>
          <div class="mt-4 grid gap-3">
            <span class="h-16 animate-pulse bg-card-hover" />
            <span class="h-16 animate-pulse bg-card-hover" />
          </div>
        </section>

        <section v-else-if="viewState === 'missing_session'" class="workspace-shell-card px-5 py-8 text-center sm:px-6" role="alert">
          <h2 class="text-lg font-black text-text-primary">尚未建立可读取的学习会话</h2>
          <p class="mx-auto mt-2 max-w-xl text-sm leading-6 text-text-secondary">{{ missingSessionMessage }}</p>
          <button type="button" class="workspace-shell-btn workspace-shell-btn--accent focus-ring mt-5 min-h-[44px] px-4 py-2 text-sm font-semibold" @click="continueLearning">
            {{ activeCourse?.course_id ? '进入当前学习任务' : '前往课程中心' }}
          </button>
        </section>

        <section v-else-if="viewState === 'error'" class="workspace-shell-card px-5 py-8 text-center sm:px-6" role="alert">
          <h2 class="text-lg font-black text-text-primary">复习队列加载失败</h2>
          <p class="mx-auto mt-2 max-w-xl text-sm leading-6 text-error">{{ loadError }}</p>
          <button type="button" class="workspace-shell-btn workspace-shell-btn--accent focus-ring mt-5 min-h-[44px] px-4 py-2 text-sm font-semibold" @click="loadDashboard({ announce: true })">
            重新加载
          </button>
        </section>

        <p v-if="refreshNotice" class="border border-success/30 bg-success-soft px-4 py-3 text-sm text-text-primary" role="status" aria-live="polite">
          {{ refreshNotice }}
        </p>

        <p v-if="actionError" class="border border-error/30 bg-error-soft px-4 py-3 text-sm text-text-primary" role="alert">
          {{ actionError }}
        </p>

        <template v-if="viewState === 'ready'">
        <section class="workspace-shell-card px-5 py-5 sm:px-6" aria-labelledby="today-review-heading">
          <div class="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p class="text-xs font-semibold text-text-muted">今日队列</p>
              <h2 id="today-review-heading" class="mt-1 text-lg font-black text-text-primary">{{ todayQueue.length ? `${todayQueue.length} 项需要处理` : '没有到期复习' }}</h2>
            </div>
            <p class="text-sm text-text-secondary">{{ dueSummary }}</p>
          </div>

          <div v-if="todayQueue.length" class="mt-5 divide-y divide-subtle">
            <article v-for="item in todayQueue" :key="item.review_item_id" class="grid gap-4 py-4 first:pt-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="text-xs font-bold text-warning">{{ errorTypeLabel(item.error_type) }}</span>
                  <span class="text-xs text-text-muted">{{ item.node_title || item.related_node }}</span>
                  <span class="text-xs text-text-muted">{{ statusLabel(item.status) }}</span>
                </div>
                <p class="mt-2 text-sm font-semibold leading-6 text-text-primary">{{ item.question_prompt || '需要复盘的诊断题' }}</p>
                <p class="mt-1 text-sm leading-6 text-text-secondary">{{ item.explanation || '先核对答案，再完成定向练习。' }}</p>
              </div>
              <button
                type="button"
                class="workspace-shell-btn workspace-shell-btn--accent focus-ring min-h-[44px] px-4 py-2 text-sm font-semibold"
                :disabled="Boolean(actionItemId)"
                @click="startReview(item)"
              >
                {{ actionItemId === item.review_item_id ? '准备中...' : item.status === 'in_progress' ? '继续补救' : '开始补救' }}
              </button>
            </article>
          </div>

          <div v-else class="mt-5 flex flex-col items-start gap-3 border-t border-subtle pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p class="text-sm leading-6 text-text-secondary">服务端已确认当前没有到期复习任务。继续完成当前节点的学习材料，新的真实错误会自动进入这里。</p>
            <button type="button" class="workspace-shell-btn workspace-shell-btn--secondary focus-ring min-h-[44px] px-4 py-2 text-sm font-semibold" @click="continueLearning">
              返回当前学习任务
            </button>
          </div>
        </section>

        <section class="workspace-shell-card px-5 py-5 sm:px-6" aria-labelledby="mistake-book-heading">
          <div class="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p class="text-xs font-semibold text-text-muted">错题本</p>
              <h2 id="mistake-book-heading" class="mt-1 text-lg font-black text-text-primary">逐题复盘</h2>
            </div>
            <p class="text-sm text-text-secondary">{{ mistakes.length }} 条记录</p>
          </div>

          <div v-if="!loading && !mistakes.length" class="mt-5 border-t border-subtle pt-5 text-sm leading-6 text-text-secondary">
            尚未形成可复盘的错题记录。
          </div>

          <div v-else class="mt-5 divide-y divide-subtle">
            <details v-for="item in mistakes" :key="item.review_item_id" class="group py-4 first:pt-0">
              <summary class="min-h-11 cursor-pointer list-none py-2 pr-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div class="min-w-0">
                    <p class="text-sm font-semibold text-text-primary">{{ item.question_prompt || item.question_id }}</p>
                    <p class="mt-1 text-xs text-text-muted">{{ item.node_title || item.related_node }} · {{ errorTypeLabel(item.error_type) }} · {{ statusLabel(item.status) }}</p>
                  </div>
                  <span class="text-xs text-text-muted">{{ formatDate(item.updated_at) }}</span>
                </div>
              </summary>
              <div class="mt-4 grid gap-4 border-t border-subtle pt-4 text-sm leading-6 sm:grid-cols-2">
                <div><p class="text-xs text-text-muted">原答案</p><p class="mt-1 text-text-secondary">{{ item.original_answer || '未作答' }}</p></div>
                <div><p class="text-xs text-text-muted">正确答案</p><p class="mt-1 text-success">{{ item.correct_answer || '以服务端判定为准' }}</p></div>
                <div class="sm:col-span-2"><p class="text-xs text-text-muted">解析</p><p class="mt-1 text-text-secondary">{{ item.explanation || '暂无解析。' }}</p></div>
                <div class="sm:col-span-2"><p class="text-xs text-text-muted">下次复习</p><p class="mt-1 text-text-secondary">{{ item.status === 'completed' ? '已完成复测' : formatDate(item.next_review_at) }}</p></div>
              </div>
            </details>
          </div>
        </section>

        <div class="grid gap-6 lg:grid-cols-2">
          <section class="workspace-shell-card px-5 py-5 sm:px-6" aria-labelledby="weak-nodes-heading">
            <p class="text-xs font-semibold text-text-muted">薄弱知识点</p>
            <h2 id="weak-nodes-heading" class="mt-1 text-lg font-black text-text-primary">优先处理的节点</h2>
            <div v-if="weakNodes.length" class="mt-5 divide-y divide-subtle">
              <article v-for="node in weakNodes" :key="node.node_id" class="py-3 first:pt-0">
                <div class="flex items-center justify-between gap-3">
                  <p class="min-w-0 truncate text-sm font-semibold text-text-primary">{{ node.node_title }}</p>
                  <p class="shrink-0 text-sm font-bold text-warning">{{ toPercent(node.mastery) }}</p>
                </div>
                <div class="mt-2 h-2 overflow-hidden bg-card-hover" aria-hidden="true"><span class="block h-full bg-warning" :style="{ width: `${Math.max(0, Math.min(100, node.mastery * 100))}%` }" /></div>
                <p class="mt-2 text-xs leading-5 text-text-muted">{{ node.outstanding_count }} 条待处理错题 · {{ node.error_types.map(errorTypeLabel).join('、') || '已由真实诊断识别' }}</p>
              </article>
            </div>
            <p v-else class="mt-5 text-sm leading-6 text-text-secondary">当前没有由掌握度或错题记录识别出的薄弱节点。</p>
          </section>

          <section class="workspace-shell-card px-5 py-5 sm:px-6" aria-labelledby="mastery-trend-heading">
            <p class="text-xs font-semibold text-text-muted">掌握度变化趋势</p>
            <h2 id="mastery-trend-heading" class="mt-1 text-lg font-black text-text-primary">每次真实证据带来的变化</h2>
            <div v-if="masteryTrend.length" class="mt-5 divide-y divide-subtle">
              <article v-for="point in masteryTrend" :key="`${point.event_id}-${point.recorded_at}`" class="py-3 first:pt-0">
                <div class="flex items-center justify-between gap-3 text-sm">
                  <p class="min-w-0 truncate font-semibold text-text-primary">{{ point.node_title }}</p>
                  <p class="shrink-0 font-bold" :class="point.mastery_delta >= 0 ? 'text-success' : 'text-error'">{{ signedPercent(point.mastery_delta) }}</p>
                </div>
                <div class="mt-2 h-2 overflow-hidden bg-card-hover" aria-hidden="true"><span class="block h-full bg-primary" :style="{ width: `${Math.max(0, Math.min(100, point.mastery_after * 100))}%` }" /></div>
                <p class="mt-2 text-xs text-text-muted">{{ toPercent(point.mastery_before) }} → {{ toPercent(point.mastery_after) }} · {{ formatDate(point.recorded_at) }}</p>
                <p class="mt-1 text-xs leading-5 text-text-secondary">{{ masteryReasonLabel(point.reason) }}<span v-if="point.evidence_summary"> · {{ point.evidence_summary }}</span></p>
                <details class="mt-2 text-xs text-text-muted">
                  <summary class="focus-ring flex min-h-11 cursor-pointer items-center py-2">查看归因凭据</summary>
                  <dl class="grid gap-2 border-t border-subtle py-3">
                    <div><dt class="inline font-semibold text-text-secondary">事件 ID：</dt><dd class="inline break-all">{{ point.event_id || '未记录' }}</dd></div>
                    <div><dt class="inline font-semibold text-text-secondary">事件类型：</dt><dd class="inline">{{ point.event_type || '未知' }}</dd></div>
                    <div><dt class="inline font-semibold text-text-secondary">资源 ID：</dt><dd class="inline break-all">{{ point.resource_id || '未记录' }}</dd></div>
                  </dl>
                </details>
              </article>
            </div>
            <p v-else class="mt-5 text-sm leading-6 text-text-secondary">完成一次服务端可验证的诊断或代码提交后，这里会显示掌握度变化。</p>
          </section>
        </div>

        <section class="workspace-shell-card px-5 py-5 sm:px-6" aria-labelledby="diagnostic-report-heading">
          <p class="text-xs font-semibold text-text-muted">诊断报告详情</p>
          <h2 id="diagnostic-report-heading" class="mt-1 text-lg font-black text-text-primary">{{ latestDiagnosticTitle }}</h2>
          <div v-if="latestDiagnostic" class="mt-4 grid gap-3 border-y border-subtle py-4 text-sm sm:grid-cols-3">
            <div><p class="text-xs text-text-muted">节点</p><p class="mt-1 font-semibold text-text-primary">{{ latestDiagnostic.node_title }}</p></div>
            <div><p class="text-xs text-text-muted">正确率</p><p class="mt-1 font-semibold text-text-primary">{{ toPercent(latestDiagnostic.correctness) }}</p></div>
            <div><p class="text-xs text-text-muted">题目结果</p><p class="mt-1 font-semibold text-text-primary">{{ latestDiagnostic.correct_count }}/{{ latestDiagnostic.question_count }}</p></div>
          </div>
          <pre v-if="diagnosticMarkdown" class="mt-4 max-h-80 overflow-auto whitespace-pre-wrap font-sans text-sm leading-7 text-text-secondary">{{ diagnosticMarkdown }}</pre>
          <p v-else class="mt-4 text-sm leading-6 text-text-secondary">完成诊断后会显示服务端生成的报告详情。</p>
        </section>
        </template>
      </div>
    </main>
  </AppPageFrame>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import AppPageFrame from "../components/AppPageFrame.vue";
import { useEduAgent } from "../composables/useEduAgent";
import { fetchSessionReviewDashboard, startSessionReviewItem } from "../services/eduAgentApi";

const router = useRouter();
const dashboard = ref(null);
const viewState = ref("not_loaded");
const loadError = ref("");
const actionError = ref("");
const refreshNotice = ref("");
const actionItemId = ref("");
const loading = computed(() => viewState.value === "loading");

const {
  activeCourse,
  bootMode,
  bootstrap,
  currentNode,
  currentPathNodes,
  sessionId,
} = useEduAgent();

const todayQueue = computed(() => Array.isArray(dashboard.value?.today_queue) ? dashboard.value.today_queue : []);
const mistakes = computed(() => Array.isArray(dashboard.value?.mistakes) ? dashboard.value.mistakes : []);
const weakNodes = computed(() => Array.isArray(dashboard.value?.weak_nodes) ? dashboard.value.weak_nodes : []);
const masteryTrend = computed(() => (
  Array.isArray(dashboard.value?.mastery_trend) ? dashboard.value.mastery_trend.slice(-12).reverse() : []
));
const diagnosticMarkdown = computed(() => dashboard.value?.diagnostic_report?.markdown || "");
const latestDiagnostic = computed(() => dashboard.value?.diagnostic_report?.latest || null);
const latestDiagnosticTitle = computed(() => latestDiagnostic.value ? "最近一次已验证诊断" : "等待诊断记录");
const dueSummary = computed(() => todayQueue.value.length ? "按到期时间排序" : "服务端已确认无到期任务");
const missingSessionMessage = computed(() => {
  if (bootMode.value === "login") return "当前登录状态无法恢复，请重新登录后再读取复习记录。";
  if (bootMode.value === "probe") return "请先完成当前课程的入学诊断，系统建立学习会话后才能读取复习记录。";
  return "当前课程还没有有效学习会话，请先进入一个学习节点，再返回复习中心。";
});

onMounted(async () => {
  viewState.value = "loading";
  try {
    await bootstrap();
    if (bootMode.value === "course_selection") {
      await router.replace({ name: "courses" });
      return;
    }
    await loadDashboard();
  } catch (error) {
    loadError.value = error?.response?.data?.detail || error?.message || "无法恢复当前学习会话。";
    viewState.value = "error";
  }
});

async function loadDashboard({ announce = false } = {}) {
  refreshNotice.value = "";
  actionError.value = "";
  if (!sessionId.value) {
    dashboard.value = null;
    loadError.value = "";
    viewState.value = "missing_session";
    return;
  }
  viewState.value = "loading";
  loadError.value = "";
  try {
    const payload = await fetchSessionReviewDashboard(sessionId.value);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new Error("服务端未返回有效的复习队列。请重试。");
    }
    dashboard.value = payload;
    viewState.value = "ready";
    if (announce) {
      refreshNotice.value = todayQueue.value.length
        ? `刷新完成，服务端返回 ${todayQueue.value.length} 项到期复习任务。`
        : "刷新完成，服务端确认当前没有到期复习任务。";
    }
  } catch (error) {
    loadError.value = error?.response?.data?.detail || error?.message || "无法加载复习队列，请重试。";
    viewState.value = "error";
  }
}

async function startReview(item) {
  if (!item?.review_item_id || actionItemId.value) return;
  actionItemId.value = item.review_item_id;
  actionError.value = "";
  try {
    const result = await startSessionReviewItem(sessionId.value, item.review_item_id);
    const task = result?.learning_task;
    if (result?.status !== "ok" || !task?.node_id || !activeCourse.value?.course_id) {
      throw new Error(result?.detail || "无法开始当前补救任务。");
    }
    await router.push({
      name: "learn",
      params: { courseId: activeCourse.value.course_id, nodeId: task.node_id },
      query: { reviewItem: item.review_item_id, reviewPhase: task.phase || "material_review" },
    });
  } catch (error) {
    actionError.value = error?.response?.data?.detail || error?.message || "无法开始当前补救任务。";
  } finally {
    actionItemId.value = "";
  }
}

function continueLearning() {
  const nodeId = currentNode.value || currentPathNodes.value[0]?.id;
  if (!activeCourse.value?.course_id || !nodeId) {
    void router.push({ name: "courses" });
    return;
  }
  void router.push({ name: "learn", params: { courseId: activeCourse.value.course_id, nodeId } });
}

function errorTypeLabel(errorType) {
  return {
    concept_understanding: "概念理解偏差",
    application_context: "适用场景判断偏差",
    boundary_condition: "边界条件遗漏",
    wrong_answer: "代码答案错误",
    syntax_error: "代码语法错误",
    runtime_error: "代码运行错误",
    time_limit: "代码执行超时",
    internal_error: "代码判题服务错误",
    insufficient_evidence: "掌握证据待补强",
  }[errorType] || "需要复盘";
}

function statusLabel(status) {
  return {
    due: "待复习",
    in_progress: "进行中",
    completed: "已完成",
  }[status] || "待处理";
}

function toPercent(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${Math.round(numeric * 100)}%` : "--";
}

function signedPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return `${numeric >= 0 ? "+" : ""}${Math.round(numeric * 100)}%`;
}

function masteryReasonLabel(reason) {
  return {
    verified_diagnostic_quiz: "服务端诊断答案验证",
    verified_code_submission: "隔离代码测试通过",
  }[reason] || reason || "服务端验证学习证据";
}

function formatDate(value) {
  if (!value) return "未安排";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未安排";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
</script>
