<template>
  <AppPageFrame>
    <section class="px-4 py-6 sm:px-6 lg:px-8">
      <div class="mx-auto flex w-full max-w-5xl flex-col gap-6">
        <section
          v-if="viewState === 'loading'"
          class="workspace-shell-card rounded-xl px-5 py-10 text-center sm:px-6"
          aria-live="polite"
        >
          <h1 class="text-lg font-black text-text-primary">正在恢复学习进度</h1>
          <p class="mt-2 text-sm text-text-secondary">正在同步当前课程、学习路径和掌握度记录。</p>
        </section>

        <section
          v-else-if="viewState === 'error'"
          class="workspace-shell-card rounded-xl px-5 py-8 text-center sm:px-6"
          role="alert"
        >
          <h1 class="text-lg font-black text-text-primary">学习进度暂时无法加载</h1>
          <p class="mx-auto mt-2 max-w-xl text-sm text-error">{{ progressErrorMessage }}</p>
          <button
            type="button"
            class="workspace-shell-btn workspace-shell-btn--accent focus-ring mt-5 min-h-11 px-4 text-sm font-semibold"
            @click="initializeProgress"
          >
            重新加载
          </button>
        </section>

        <section
          v-else-if="viewState === 'login'"
          class="workspace-shell-card rounded-xl px-5 py-8 text-center sm:px-6"
        >
          <h1 class="text-lg font-black text-text-primary">登录后查看学习进度</h1>
          <p class="mt-2 text-sm text-text-secondary">当前登录状态已失效，请重新登录后恢复课程位置。</p>
          <button
            type="button"
            class="workspace-shell-btn workspace-shell-btn--accent focus-ring mt-5 min-h-11 px-4 text-sm font-semibold"
            @click="goToLogin"
          >
            前往登录
          </button>
        </section>

        <section
          v-else-if="viewState === 'probe'"
          class="workspace-shell-card rounded-xl px-5 py-8 text-center sm:px-6"
        >
          <h1 class="text-lg font-black text-text-primary">先完成入学诊断</h1>
          <p class="mt-2 text-sm text-text-secondary">系统会根据真实诊断结果生成课程路径，完成前不会显示模拟进度。</p>
          <button
            type="button"
            class="workspace-shell-btn workspace-shell-btn--accent focus-ring mt-5 min-h-11 px-4 text-sm font-semibold"
            @click="continueProbe"
          >
            继续诊断
          </button>
        </section>

        <template v-else>
          <header class="workspace-shell-card rounded-xl px-5 py-6 sm:px-6">
            <p class="text-xs font-semibold text-text-muted">学习进度</p>
            <h1 class="mt-2 text-2xl font-black text-text-primary">{{ activeCourse?.title_cn || '当前课程' }}</h1>
            <p class="mt-3 text-sm text-text-secondary">已掌握 {{ masteredCount }} / {{ currentPathNodes.length }} 个节点，整体进度 {{ overallProgress }}%。</p>
            <div class="mt-4 h-2 overflow-hidden rounded-full bg-space-elevated" aria-label="整体学习进度" role="progressbar" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="overallProgress">
              <div class="h-full bg-primary transition-all" :style="{ width: `${overallProgress}%` }" />
            </div>
          </header>

          <section class="workspace-shell-card rounded-xl px-5 py-5 sm:px-6">
            <div v-if="viewState === 'empty'" class="py-6 text-center">
              <h2 class="text-base font-black text-text-primary">当前课程没有可用的学习路径</h2>
              <p class="mt-2 text-sm text-text-secondary">路径同步已完成，但服务端没有返回学习节点。可以重新同步，或前往课程中心选择其他课程。</p>
              <div class="mt-5 flex flex-wrap justify-center gap-3">
                <button
                  type="button"
                  class="workspace-shell-btn workspace-shell-btn--accent focus-ring min-h-11 px-4 text-sm font-semibold"
                  @click="initializeProgress"
                >
                  重新同步
                </button>
                <button
                  type="button"
                  class="workspace-shell-btn focus-ring min-h-11 px-4 text-sm font-semibold"
                  @click="openCourses"
                >
                  前往课程中心
                </button>
              </div>
            </div>
            <ol v-else class="space-y-3">
              <li v-for="node in currentPathNodes" :key="node.id" class="flex flex-col gap-3 border-b border-subtle py-3 last:border-b-0 sm:flex-row sm:items-center sm:justify-between">
                <div class="min-w-0">
                  <p class="text-sm font-bold text-text-primary">{{ node.order }}. {{ node.title }}</p>
                  <p class="mt-1 text-xs text-text-muted">掌握度 {{ Math.round((node.mastery || 0) * 100) }}%</p>
                </div>
                <button type="button" class="workspace-shell-btn focus-ring min-h-11 shrink-0 px-3 py-2 text-xs font-semibold" @click="openNode(node.id)">
                  {{ node.id === currentNode ? '当前学习中' : '打开节点' }}
                </button>
              </li>
            </ol>
          </section>

          <section class="workspace-shell-card rounded-xl px-5 py-5 sm:px-6" aria-labelledby="mastery-audit-title">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p class="text-xs font-semibold text-text-muted">学习事件账本</p>
              <h2 id="mastery-audit-title" class="mt-1 text-lg font-black text-text-primary">掌握度变更依据</h2>
            </div>
            <button
              type="button"
              class="workspace-shell-btn focus-ring min-h-11 px-3 py-2 text-xs font-semibold"
              :disabled="auditLoading || Boolean(auditPrerequisiteError)"
              :title="auditPrerequisiteError || ''"
              :aria-describedby="auditPrerequisiteError || auditError || !masteryAttributions.length ? 'mastery-audit-state' : undefined"
              @click="loadAudit"
            >
              {{ auditLoading ? '同步中' : '刷新记录' }}
            </button>
          </div>

          <p v-if="auditPrerequisiteError" id="mastery-audit-state" class="mt-4 text-sm leading-6 text-error" role="alert">{{ auditPrerequisiteError }}</p>
          <p v-else-if="auditError" id="mastery-audit-state" class="mt-4 text-sm text-error" role="alert">{{ auditError }}</p>
          <p v-else-if="auditLoading" id="mastery-audit-state" class="mt-4 text-sm text-text-secondary">正在同步服务端学习事件。</p>
          <p v-else-if="!masteryAttributions.length" id="mastery-audit-state" class="mt-4 text-sm text-text-secondary">尚无服务端确认的掌握度变化。</p>

          <ol v-else class="mt-5 space-y-4" data-testid="mastery-audit-list">
            <li
              v-for="entry in masteryAttributions"
              :key="entry.event_id"
              class="border-b border-subtle pb-4 last:border-b-0 last:pb-0"
            >
              <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div class="min-w-0">
                  <p class="text-sm font-bold text-text-primary">{{ nodeLabel(entry.node_id) }}</p>
                  <p class="mt-1 break-all text-xs text-text-muted">{{ entry.resource_id || '无资源标识' }}</p>
                </div>
                <p class="shrink-0 text-xs text-text-muted">{{ formatTime(entry.recorded_at) }}</p>
              </div>

              <dl class="mt-3 grid gap-3 text-xs text-text-secondary sm:grid-cols-2 lg:grid-cols-4">
                <div><dt class="text-text-muted">事件</dt><dd class="mt-1 font-semibold text-text-primary">{{ entry.event_type }}</dd></div>
                <div><dt class="text-text-muted">尝试</dt><dd class="mt-1 font-semibold text-text-primary">{{ entry.attempt_number }} · {{ entry.used_hint ? '使用提示' : '未使用提示' }}</dd></div>
                <div><dt class="text-text-muted">掌握度</dt><dd class="mt-1 font-semibold text-text-primary">{{ percent(entry.mastery_before) }} → {{ percent(entry.mastery_after) }}</dd></div>
                <div><dt class="text-text-muted">服务端结论</dt><dd class="mt-1 font-semibold text-text-primary">{{ entry.reason || '已验证' }}</dd></div>
              </dl>

              <details v-if="entry.evidence" class="mt-3">
                <summary class="focus-ring flex min-h-11 cursor-pointer items-center py-2 text-xs font-semibold text-primary">服务端验证证据</summary>
                <pre class="mt-2 overflow-x-auto whitespace-pre-wrap rounded-lg bg-space-elevated px-3 py-2 text-[11px] leading-5 text-text-secondary">{{ evidenceText(entry.evidence) }}</pre>
              </details>
            </li>
          </ol>
          </section>
        </template>
      </div>
    </section>
  </AppPageFrame>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import AppPageFrame from "../components/AppPageFrame.vue";
