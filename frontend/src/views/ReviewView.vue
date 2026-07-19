<template>
  <div class="h-screen flex flex-col" :style="{ background: 'var(--space-bg)', color: 'var(--text-primary)' }">
    <header class="sticky top-0 z-20 border-b border-subtle backdrop-blur-lg shrink-0" style="background:color-mix(in srgb, var(--space-panel) 96%, transparent);min-height:4rem">
      <div class="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
        <div class="flex items-center gap-4">
          <button type="button" class="focus-ring rounded-lg px-3 py-1.5 text-sm font-medium text-text-secondary hover:text-text-primary transition-colors" @click="goBack">&larr; 返回工作台</button>
          <div class="flex items-center gap-2">
            <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-[10px] font-black text-primary-text">错</span>
            <h1 class="text-base font-bold text-text-primary">错题本</h1>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div v-if="totalCount" class="relative">
            <button type="button" class="focus-ring flex items-center gap-1 rounded-lg bg-primary px-4 py-1.5 text-xs font-semibold text-primary-text transition-colors hover:bg-primary-dark" @click.stop="retestOpen = !retestOpen">重新刷题<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg></button>
            <div v-if="retestOpen" class="absolute right-0 top-full mt-1 rounded-xl border border-subtle bg-card shadow-lg py-1 min-w-[160px] z-50" @click.stop>
              <button type="button" class="focus-ring w-full px-4 py-2 text-left text-xs text-text-secondary hover:text-text-primary hover:bg-card-hover transition-colors" @click="goRetest('today')">重刷今日错题</button>
              <button type="button" class="focus-ring w-full px-4 py-2 text-left text-xs text-text-secondary hover:text-text-primary hover:bg-card-hover transition-colors" @click="goRetest('all')">重刷全部错题</button>
            </div>
          </div>
          <span class="text-xs text-text-muted">数据结构与算法</span>
        </div>
      </div>
    </header>

    <div class="flex-1 flex min-h-0">
    <main class="flex-1 overflow-y-auto mx-auto max-w-3xl px-5 py-8">
      <div v-if="loading" class="flex items-center justify-center py-20">
        <div class="flex items-center gap-2 text-text-muted">
          <span class="h-4 w-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />
          加载错题数据...
        </div>
      </div>

      <div v-else-if="error" class="rounded-xl border border-error-soft bg-error-soft/30 p-6 text-center">
        <p class="text-sm text-error">{{ error }}</p>
        <button type="button" class="focus-ring mt-3 rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-text" @click="fetchData">重试</button>
      </div>

      <template v-else>
        <!-- 今日错题 -->
        <section v-if="todayQueue.length" class="mb-8">
          <h2 class="mb-4 flex items-center gap-2 text-sm font-semibold">
            <span class="h-2 w-2 rounded-full bg-warning" />
            今日错题
            <span class="rounded-full bg-warning-soft px-2 py-0.5 text-xs text-warning-dark">{{ todayQueue.length }}</span>
          </h2>
          <div class="space-y-3">
            <article
              v-for="item in todayQueue"
              :key="item.review_item_id"
              class="rounded-xl border border-subtle bg-card p-4 transition-all duration-300"
              :class="removingIds.includes(item.review_item_id) ? 'opacity-0 translate-x-4 scale-95' : 'hover:border-warning/30'"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2 mb-2">
                    <span class="rounded-full bg-warning-soft px-2 py-0.5 text-xs font-semibold text-warning-dark">{{ errorLabel(item.error_type) }}</span>
                    <span class="text-sm text-text-muted">{{ item.node_title || item.node_id }}</span>
                  </div>
                  <p class="text-sm leading-6 text-text-primary">{{ item.question_prompt }}</p>
                  <div class="mt-3 space-y-1.5 text-sm">
                    <div class="text-text-muted">你的答案：<span class="text-error font-medium">{{ item.original_answer || '未作答' }}</span></div>
                    <div class="text-text-muted">正确答案：<span class="text-success font-medium">{{ item.correct_answer }}</span></div>
                  </div>
                  <p v-if="item.explanation" class="mt-2 rounded-lg bg-[#FAFCFB] px-3 py-2 text-sm leading-6 text-text-secondary">
                    <span class="font-semibold text-text-muted">解析：</span>{{ item.explanation }}
                  </p>
                </div>
                <button type="button" class="focus-ring shrink-0 rounded-lg p-1.5 text-text-muted hover:text-error hover:bg-error-soft transition-colors" title="删除" @click="removeItem(item.review_item_id)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>
                </button>
              </div>
            </article>
          </div>
        </section>

        <!-- 全部错题 -->
        <section v-if="mistakes.length">
          <h2 class="mb-4 flex items-center gap-2 text-sm font-semibold">
            <span class="h-2 w-2 rounded-full bg-error" />
            全部错题
            <span class="rounded-full bg-error-soft px-2 py-0.5 text-xs text-error">{{ mistakes.length }}</span>
          </h2>
          <TransitionGroup name="mistake" tag="div" class="space-y-3">
            <article
              v-for="item in mistakes"
              :key="item.review_item_id"
              class="rounded-xl border border-subtle bg-card p-4 transition-all duration-200"
              :class="item.status === 'due' ? 'border-l-2 border-l-warning' : ''"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2 mb-2">
                    <span class="rounded-full bg-error-soft px-2 py-0.5 text-xs font-semibold text-error">{{ errorLabel(item.error_type) }}</span>
                    <span class="text-sm text-text-muted">{{ item.node_title || item.node_id }}</span>
                    <span class="ml-auto text-[10px] text-text-muted">{{ statusLabel(item.status) }}</span>
                  </div>
                  <p class="text-sm leading-6 text-text-primary">{{ item.question_prompt }}</p>
                  <div class="mt-3 space-y-1.5 text-sm">
                    <div class="text-text-muted">你的答案：<span class="text-error font-medium">{{ item.original_answer || '未作答' }}</span></div>
                    <div class="text-text-muted">正确答案：<span class="text-success font-medium">{{ item.correct_answer }}</span></div>
                  </div>
                  <p v-if="item.explanation" class="mt-2 rounded-lg bg-[#FAFCFB] px-3 py-2 text-sm leading-6 text-text-secondary">
                    <span class="font-semibold text-text-muted">解析：</span>{{ item.explanation }}
                  </p>
                </div>
                <button type="button" class="focus-ring shrink-0 rounded-lg p-1.5 text-text-muted hover:text-error hover:bg-error-soft transition-colors" title="删除" @click="removeItem(item.review_item_id)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>
                </button>
              </div>
            </article>
          </TransitionGroup>
        </section>

        <!-- 强化任务 -->
        <section v-if="reinforcementTasks.length" class="mt-8">
          <h2 class="mb-4 flex items-center gap-2 text-sm font-semibold">
            <span class="h-2 w-2 rounded-full bg-info" />
            掌握强化
            <span class="rounded-full bg-info-soft px-2 py-0.5 text-xs text-info-dark">{{ reinforcementTasks.length }}</span>
          </h2>
          <div class="space-y-3">
            <article
              v-for="item in reinforcementTasks"
              :key="item.review_item_id"
              class="rounded-xl border border-subtle bg-card p-4 transition-all duration-300"
              :class="removingIds.includes(item.review_item_id) ? 'opacity-0 translate-x-4 scale-95' : ''"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2 mb-2">
                    <span class="rounded-full bg-info-soft px-2 py-0.5 text-[10px] font-semibold text-info-dark">强化</span>
                    <span class="text-sm text-text-muted">{{ item.node_title || item.node_id }}</span>
                  </div>
                  <p class="text-sm leading-6 text-text-primary">{{ item.question_prompt }}</p>
                </div>
                <button type="button" class="focus-ring shrink-0 rounded-lg p-1.5 text-text-muted hover:text-error hover:bg-error-soft transition-colors" title="删除" @click="removeItem(item.review_item_id)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>
                </button>
              </div>
            </article>
          </div>
        </section>

        <!-- 空 -->
        <div v-if="!mistakes.length && !todayQueue.length && !reinforcementTasks.length" class="flex flex-col items-center justify-center py-20 text-center">
          <div class="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-success-soft">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--color-success)" stroke-width="1.5" stroke-linecap="round">
              <path d="M20 6L9 17l-5-5" />
            </svg>
          </div>
          <h2 class="text-base font-bold text-text-primary">没有错题记录</h2>
          <p class="mt-2 text-sm text-text-muted">继续学习，提交诊断测验后会在这里看到需要复习的题目。</p>
        </div>
      </template>
    </main>

    <aside class="hidden lg:flex flex-col shrink-0 border-l border-subtle" style="width:360px">
      <div class="px-4 pt-3 pb-2 shrink-0">
        <p class="text-xs font-semibold text-text-muted">错题辅导</p>
      </div>
      <div class="flex-1 min-h-0">
        <ChatArea :messages="tutorMessages" :busy="tutorBusy" :node-title="'错题复习'" :boot-mode="'ready'" session-id="student:data_structures" node-id="N01" :suggestions="tutorSuggestions" @send="onTutorSend" />
      </div>
    </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import ChatArea from "../components/ChatArea.vue";
