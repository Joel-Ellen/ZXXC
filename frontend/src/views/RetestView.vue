<template>
  <div class="retest-page">
    <header class="retest-topbar">
      <div class="retest-topbar__inner">
        <button type="button" class="retest-back focus-ring" @click="goBack">
          <IconArrowLeft />
          返回错题本
        </button>
        <div class="retest-heading">
          <span class="retest-heading__eyebrow">错题复习</span>
          <h1>重刷题目</h1>
        </div>
        <span class="retest-counter">{{ answeredCount }} / {{ questions.length }} 已作答</span>
      </div>
      <div class="retest-progress" aria-hidden="true">
        <span :style="{ width: `${progressPercent}%` }" />
      </div>
    </header>

    <div class="retest-workspace">
      <main class="retest-main">
      <section v-if="loading" class="retest-state" aria-live="polite">
        <div class="retest-spinner" />
        <h2>正在准备新的复测题</h2>
        <p>题目由服务端生成，请稍候。</p>
      </section>

      <section v-else-if="error" class="retest-state retest-state--error" role="alert">
        <div class="retest-state__icon" aria-hidden="true"><IconAlert :size="22" /></div>
        <h2>复测题加载失败</h2>
        <p>{{ error }}</p>
        <button type="button" class="retest-submit focus-ring" @click="loadQuiz">重新加载</button>
      </section>
      <template v-else-if="questions.length">
        <section class="retest-intro">
          <p class="retest-intro__eyebrow">{{ item?.node_title || "当前知识点" }}</p>
          <h2>请完成下面的复测题</h2>
          <p>每道题只选择一个答案。提交后系统会统一判分，并更新本次错题复习结果。</p>
        </section>

        <form class="retest-form" @submit.prevent="submitQuiz">
          <article v-for="(question, index) in questions" :key="question.id" class="retest-question">
            <div class="retest-question__meta">
              <span>第 {{ index + 1 }} 题</span>
              <span v-if="question.skillTag || question.difficulty">{{ [question.skillTag, question.difficulty].filter(Boolean).join(" · ") }}</span>
            </div>
            <h3>{{ question.prompt }}</h3>
            <div class="retest-options" role="radiogroup" :aria-label="`第 ${index + 1} 题选项`">
              <button
                v-for="(option, optionIndex) in question.options"
                :key="`${question.id}-${optionIndex}`"
                type="button"
                class="retest-option focus-ring"
                :class="optionClass(question, optionIndex)"
                :disabled="submitting || submitted"
                role="radio"
                :aria-checked="answers[question.id] === optionIndex"
                @click="selectAnswer(question.id, optionIndex)"
              >
                <span class="retest-option__mark">{{ optionLetter(optionIndex) }}</span>
                <span>{{ option }}</span>
              </button>
            </div>
            <div v-if="submitted && resultFor(question.id)" class="retest-feedback" :class="resultFor(question.id).correct ? 'retest-feedback--correct' : 'retest-feedback--wrong'">
              <strong>{{ resultFor(question.id).correct ? "回答正确" : "需要复习" }}</strong>
              <span v-if="!resultFor(question.id).correct">正确答案：{{ resultFor(question.id).correct_answer || "请查看解析" }}</span>
              <span v-if="resultFor(question.id).explanation">{{ resultFor(question.id).explanation }}</span>
            </div>
          </article>

          <section v-if="submitted" class="retest-result" aria-live="polite">
            <div>
              <span class="retest-result__label">本次得分</span>
              <strong>{{ correctCount }} / {{ questions.length }}</strong>
            </div>
            <p>{{ correctCount === questions.length ? "本次复测已通过，错题状态已更新。" : "部分题目仍需巩固，错题会保留在复习清单中。" }}</p>
          </section>

          <div class="retest-submit-row">
            <p v-if="submitError" class="retest-submit-error" role="alert">{{ submitError }}</p>
            <button type="submit" class="retest-submit focus-ring" :disabled="submitting || submitted || answeredCount !== questions.length">
              {{ submitting ? "正在判分..." : submitted ? "已提交" : "提交答案" }}
            </button>
          </div>
        </form>
      </template>

      <section v-else class="retest-state">
        <h2>暂时没有可刷的题目</h2>
        <p>返回错题本后可以选择其他复习任务。</p>
        <button type="button" class="retest-submit focus-ring" @click="goBack">返回错题本</button>
      </section>
      </main>

      <aside class="retest-tutor-sidebar">
        <div class="retest-tutor-sidebar__header">
          <p>错题辅导</p>
        </div>
        <div class="retest-tutor-sidebar__body">
          <ChatArea
            :messages="tutorMessages"
            :busy="tutorBusy"
            :node-title="'错题复习'"
            :boot-mode="'ready'"
            session-id="student:data_structures"
            node-id="N01"
            :suggestions="tutorSuggestions"
            @send="onTutorSend"
          />
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import ChatArea from "../components/ChatArea.vue";
import IconAlert from "../components/icons/IconAlert.vue";
import IconArrowLeft from "../components/icons/IconArrowLeft.vue";
import {
  fetchSessionReviewDashboard,
  fetchSessionResources,
  streamSessionTutorWithReconnect,
  submitSessionLearningEvent,
} from "../services/eduAgentApi";