import { useEduAgent } from "../composables/useEduAgent";
import { buildSessionId, fetchSessionLearningEventHistory } from "../services/eduAgentApi";

const router = useRouter();
const {
  activeCourse,
  bootMode,
  bootstrap,
  bootstrapError,
  currentNode,
  currentPathNodes,
  infoMessage,
  masteredCount,
  overallProgress,
  userId,
} = useEduAgent();
const auditHistory = ref({ events: [], mastery_attributions: [] });
const auditLoading = ref(false);
const auditError = ref("");
const pageLoading = ref(true);
const pageError = ref("");
const masteryAttributions = computed(() => auditHistory.value.mastery_attributions ?? []);
const auditPrerequisiteError = computed(() => {
  if (!activeCourse.value?.course_id) {
    return "尚未确定当前课程，无法刷新学习事件记录。请先从课程中心选择课程。";
  }
  if (!userId.value) {
    return "当前会话缺少用户身份，无法刷新学习事件记录。请重新登录后再试。";
  }
  return "";
});
const viewState = computed(() => {
  if (pageLoading.value || bootMode.value === "loading" || bootMode.value === "course_selection") {
    return "loading";
  }
  if (pageError.value || bootstrapError.value || bootMode.value === "error") {
    return "error";
  }
  if (bootMode.value === "login") {
    return "login";
  }
  if (bootMode.value === "probe") {
    return "probe";
  }
  if (bootMode.value === "ready") {
    return currentPathNodes.value.length ? "ready" : "empty";
  }
  return "error";
});
const progressErrorMessage = computed(() => (
  pageError.value || bootstrapError.value || infoMessage.value || "无法同步当前课程的学习状态，请在此处重试。"
));