import apiClient from "../services/apiClient";

const router = useRouter();
const loading = ref(true);
const error = ref("");
const dashboard = ref({ mistakes: [], today_queue: [], reinforcement_tasks: [] });
const removingIds = ref([]);
const retestOpen = ref(false);

function onDocClick() { retestOpen.value = false; }
onMounted(() => document.addEventListener("click", onDocClick));
onBeforeUnmount(() => document.removeEventListener("click", onDocClick));

const mistakes = computed(() => dashboard.value.mistakes || []);
const todayQueue = computed(() => dashboard.value.today_queue || []);
const reinforcementTasks = computed(() => dashboard.value.reinforcement_tasks || []);
const totalCount = computed(() => mistakes.value.length + reinforcementTasks.value.length);

const tutorMessages = ref([]);
const tutorBusy = ref(false);
const tutorSuggestions = [
  "这道题考察了什么知识点？",
  "帮我分析一下这个错题的错误原因",
  "请出一道类似的题目让我巩固一下",
];

function onTutorSend({ text }) {
  const userMsg = { id: `u-${Date.now()}`, role: "user", content: text };
  tutorMessages.value = [...tutorMessages.value, userMsg];
  const aid = `a-${Date.now()}`;
  tutorMessages.value = [...tutorMessages.value, { id: aid, role: "assistant", content: "", isStreaming: true }];
  tutorBusy.value = true;
  apiClient.post(`/sessions/${encodeURIComponent("student:data_structures")}/tutor-stream`, { question: text }, {
    responseType: "stream",
    onDownloadProgress(e) {
      const chunk = e?.event?.target?.response || e?.currentTarget?.response || "";
      chunk.split("\n").filter(l => l.startsWith("data: ")).forEach(line => {
        try {
          const d = JSON.parse(line.slice(6));
          if (d.token) {
            const idx = tutorMessages.value.findIndex(m => m.id === aid);
            if (idx >= 0) { const msgs = [...tutorMessages.value]; msgs[idx] = { ...msgs[idx], content: msgs[idx].content + d.token }; tutorMessages.value = msgs; }
          }
        } catch (_) {}
      });
    },
  }).then(() => {
    const idx = tutorMessages.value.findIndex(m => m.id === aid);
    if (idx >= 0) { const msgs = [...tutorMessages.value]; msgs[idx] = { ...msgs[idx], isStreaming: false }; tutorMessages.value = msgs; }
  }).catch(() => {
    const idx = tutorMessages.value.findIndex(m => m.id === aid);
    if (idx >= 0) { const msgs = [...tutorMessages.value]; msgs[idx] = { ...msgs[idx], isStreaming: false, content: msgs[idx].content || "辅导服务暂不可用。" }; tutorMessages.value = msgs; }
  }).finally(() => { tutorBusy.value = false; });
}