const REVIEW_SESSION_ID = "student:data_structures";
const router = useRouter();
const route = useRoute();
const sessionId = "student:data_structures";
const loading = ref(true);
const error = ref("");
const submitError = ref("");
const item = ref(null);
const questions = ref([]);
const answers = ref({});
const results = ref([]);
const submitting = ref(false);
const submitted = ref(false);
const resourceId = ref("");
const nodeId = ref(String(route.query.nodeId || ""));
let tutorAbortController = null;

onBeforeUnmount(() => tutorAbortController?.abort());

const answeredCount = computed(() => Object.keys(answers.value).length);
const progressPercent = computed(() => questions.value.length ? Math.round(answeredCount.value / questions.value.length * 100) : 0);
const correctCount = computed(() => results.value.filter((result) => result.correct).length);

function optionLetter(index) {
  return String.fromCharCode(65 + index);
}

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

function selectAnswer(questionId, optionIndex) {
  answers.value = { ...answers.value, [questionId]: optionIndex };
}

function optionClass(question, optionIndex) {
  if (!submitted.value) return answers.value[question.id] === optionIndex ? "retest-option--selected" : "";
  const result = resultFor(question.id);
  if (!result) return answers.value[question.id] === optionIndex ? "retest-option--selected" : "";
  if (result.correct_index === optionIndex) return "retest-option--correct";
  if (!result.correct && answers.value[question.id] === optionIndex) return "retest-option--wrong";
  return "";
}

function resultFor(questionId) {
  return results.value.find((result) => String(result.question_id) === String(questionId));
}

function resourceList(response) {
  return response?.resources || response?.existing_resources || response?.data?.resources || response?.data?.existing_resources || [];
}

function questionList(card) {
  const payload = card?.structured_payload || card?.metadata?.structured_payload || card?.metadata || {};
  const raw = Array.isArray(payload.questions) ? payload.questions : [];
  return raw
    .map((question, index) => ({
      id: String(question.id || question.question_id || `question-${index + 1}`),
      prompt: String(question.prompt || question.question || "").trim(),
      options: Array.isArray(question.options) ? question.options.map((option) => String(option)) : [],
      skillTag: question.skill_tag || question.skillTag || "",
      difficulty: question.difficulty || "",
    }))
    .filter((question) => question.prompt && question.options.length >= 2);
}