onMounted(initializeProgress);

async function initializeProgress() {
  pageLoading.value = true;
  pageError.value = "";
  auditHistory.value = { events: [], mastery_attributions: [] };
  auditError.value = "";

  try {
    await bootstrap();
    if (bootMode.value === "course_selection") {
      await router.replace({ name: "courses" });
      return;
    }
    if (bootMode.value === "ready") {
      await loadAudit();
    }
  } catch (error) {
    pageError.value = error?.response?.data?.detail || error?.message || "无法恢复学习进度。";
  } finally {
    pageLoading.value = false;
  }
}

function goToLogin() {
  router.push({ name: "login", query: { redirect: "/progress" } });
}

function continueProbe() {
  if (!activeCourse.value?.course_id) {
    router.push({ name: "courses" });
    return;
  }
  router.push({
    name: "learn",
    params: { courseId: activeCourse.value.course_id, nodeId: "setup" },
  });
}

function openCourses() {
  router.push({ name: "courses" });
}

function openNode(nodeId) {
  if (!activeCourse.value) {
    router.push({ name: "courses" });
    return;
  }
  router.push({ name: "learn", params: { courseId: activeCourse.value.course_id, nodeId } });
}

async function loadAudit() {
  if (auditPrerequisiteError.value) {
    auditError.value = auditPrerequisiteError.value;
    return;
  }

  auditLoading.value = true;
  auditError.value = "";
  try {
    auditHistory.value = await fetchSessionLearningEventHistory(
      buildSessionId(userId.value, activeCourse.value.course_id),
    );
  } catch (error) {
    auditError.value = error?.response?.data?.detail || error?.message || "无法同步学习事件。";
  } finally {
    auditLoading.value = false;
  }
}

function nodeLabel(nodeId) {
  return currentPathNodes.value.find((node) => node.id === nodeId)?.title || nodeId || "未标记节点";
}

function percent(value) {
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : "--";
}

function formatTime(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}

function evidenceText(evidence) {
  return typeof evidence === "string" ? evidence : JSON.stringify(evidence, null, 2);
}
</script>
