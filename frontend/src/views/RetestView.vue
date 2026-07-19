<template>
  <div class="h-screen flex flex-col" :style="{ background: 'var(--space-bg)', color: 'var(--text-primary)' }">
    <header class="sticky top-0 z-20 border-b border-subtle backdrop-blur-lg shrink-0" style="background:color-mix(in srgb, var(--space-panel) 96%, transparent);min-height:4rem">
      <div class="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
        <div class="flex items-center gap-4">
          <button type="button" class="focus-ring rounded-lg px-3 py-1.5 text-sm font-medium text-text-secondary hover:text-text-primary transition-colors" @click="goBack">&larr; 返回错题本</button>
          <div class="flex items-center gap-2">
            <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-[10px] font-black text-primary-text">练</span>
            <h1 class="text-base font-bold text-text-primary">重新刷题</h1>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" class="focus-ring rounded-lg border border-subtle px-3 py-1.5 text-xs text-text-secondary hover:text-primary transition-colors" @click="resetAll" v-if="allQuestions.length">全部重置</button>
          <span class="text-sm text-text-muted ml-2">{{ visibleCount }} / {{ allQuestions.length }} 题</span>
        </div>
      </div>
      <div class="mx-auto max-w-6xl px-5 pb-3">
        <div class="h-1 rounded-full bg-card-hover overflow-hidden">
          <div class="h-full rounded-full bg-primary transition-all duration-700" :style="{ width: progressPercent + '%' }" />
        </div>
      </div>
    </header>

    <div class="flex-1 flex min-h-0">
    <main class="flex-1 overflow-y-auto">
      <div v-if="!allQuestions.length" class="flex flex-col items-center justify-center py-20 text-center">
        <p class="text-text-muted">没有可刷的题目</p>
        <button type="button" class="focus-ring mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-text" @click="goBack">返回</button>
      </div>

      <TransitionGroup name="question" tag="div" class="mx-auto max-w-2xl px-5 py-6 space-y-4">
        <article
          v-for="q in visibleQuestions"
          :key="q.review_item_id"
          class="rounded-xl border border-subtle bg-card p-5 transition-all duration-300"
        >
          <div class="flex flex-wrap items-center gap-2 mb-3">
            <span class="rounded-full bg-error-soft px-2 py-0.5 text-xs font-semibold text-error">{{ labelMap[q.error_type] || '错题' }}</span>
            <span class="text-sm text-text-muted">{{ q.node_title || q.node_id }}</span>
            <span class="ml-auto text-xs text-text-muted">#{{ allQuestions.indexOf(q) + 1 }}</span>
          </div>

          <p class="text-sm font-medium text-text-primary leading-6 mb-4">{{ q.question_prompt }}</p>

          <div class="flex items-center gap-2">
            <button v-if="!q._revealed" type="button" class="focus-ring rounded-lg border border-subtle px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-card-hover transition-colors" @click="q._revealed = true">显示答案</button>
            <span v-else class="text-xs text-success font-medium">已显示</span>
            <button v-if="!q._skipped" type="button" class="focus-ring rounded-lg border border-subtle px-3 py-1.5 text-xs text-text-muted hover:text-error hover:border-error/30 transition-colors ml-auto" @click="skipQuestion(q)">跳过</button>
          </div>

          <Transition name="reveal">
            <div v-if="q._revealed" class="mt-4 rounded-lg bg-[#FAFCFB] p-3 text-sm leading-6 text-text-secondary">
              <span class="font-semibold text-text-muted">正确答案：</span>
              <span class="text-success font-medium">{{ q.correct_answer || '' }}</span>
            </div>
          </Transition>
        </article>
      </TransitionGroup>

      <div v-if="allQuestions.length && visibleCount === 0" class="text-center py-8">
        <p class="text-text-muted text-sm">全部完成</p>
      </div>
    </main>

    <!-- 右侧固定辅导面板 -->
    <aside class="tutor-sidebar hidden lg:flex flex-col shrink-0 border-l border-subtle" style="width:360px">
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
import { computed, onBeforeUnmount, ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import apiClient from "../services/apiClient";
import { streamSessionTutorWithReconnect } from "../services/eduAgentApi";
import ChatArea from "../components/ChatArea.vue";

const REVIEW_SESSION_ID = "student:data_structures";
const router = useRouter();
const route = useRoute();
const allQuestions = ref([]);
let tutorAbortController = null;

onBeforeUnmount(() => tutorAbortController?.abort());

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
const labelMap = new Proxy({}, { get: (_, key) => errorLabel(key) });

const visibleQuestions = computed(() => allQuestions.value.filter(q => !q._skipped));
const visibleCount = computed(() => visibleQuestions.value.length);
const progressPercent = computed(() => allQuestions.value.length ? Math.round((allQuestions.value.length - visibleQuestions.value.length) / allQuestions.value.length * 100) : 0);

// 辅导面板
const tutorMessages = ref([]);
const tutorBusy = ref(false);
const tutorSuggestions = [
  "这道题考察了什么知识点？",
  "帮我分析一下错题的错误原因",
  "请出一道类似的题目让我巩固一下",
];

function patchTutorMessage(messageId, fields) {
  const index = tutorMessages.value.findIndex((message) => message.id === messageId);
  if (index < 0) return;
  const messages = [...tutorMessages.value];
  messages[index] = { ...messages[index], ...fields };
  tutorMessages.value = messages;
}

async function onTutorSend({ text }) {
  const question = String(text || "").trim();
  if (!question || tutorBusy.value) return;
  const userMsg = { id: `u-${Date.now()}`, role: "user", content: question };
  tutorMessages.value = [...tutorMessages.value, userMsg];
  const aid = `a-${Date.now()}`;
  tutorMessages.value = [...tutorMessages.value, { id: aid, role: "assistant", content: "", isStreaming: true }];
  tutorBusy.value = true;
  const controller = new AbortController();
  tutorAbortController = controller;
  let accumulated = "";
  const fail = (error) => patchTutorMessage(aid, {
    content: accumulated || (error?.status === 401 ? "登录状态已失效，请重新登录。" : "辅导服务暂不可用。"),
    isStreaming: false,
    streamStatus: "error",
  });

  try {
    await streamSessionTutorWithReconnect(REVIEW_SESSION_ID, { question }, {
      signal: controller.signal,
      onToken(token) {
        accumulated += token;
        patchTutorMessage(aid, { content: accumulated });
      },
      onReset() {
        accumulated = "";
        patchTutorMessage(aid, { content: "" });
      },
      onDone() {
        patchTutorMessage(aid, { isStreaming: false, streamStatus: "complete" });
      },
      onError: fail,
    });
  } catch (error) {
    fail(error);
  } finally {
    if (tutorAbortController === controller) tutorAbortController = null;
    tutorBusy.value = false;
  }
}

async function loadQuestions() {
  const mode = route.query.mode || "all";
  try {
    const sessionId = "student:data_structures";
    const { data } = await apiClient.get(`/sessions/${encodeURIComponent(sessionId)}/review`);
    if (data && data.status === "ok") {
      const raw = mode === "today" ? (data.today_queue || []) : [...(data.mistakes || []), ...(data.reinforcement_tasks || [])];
      allQuestions.value = raw.map(q => ({ ...q, _revealed: false, _skipped: false }));
    }
  } catch {
    allQuestions.value = [];
  }
}

function skipQuestion(q) { q._skipped = true; }
function resetAll() { allQuestions.value.forEach(q => { q._revealed = false; q._skipped = false; }); }
function goBack() { router.push("/review"); }

loadQuestions();
</script>

<style scoped>
.question-enter-active { transition: all 400ms cubic-bezier(0.16, 1, 0.3, 1); }
.question-leave-active { transition: all 300ms cubic-bezier(0.16, 1, 0.3, 1); }
.question-enter-from { opacity: 0; transform: translateY(12px) scale(0.98); }
.question-leave-to { opacity: 0; transform: translateX(-20px); }

.reveal-enter-active { transition: all 350ms cubic-bezier(0.16, 1, 0.3, 1); }
.reveal-leave-active { transition: all 200ms cubic-bezier(0.16, 1, 0.3, 1); }
.reveal-enter-from { opacity: 0; max-height: 0; overflow: hidden; }
.reveal-enter-to { opacity: 1; max-height: 200px; }
.reveal-leave-from { opacity: 1; max-height: 200px; }
.reveal-leave-to { opacity: 0; max-height: 0; overflow: hidden; }

@media (max-width: 1023px) {
  aside { display: none !important; }
}
</style>