async function loadQuiz() {
  loading.value = true;
  error.value = "";
  submitError.value = "";
  submitted.value = false;
  results.value = [];
  answers.value = {};
  try {
    const dashboard = await fetchSessionReviewDashboard(sessionId);
    const allItems = [
      ...(Array.isArray(dashboard?.mistakes) ? dashboard.mistakes : []),
    ];
    const requestedItemId = String(route.query.reviewItem || "");
    item.value = allItems.find((candidate) => candidate.review_item_id === requestedItemId)
      || allItems.find((candidate) => candidate.status !== "completed")
      || null;
    nodeId.value = String(route.query.nodeId || item.value?.node_id || "");
    if (!nodeId.value) throw new Error("缺少复测知识点，请返回错题本重新进入。");

    const response = await fetchSessionResources(sessionId, nodeId.value);
    const cards = resourceList(response).filter((card) => (
      String(card?.resource_type || card?.card_type || card?.type || "") === "diagnostic_quiz"
    ));
    const requestedResourceId = String(route.query.resourceId || item.value?.retest_resource_id || "");
    const card = cards.find((candidate) => String(candidate.resource_id || "") === requestedResourceId) || cards[0];
    if (!card) throw new Error("新的复测题暂未准备好，请返回后重新点击重刷。");
    resourceId.value = String(card.resource_id || requestedResourceId);
    questions.value = questionList(card);
    if (!questions.value.length) throw new Error("复测题暂时没有可作答的选项，请稍后重试。");
  } catch (requestError) {
    error.value = requestError?.response?.data?.detail || requestError?.message || "复测题加载失败，请稍后重试。";
  } finally {
    loading.value = false;
  }
}

async function submitQuiz() {
  if (answeredCount.value !== questions.value.length || submitting.value || submitted.value) return;
  submitting.value = true;
  submitError.value = "";
  try {
    const response = await submitSessionLearningEvent(sessionId, {
      event_type: "review_completed",
      node_id: nodeId.value,
      resource_id: resourceId.value,
      attempt_number: 1,
      result: {
        evidence_type: "diagnostic_quiz",
        answers: questions.value.map((question) => ({
          question_id: question.id,
          answer_index: answers.value[question.id],
        })),
      },
    });
    const evidence = response?.verified_evidence || response?.event?.verified_evidence || {};
    results.value = Array.isArray(evidence.question_results) ? evidence.question_results : [];
    submitted.value = true;
  } catch (requestError) {
    submitError.value = requestError?.response?.data?.detail || requestError?.message || "提交失败，请稍后重试。";
  } finally {
    submitting.value = false;
  }
}

function goBack() {
  router.push({ name: "review" });
}

onMounted(loadQuiz);
</script>

<style scoped>
.retest-page {
  min-height: 100vh;
  color: var(--text-primary);
  background: var(--space-bg);
}

.retest-topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  border-bottom: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--space-panel) 96%, transparent);
  backdrop-filter: blur(18px);
}

.retest-topbar__inner,
.retest-progress,
.retest-main {
  width: min(100% - 40px, 820px);
  margin: 0 auto;
}

.retest-topbar__inner {
  min-height: 76px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.retest-back {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 0;
  color: var(--text-secondary);
  background: transparent;
  font-size: 13px;
  cursor: pointer;
}

.retest-back svg {
  width: 17px;
  height: 17px;
}

.retest-heading {
  flex: 1;
  text-align: center;
}

.retest-heading__eyebrow {
  color: var(--text-muted);
  font-size: 11px;
}

.retest-heading h1 {
  margin: 3px 0 0;
  font-size: 20px;
  font-weight: 800;
}

.retest-counter {
  min-width: 94px;
  color: var(--text-muted);
  font-size: 12px;
  text-align: right;
}

.retest-progress {
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--card-bg-hover);
}

.retest-progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--color-primary);
  transition: width 220ms ease;
}

.retest-main {
  padding: 48px 0 72px;
}

.retest-workspace {
  display: flex;
  align-items: stretch;
  width: min(100% - 40px, 1200px);
  min-height: calc(100vh - 80px);
  margin: 0 auto;
}

.retest-workspace > .retest-main {
  flex: 1 1 auto;
  width: auto;
  min-width: 0;
  margin: 0;
  padding-right: 28px;
}

.retest-tutor-sidebar {
  display: flex;
  flex: 0 0 360px;
  flex-direction: column;
  min-height: 0;
  border-left: 1px solid var(--border-subtle);
  background: var(--space-panel);
}

.retest-tutor-sidebar__header {
  flex: 0 0 auto;
  padding: 16px 18px 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.retest-tutor-sidebar__header p {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
}

.retest-tutor-sidebar__body {
  flex: 1 1 auto;
  min-height: 0;
}

.retest-intro {
  margin-bottom: 28px;
}

.retest-intro__eyebrow {
  margin: 0 0 8px;
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 700;
}

.retest-intro h2 {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
}

.retest-intro > p:last-child {
  margin: 10px 0 0;
  color: var(--text-muted);
  font-size: 14px;
  line-height: 1.7;
}

.retest-form {
  display: grid;
  gap: 16px;
}

.retest-question {
  padding: 24px;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background: var(--space-surface);
}

.retest-question__meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-muted);
  font-size: 12px;
}