function goBack() { router.push("/app"); }

function goRetest(mode) {
  retestOpen.value = false;
  router.push(`/review/retest?mode=${mode}`);
}

function removeItem(id) {
  removingIds.value.push(id);
  setTimeout(() => {
    dashboard.value.mistakes = dashboard.value.mistakes.filter(item => item.review_item_id !== id);
    dashboard.value.today_queue = dashboard.value.today_queue.filter(item => item.review_item_id !== id);
    dashboard.value.reinforcement_tasks = dashboard.value.reinforcement_tasks.filter(item => item.review_item_id !== id);
    removingIds.value = removingIds.value.filter(rid => rid !== id);
  }, 300);
}

async function fetchData() {
  loading.value = true;
  error.value = "";
  try {
    const sessionId = "student:data_structures";
    const { data } = await apiClient.get(`/sessions/${encodeURIComponent(sessionId)}/review`);
    if (data && data.status === "ok") dashboard.value = data;
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || "加载错题数据失败";
  } finally {
    loading.value = false;
  }
}

function errorLabel(type) {
  if (!type) return "其他";
  const key = String(type).toLowerCase().replace(/[\s-]+/g, "_");
  const map = {
    definition: "概念不清", understanding: "理解有误", application: "不会应用",
    concept: "概念错误", concept_understanding: "概念理解", concept_application: "概念应用",
    syntax_error: "语法错误", wrong_answer: "答案错误", runtime_error: "运行错误",
    time_limit: "超时", internal_error: "系统错误", code_error: "代码错误",
    logic_error: "逻辑错误", memory_limit: "内存超限", output_error: "输出错误",
    compilation_error: "编译错误", semantic_error: "语义错误", incomplete: "未完成",
    boundary: "边界条件", boundary_condition: "边界条件", edge_case: "边界情况",
    design_error: "设计错误", type_error: "类型错误", null_pointer: "空值错误",
    off_by_one: "差一错误", infinite_loop: "死循环", stack_overflow: "栈溢出",
    index_error: "索引错误", key_error: "键值错误", value_error: "数值错误",
    timeout: "超时", resource_error: "资源错误", network_error: "网络错误",
    assertion_error: "断言失败", arithmetic_error: "算术错误", overflow: "溢出",
    underflow: "下溢", precision: "精度问题", rounding: "舍入错误",
  };
  return map[key] || "其他错误";
}
function statusLabel(status) { return status === "due" ? "待复习" : status === "in_progress" ? "复习中" : status === "completed" ? "已完成" : status || ""; }

onMounted(fetchData);
</script>

<style scoped>
.mistake-enter-active { transition: all 300ms cubic-bezier(0.16, 1, 0.3, 1); }
.mistake-leave-active { transition: all 280ms cubic-bezier(0.16, 1, 0.3, 1); }
.mistake-enter-from { opacity: 0; transform: translateY(8px); }
.mistake-leave-to { opacity: 0; transform: translateX(16px) scale(0.96); }
</style>