.retest-question__meta span:first-child {
  color: var(--color-primary);
  font-weight: 700;
}

.retest-question h3 {
  margin: 14px 0 20px;
  color: var(--text-primary);
  font-size: 17px;
  font-weight: 700;
  line-height: 1.7;
}

.retest-options {
  display: grid;
  gap: 10px;
}

.retest-option {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 13px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: 9px;
  color: var(--text-secondary);
  background: var(--space-panel);
  font-size: 14px;
  line-height: 1.6;
  text-align: left;
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease, color 160ms ease;
}

.retest-option:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--color-primary) 55%, var(--border-subtle));
  background: var(--card-bg-hover);
}

.retest-option__mark {
  width: 24px;
  height: 24px;
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 1px solid currentColor;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 700;
}

.retest-option--selected {
  border-color: var(--color-primary);
  color: var(--color-primary-dark);
  background: var(--color-primary-soft);
}

.retest-option--correct {
  border-color: var(--color-success);
  color: var(--color-success-dark);
  background: var(--color-success-soft);
}

.retest-option--wrong {
  border-color: var(--color-error);
  color: var(--color-error-dark);
  background: var(--color-error-soft);
}

.retest-feedback {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  margin-top: 16px;
  padding: 12px 14px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.6;
}

.retest-feedback--correct {
  color: var(--color-success-dark);
  background: var(--color-success-soft);
}

.retest-feedback--wrong {
  color: var(--color-error-dark);
  background: var(--color-error-soft);
}

.retest-result {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 24px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 30%, var(--border-subtle));
  border-radius: 12px;
  background: var(--color-primary-soft);
}

.retest-result__label {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.retest-result strong {
  display: block;
  margin-top: 4px;
  color: var(--color-primary-dark);
  font-size: 24px;
}

.retest-result p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.retest-submit-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  min-height: 48px;
}

.retest-submit-error {
  flex: 1;
  margin: 0;
  color: var(--color-error-dark);
  font-size: 12px;
}

.retest-submit {
  min-width: 126px;
  min-height: 42px;
  padding: 0 18px;
  border: 0;
  border-radius: 9px;
  color: var(--color-primary-text);
  background: var(--color-primary);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.retest-submit:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.retest-state {
  min-height: 360px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
}

.retest-state h2,
.retest-state p {
  margin: 0;
}

.retest-state h2 {
  font-size: 20px;
}

.retest-state p {
  color: var(--text-muted);
  font-size: 13px;
}

.retest-state__icon {
  width: 38px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: var(--color-error-dark);
  background: var(--color-error-soft);
  font-weight: 800;
}

.retest-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--border-subtle);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: retest-spin 800ms linear infinite;
}

@keyframes retest-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 640px) {
  .retest-topbar__inner,
  .retest-progress,
  .retest-main {
    width: min(100% - 28px, 820px);
  }

  .retest-topbar__inner {
    min-height: 68px;
    gap: 10px;
  }

  .retest-back {
    font-size: 0;
  }

  .retest-back svg {
    width: 19px;
    height: 19px;
  }

  .retest-counter {
    min-width: 80px;
    font-size: 11px;
  }

  .retest-main {
    padding-top: 32px;
  }

  .retest-workspace {
    width: min(100% - 28px, 820px);
  }

  .retest-workspace > .retest-main {
    width: 100%;
    padding-right: 0;
  }

  .retest-tutor-sidebar {
    display: none;
  }

  .retest-intro h2 {
    font-size: 24px;
  }

  .retest-question {
    padding: 18px;
  }

  .retest-question h3 {
    font-size: 16px;
  }

  .retest-result {
    align-items: flex-start;
    flex-direction: column;
  }

  .retest-submit-row {
    align-items: stretch;
    flex-direction: column;
  }

  .retest-submit-error {
    flex: initial;
  }
}
</style>
