<template>
  <section class="code-practice-panel" :aria-busy="isBusy ? 'true' : 'false'" aria-label="代码练习">
    <header class="code-practice-panel__header">
      <div class="min-w-0">
        <p class="code-practice-panel__eyebrow">代码练习</p>
        <h3 class="code-practice-panel__title">{{ problemTitle }}</h3>
      </div>
      <span class="code-practice-panel__state" :class="`is-${practiceState}`">
        {{ practiceStateLabel }}
      </span>
    </header>

    <div v-if="practiceState === 'loading'" class="code-practice-panel__loading" role="status" aria-live="polite">
      <span class="code-practice-panel__loading-line is-wide" />
      <span class="code-practice-panel__loading-line" />
      <span class="code-practice-panel__loading-editor" />
    </div>

    <div v-else-if="practiceState === 'not_configured' || practiceState === 'error'" class="code-practice-panel__empty" role="status" aria-live="polite">
      <p class="code-practice-panel__empty-title">
        {{ practiceState === 'not_configured' ? '该资源暂无可执行练习' : '无法加载练习' }}
      </p>
      <p class="code-practice-panel__empty-detail">{{ practiceLoadError }}</p>
      <button
        type="button"
        class="workspace-shell-btn focus-ring px-3 py-2 text-[11px] font-semibold"
        :disabled="isBusy"
        @click="loadPracticeProblem"
      >
        重新加载
      </button>
    </div>

    <div v-else-if="practiceState === 'ready'" class="space-y-4">
      <section v-if="problemPrompt" class="code-practice-panel__prompt">
        <p>{{ problemPrompt }}</p>
        <p v-if="problemConstraints" class="code-practice-panel__constraints">{{ problemConstraints }}</p>
      </section>

      <div class="code-practice-panel__workspace">
        <div class="code-practice-panel__editor-region">
          <div class="code-practice-panel__editor-toolbar">
            <span class="font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-300">
              {{ languageLabel }}
            </span>
            <span class="code-practice-panel__draft-status" aria-live="polite">{{ draftStatus }}</span>
          </div>

          <div
            ref="editorHost"
            class="code-practice-panel__editor"
            aria-label="代码编辑器"
          />

          <div class="code-practice-panel__actions">
            <div class="flex flex-wrap items-center gap-2">
              <button
                type="button"
                class="workspace-shell-btn workspace-shell-btn--secondary focus-ring px-3.5 py-2 text-[11px] font-semibold"
                :disabled="!canExecute"
                @click="execute('run')"
              >
                {{ activeAction === 'run' ? '运行中...' : '运行公开测试' }}
              </button>
              <button
                type="button"
                class="workspace-shell-btn workspace-shell-btn--accent focus-ring px-3.5 py-2 text-[11px] font-semibold"
                :disabled="!canExecute"
                @click="execute('submit')"
              >
                {{ activeAction === 'submit' ? '提交中...' : '提交全部测试' }}
              </button>
            </div>
            <button
              type="button"
              class="workspace-shell-btn focus-ring px-3 py-2 text-[11px] font-semibold text-text-secondary"
              :disabled="isBusy"
              @click="resetDraft"
            >
              重置
            </button>
          </div>
        </div>

        <aside class="code-practice-panel__results" aria-label="测试结果">
          <section class="code-practice-panel__test-overview">
            <div>
              <p class="code-practice-panel__section-label">公开测试</p>
              <p class="code-practice-panel__section-value">{{ publicTestSummary }}</p>
            </div>
            <div>
              <p class="code-practice-panel__section-label">隐藏测试</p>
              <p class="code-practice-panel__section-value">{{ hiddenTestSummary }}</p>
            </div>
          </section>

          <section v-if="publicSpecificationTests.length" class="code-practice-panel__test-list" aria-label="公开测试用例">
            <p class="code-practice-panel__section-label">公开用例</p>
            <article
              v-for="(test, index) in publicSpecificationTests"
              :key="`spec-${test.id || index}`"
              class="code-practice-panel__test-case"
            >
              <p class="code-practice-panel__test-name">{{ testName(test, index) }}</p>
              <dl class="code-practice-panel__test-data">
                <template v-if="hasValue(test.input)">
                  <dt>输入</dt><dd>{{ formatValue(test.input) }}</dd>
                </template>
                <template v-if="hasValue(test.expected)">
                  <dt>期望</dt><dd>{{ formatValue(test.expected) }}</dd>
                </template>
              </dl>
            </article>
          </section>

          <section v-if="execution" class="code-practice-panel__execution" aria-live="polite">
            <div class="code-practice-panel__verdict-row">
              <div>
                <p class="code-practice-panel__section-label">{{ execution.mode === 'submit' ? '提交结果' : '运行结果' }}</p>
                <p class="code-practice-panel__verdict" :class="`is-${executionVerdict}`">
                  {{ verdictLabel(executionVerdict) }}
                </p>
              </div>
              <dl class="code-practice-panel__metrics">
                <div>
                  <dt>运行时间</dt>
                  <dd>{{ metricValue(execution.runtime_ms, 'ms') }}</dd>
                </div>
                <div>
                  <dt>内存</dt>
                  <dd>{{ metricValue(execution.memory_kb, 'KB') }}</dd>
                </div>
              </dl>
            </div>

            <p v-if="executionMessage" class="code-practice-panel__execution-message">{{ executionMessage }}</p>

            <div v-if="executionTests.length" class="code-practice-panel__test-list">
              <article
                v-for="(test, index) in executionTests"
                :key="`result-${test.id || index}`"
                class="code-practice-panel__test-case"
              >
                <div class="flex items-center justify-between gap-3">
                  <p class="code-practice-panel__test-name">{{ testName(test, index) }}</p>
                  <span class="code-practice-panel__test-verdict" :class="test.passed ? 'is-passed' : 'is-failed'">
                    {{ test.passed ? '通过' : verdictLabel(test.verdict) }}
                  </span>
                </div>
                <p v-if="test.message" class="code-practice-panel__test-message">{{ test.message }}</p>
                <dl v-if="test.visibility === 'public'" class="code-practice-panel__test-data">
                  <template v-if="hasValue(test.input)">
                    <dt>输入</dt><dd>{{ formatValue(test.input) }}</dd>
                  </template>
                  <template v-if="hasValue(test.expected)">
                    <dt>期望</dt><dd>{{ formatValue(test.expected) }}</dd>
                  </template>
                  <template v-if="hasValue(test.actual)">
                    <dt>实际</dt><dd>{{ formatValue(test.actual) }}</dd>
                  </template>
                </dl>
              </article>
            </div>
          </section>

          <p v-else-if="executionError" class="code-practice-panel__execution-message" role="alert">{{ executionError }}</p>
          <p v-else class="code-practice-panel__result-placeholder">运行或提交后在此查看结果。</p>
        </aside>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { history, historyKeymap, defaultKeymap, indentWithTab } from "@codemirror/commands";
import { cpp } from "@codemirror/lang-cpp";
import { EditorState } from "@codemirror/state";
import { oneDark } from "@codemirror/theme-one-dark";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import {
  fetchSessionPracticeProblem,
  runSessionPractice,
  submitSessionPractice,
} from "../services/eduAgentApi";
import { useLearningAssetsStore } from "../stores/learningAssets";
import {
  CODE_LANGUAGE,
  CODE_LANGUAGE_LABEL,
  normalizeCodeLanguage,
} from "../utils/codeExample.js";

const props = defineProps({
  sessionId: { type: String, default: "" },
  nodeId: { type: String, default: "" },
  resourceId: { type: String, required: true },
  problemId: { type: String, default: "" },
  starterCode: { type: String, default: "" },
  language: { type: String, default: CODE_LANGUAGE },
});

const emit = defineEmits(["code-run", "code-submitted"]);

const learningAssets = useLearningAssetsStore();
const editorHost = ref(null);
const practiceProblem = ref(null);
const practiceState = ref("loading");
const practiceLoadError = ref("");
const code = ref("");
const execution = ref(null);
const executionError = ref("");
const activeAction = ref("");
const draftSavedAt = ref(0);
const draftStorageUnavailable = ref(false);
const runAttempts = ref(0);
const submitAttempts = ref(0);
const draftContext = ref(null);
const draftDirty = ref(false);
const restoredRemoteDraftKey = ref("");

let editorView = null;
let loadingGeneration = 0;
let executionGeneration = 0;
let draftSaveTimer = null;
let suppressDraftChangeTracking = false;

const VERDICT_LABELS = {
  accepted: "通过",
  wrong_answer: "答案错误",
  syntax_error: "语法错误",
  runtime_error: "运行错误",
  time_limit: "超时",
  internal_error: "判题服务错误",
  sandbox_unavailable: "隔离运行时不可用",
  invalid_request: "请求无效",
};

const isBusy = computed(() => practiceState.value === "loading" || Boolean(activeAction.value));
const isProblemReady = computed(() => practiceState.value === "ready" && Boolean(practiceProblem.value));
const canExecute = computed(() => isProblemReady.value && !activeAction.value && Boolean(code.value.trim()));
const resolvedLanguage = computed(() => normalizeCodeLanguage(
  practiceProblem.value?.language || props.language,
));
const languageLabel = computed(() => CODE_LANGUAGE_LABEL);
const problemTitle = computed(() => firstString(practiceProblem.value?.title, "编程练习"));
const problemPrompt = computed(() => firstString(
  practiceProblem.value?.prompt,
  practiceProblem.value?.description,
  practiceProblem.value?.statement,
));
const problemConstraints = computed(() => firstString(practiceProblem.value?.constraints));
const publicSpecificationTests = computed(() => testArray(
  practiceProblem.value?.public_tests,
  practiceProblem.value?.public_test_cases,
  practiceProblem.value?.test_cases,
));
const executionTests = computed(() => testArray(execution.value?.tests));
const executionVerdict = computed(() => firstString(
  execution.value?.verdict,
  execution.value?.status,
  "internal_error",
));
const hasVerifiedExecution = computed(() => execution.value?.status === "ok");
const publicTestCount = computed(() => countValue(
  practiceProblem.value?.public_test_count,
  practiceProblem.value?.public_tests_count,
  publicSpecificationTests.value.length,
));
const hiddenTestCount = computed(() => countValue(
  practiceProblem.value?.hidden_test_count,
  practiceProblem.value?.hidden_tests_count,
));
const publicTestSummary = computed(() => hasVerifiedExecution.value
  ? summaryValue(
    execution.value?.summary?.public_total,
    executionTests.value.filter((test) => test.visibility === "public").length || null,
    publicTestCount.value,
  )
  : countSummary(publicTestCount.value));
const hiddenTestSummary = computed(() => hasVerifiedExecution.value
  ? summaryValue(
    execution.value?.summary?.hidden_total,
    executionTests.value.filter((test) => test.visibility === "hidden").length || null,
    hiddenTestCount.value,
  )
  : countSummary(hiddenTestCount.value));
const practiceStateLabel = computed(() => ({
  loading: "加载中",
  ready: "可练习",
  not_configured: "尚未配置",
  error: "加载失败",
}[practiceState.value] || "加载中"));
const draftStatus = computed(() => {
  if (draftStorageUnavailable.value) return "草稿无法保存";
  if (!draftSavedAt.value) return "草稿会自动保存";
  return `草稿已保存 ${formatSavedTime(draftSavedAt.value)}`;
});
const executionMessage = computed(() => firstString(
  execution.value?.message,
  typeof execution.value?.detail === "string" ? execution.value.detail : "",
  execution.value?.detail?.message,
));

watch(
  () => [props.sessionId, props.nodeId, props.resourceId, props.problemId, props.starterCode, props.language],
  () => {
    void loadPracticeProblem();
  },
  { immediate: true },
);

watch(
  [() => learningAssets.hydrated, () => learningAssets.sessionId],
  () => {
    restoreSynchronizedDraft();
  },
);

onMounted(() => {
  installEditor();
  syncEditorDocument();
});

onBeforeUnmount(() => {
  flushPendingDraft();
  destroyEditor();
});

function firstString(...values) {
  return values.find((value) => typeof value === "string" && value.trim())?.trim() || "";
}

function countValue(...values) {
  for (const value of values) {
    const numeric = Number(value);
    if (Number.isFinite(numeric) && numeric >= 0) return numeric;
  }
  return null;
}

function countSummary(count) {
  return count === null ? "未公布数量" : `${count} 项`;
}

function summaryValue(...values) {
  const count = countValue(...values);
  return count === null ? "未公布数量" : `${count} 项`;
}

function testArray(...values) {
  const tests = values.find(Array.isArray);
  return tests ? tests.filter((test) => test && typeof test === "object") : [];
}

function normalizedText(value) {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "";
}

function resolvedProblemVersion() {
  return normalizedText(
    practiceProblem.value?.version
      ?? practiceProblem.value?.problem_version
      ?? practiceProblem.value?.version_id,
  ) || "current";
}

function hashDraftIdentity(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function assetKeySegment(value) {
  const raw = normalizedText(value) || "unknown";
  const readable = raw.replace(/[^A-Za-z0-9._:@-]/g, "_").slice(0, 30) || "unknown";
  return `${readable}-${hashDraftIdentity(raw)}`;
}

function createDraftContext() {
  const sessionId = normalizedText(props.sessionId);
  const resourceId = normalizedText(props.resourceId);
  if (!sessionId || !resourceId) return null;

  const problemId = normalizedText(resolvedProblemId()) || resourceId;
  const version = resolvedProblemVersion();
  return {
    sessionId,
    resourceId,
    problemId,
    version,
    language: normalizeCodeLanguage(resolvedLanguage.value),
    assetKey: `code:${assetKeySegment(resourceId)}:${assetKeySegment(problemId)}:${assetKeySegment(version)}`,
  };
}

function storageKey(context) {
  if (!context) return "";
  return `eduagent:practice-draft:v2:${context.sessionId}:${context.assetKey}`;
}

function legacyStorageKey(context) {
  if (!context) return "";
  return `eduagent:practice-draft:v1:${context.sessionId}:${context.resourceId}`;
}

function hasDraftCode(draft) {
  return Boolean(draft && typeof draft === "object" && typeof draft.code === "string");
}

function draftMatchesContext(draft, context) {
  if (!hasDraftCode(draft) || !context) return false;
  const resourceId = normalizedText(draft.resource_id ?? draft.resourceId);
  const problemId = normalizedText(draft.problem_id ?? draft.problemId);
  const version = normalizedText(draft.version ?? draft.problem_version ?? draft.problemVersion);
  const language = normalizedText(draft.language).toLowerCase();
  return (!resourceId || resourceId === context.resourceId)
    && (!problemId || problemId === context.problemId)
    && (!version || version === context.version)
    // Drafts without an explicit language belong to the pre-C contract. Do
    // not migrate them into the C editor where they would be submitted as C.
    && language === context.language;
}

function readStoredDraft(key) {
  if (typeof window === "undefined" || !key) return null;
  try {
    const raw = window.localStorage.getItem(key);
    const draft = raw ? JSON.parse(raw) : null;
    return hasDraftCode(draft) ? draft : null;
  } catch {
    draftStorageUnavailable.value = true;
    return null;
  }
}

function readLocalDraft(context) {
  const current = readStoredDraft(storageKey(context));
  if (draftMatchesContext(current, context)) return current;

  // Keep the old per-resource browser cache as a migration fallback. New
  // writes use a problem/version key so drafts do not bleed across revisions.
  const legacy = readStoredDraft(legacyStorageKey(context));
  return draftMatchesContext(legacy, context) ? legacy : null;
}

function isLearningAssetsContext(context) {
  return Boolean(
    context
      && learningAssets.hasContext
      && normalizedText(learningAssets.sessionId) === context.sessionId,
  );
}

function readSynchronizedDraft(context) {
  if (!isLearningAssetsContext(context)) return null;
  const draft = learningAssets.read("code_drafts", context.assetKey, null);
  return draftMatchesContext(draft, context) ? draft : null;
}

function attemptCount(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= 0 ? Math.floor(numeric) : fallback;
}

function mergeDrafts(primary, fallback) {
  if (!primary) return fallback;
  if (!fallback) return primary;

  const fallbackIsNewer = draftTimestamp(fallback.updated_at) > draftTimestamp(primary.updated_at);
  const preferred = fallbackIsNewer ? fallback : primary;
  const secondary = fallbackIsNewer ? primary : fallback;
  return {
    ...secondary,
    ...preferred,
    // Older servers may omit these UI-only counters. Preserve the browser
    // copy until the newest draft explicitly includes them.
    run_attempts: preferred.run_attempts === undefined
      ? secondary.run_attempts
      : preferred.run_attempts,
    submit_attempts: preferred.submit_attempts === undefined
      ? secondary.submit_attempts
      : preferred.submit_attempts,
  };
}

function readDraft(context) {
  const localDraft = readLocalDraft(context);
  const synchronizedDraft = readSynchronizedDraft(context);
  return mergeDrafts(synchronizedDraft, localDraft);
}

function draftTimestamp(value) {
  const numeric = Number(value);
  if (Number.isFinite(numeric) && numeric > 0) return numeric;
  const parsed = Date.parse(String(value || ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function applyDraft(draft, fallbackCode = resolvedStarterCode()) {
  runAttempts.value = attemptCount(draft?.run_attempts);
  submitAttempts.value = attemptCount(draft?.submit_attempts);
  draftSavedAt.value = draftTimestamp(draft?.updated_at);
  setCode(typeof draft?.code === "string" ? draft.code : fallbackCode, { markDirty: false });
}

function draftPayload(context) {
  return {
    resource_id: context.resourceId,
    problem_id: context.problemId,
    version: context.version,
    code: code.value,
    language: normalizeCodeLanguage(context.language || resolvedLanguage.value),
    updated_at: Date.now(),
    run_attempts: runAttempts.value,
    submit_attempts: submitAttempts.value,
  };
}

function persistDraft() {
  const context = draftContext.value;
  if (!context || !code.value) return;

  const draft = draftPayload(context);
  let saved = false;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(storageKey(context), JSON.stringify(draft));
      draftStorageUnavailable.value = false;
      saved = true;
    } catch {
      draftStorageUnavailable.value = true;
    }
  }

  if (isLearningAssetsContext(context)) {
    learningAssets.write("code_drafts", context.assetKey, draft);
    saved = true;
  }

  if (saved) {
    draftSavedAt.value = draft.updated_at;
  }
}

function schedulePersistDraft() {
  if (draftSaveTimer) {
    window.clearTimeout(draftSaveTimer);
  }
  draftSaveTimer = window.setTimeout(() => {
    draftSaveTimer = null;
    persistDraft();
  }, 300);
}

function flushPendingDraft() {
  if (draftSaveTimer) {
    window.clearTimeout(draftSaveTimer);
    draftSaveTimer = null;
  }
  persistDraft();
}

function restoreSynchronizedDraft() {
  const context = draftContext.value;
  if (!context || !learningAssets.hydrated || draftDirty.value || practiceState.value !== "ready") return;
  if (!isLearningAssetsContext(context)) return;

  const restoreKey = `${context.assetKey}:remote`;
  if (restoredRemoteDraftKey.value === restoreKey) return;
  const draft = mergeDrafts(readSynchronizedDraft(context), readLocalDraft(context));
  if (draft) {
    applyDraft(draft);
  }
  restoredRemoteDraftKey.value = restoreKey;
}

function resolvedStarterCode() {
  return firstString(
    practiceProblem.value?.starter_code,
    practiceProblem.value?.template,
    practiceProblem.value?.code_template,
    props.starterCode,
  );
}

function resolvedProblemId() {
  return firstString(props.problemId, practiceProblem.value?.id, practiceProblem.value?.problem_id, props.resourceId);
}

async function loadPracticeProblem() {
  const generation = ++loadingGeneration;
  executionGeneration += 1;
  activeAction.value = "";
  // Props can change while a debounce is pending. Keep the old draft under
  // its captured identity before switching to the next resource/problem.
  flushPendingDraft();
  destroyEditor();
  practiceProblem.value = null;
  draftContext.value = null;
  draftDirty.value = false;
  restoredRemoteDraftKey.value = "";
  execution.value = null;
  executionError.value = "";
  practiceLoadError.value = "";
  if (!props.sessionId || !props.resourceId) {
    practiceState.value = "not_configured";
    practiceLoadError.value = "缺少当前练习的会话或资源标识。";
    return;
  }

  practiceState.value = "loading";
  try {
    const response = await fetchSessionPracticeProblem(props.sessionId, resolvedProblemId());
    if (generation !== loadingGeneration) return;

    const problem = response?.problem ?? response?.data?.problem ?? response;
    if (!problem || typeof problem !== "object" || problem.status === "practice_problem_not_configured") {
      practiceState.value = "not_configured";
      practiceLoadError.value = firstString(problem?.message, response?.message, "该学习资源还没有绑定可执行的练习题。");
      return;
    }

    practiceProblem.value = problem;
    if (!resolvedStarterCode()) {
      practiceState.value = "not_configured";
      practiceLoadError.value = "该练习缺少服务端提供的 C 函数模板，请刷新资源后重试。";
      return;
    }
    draftContext.value = createDraftContext();
    const draft = readDraft(draftContext.value);
    applyDraft(draft);
    practiceState.value = "ready";
    await nextTick();
    if (generation !== loadingGeneration) return;
    installEditor();
    syncEditorDocument();
    restoreSynchronizedDraft();
  } catch (error) {
    if (generation !== loadingGeneration) return;
    const payload = error?.response?.data;
    const detail = payload?.detail;
    const codeValue = firstString(payload?.code, detail?.code, payload?.status);
    practiceState.value = codeValue === "practice_problem_not_configured" || error?.response?.status === 404
      ? "not_configured"
      : "error";
    practiceLoadError.value = firstString(
      payload?.message,
      detail?.message,
      typeof detail === "string" ? detail : "",
      "请稍后重试。",
    );
  }
}

function installEditor() {
  if (!editorHost.value || editorView) return;
  editorView = new EditorView({
    state: EditorState.create({
      doc: code.value,
      extensions: [
        lineNumbers(),
        history(),
        cpp(),
        oneDark,
        EditorView.lineWrapping,
        EditorView.contentAttributes.of({
          "aria-label": "代码编辑器",
          spellcheck: "false",
        }),
        keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
        EditorView.updateListener.of((update) => {
          if (!update.docChanged) return;
          code.value = update.state.doc.toString();
          if (suppressDraftChangeTracking) return;
          draftDirty.value = true;
          schedulePersistDraft();
        }),
      ],
    }),
    parent: editorHost.value,
  });
}

function destroyEditor() {
  editorView?.destroy();
  editorView = null;
}

function syncEditorDocument() {
  if (!editorView || editorView.state.doc.toString() === code.value) return;
  editorView.dispatch({
    changes: { from: 0, to: editorView.state.doc.length, insert: code.value },
  });
}

function setCode(nextCode, { markDirty = false } = {}) {
  code.value = typeof nextCode === "string" ? nextCode : "";
  draftDirty.value = markDirty;
  suppressDraftChangeTracking = true;
  nextTick(() => {
    syncEditorDocument();
    suppressDraftChangeTracking = false;
  });
}

function resetDraft() {
  execution.value = null;
  setCode(resolvedStarterCode(), { markDirty: true });
  persistDraft();
}

function eventResult(result, { httpStatus, requestError } = {}) {
  const source = result && typeof result === "object" && !Array.isArray(result)
    ? result
    : null;
  const outcome = {};

  // Keep only facts returned by the practice endpoint. In particular, do not
  // turn an unavailable sandbox into a locally invented verdict or receipt.
  for (const key of [
    "status",
    "mode",
    "submission_id",
    "verdict",
    "resource_id",
    "node_id",
    "problem_id",
    "problem_version",
    "message",
    "reason",
  ]) {
    if (typeof source?.[key] === "string" && source[key].trim()) {
      outcome[key] = source[key].trim();
    }
  }

  for (const key of ["runtime_ms", "memory_kb"]) {
    if (Number.isFinite(source?.[key])) {
      outcome[key] = source[key];
    }
  }
  if (source?.summary && typeof source.summary === "object" && !Array.isArray(source.summary)) {
    outcome.summary = source.summary;
  }
  if (Array.isArray(source?.tests)) {
    outcome.test_results = source.tests;
  }
  if (typeof source?.detail === "string" || Array.isArray(source?.detail)
    || (source?.detail && typeof source.detail === "object")) {
    outcome.detail = source.detail;
  }

  if (Number.isInteger(httpStatus) && httpStatus >= 100 && httpStatus <= 599) {
    outcome.http_status = httpStatus;
  }
  if (!source && requestError && typeof requestError === "object") {
    const error = {};
    if (typeof requestError.code === "string" && requestError.code.trim()) {
      error.code = requestError.code.trim();
    }
    if (typeof requestError.message === "string" && requestError.message.trim()) {
      error.message = requestError.message.trim();
    }
    if (Object.keys(error).length) {
      outcome.request_error = error;
    }
  }

  return outcome;
}

function capturePracticeRequest(mode) {
  const attemptNumber = mode === "run"
    ? runAttempts.value + 1
    : submitAttempts.value + 1;
  if (mode === "run") {
    runAttempts.value = attemptNumber;
  } else {
    submitAttempts.value = attemptNumber;
  }
  draftDirty.value = true;
  persistDraft();

  const context = draftContext.value ? { ...draftContext.value } : createDraftContext();
  return {
    executionId: ++executionGeneration,
    loadingGeneration,
    mode,
    sessionId: normalizedText(props.sessionId),
    nodeId: normalizedText(props.nodeId),
    resourceId: normalizedText(context?.resourceId || props.resourceId),
    problemId: normalizedText(context?.problemId || resolvedProblemId()),
    problemVersion: normalizedText(context?.version || resolvedProblemVersion()),
    language: normalizeCodeLanguage(context?.language || resolvedLanguage.value),
    code: code.value,
    attemptNumber,
  };
}

function practiceRequestMatchesCurrent(request) {
  return Boolean(
    request
      && request.executionId === executionGeneration
      && request.loadingGeneration === loadingGeneration
      && request.sessionId === normalizedText(props.sessionId)
      && request.nodeId === normalizedText(props.nodeId)
      && request.resourceId === normalizedText(props.resourceId),
  );
}

function emitPracticeAttempt(request, result, options = {}) {
  const payload = {
    sessionId: request.sessionId,
    nodeId: request.nodeId,
    resourceId: request.resourceId,
    problemId: request.problemId,
    problemVersion: request.problemVersion,
    attemptNumber: request.attemptNumber,
    codeSnapshot: request.code,
    result: eventResult(result, options),
  };

  emit(request.mode === "run" ? "code-run" : "code-submitted", payload);
}

async function execute(mode) {
  if (!canExecute.value || mode !== "run" && mode !== "submit") return;
  const request = capturePracticeRequest(mode);
  activeAction.value = mode;
  executionError.value = "";
  try {
    const payload = {
      resource_id: request.resourceId,
      language: request.language,
      code: request.code,
    };
    const result = mode === "run"
      ? await runSessionPractice(request.sessionId, payload)
      : await submitSessionPractice(request.sessionId, payload);
    if (practiceRequestMatchesCurrent(request)) {
      execution.value = result;
    }
    emitPracticeAttempt(request, result);
  } catch (error) {
    // HTTP failures such as 503 sandbox_unavailable are still genuine learner
    // attempts. Record the returned service state, without inventing a
    // verdict or submission receipt, so the audit ledger remains complete.
    const failure = error?.response?.data;
    const structuredFailure = failure && typeof failure === "object" && !Array.isArray(failure)
      ? failure
      : null;
    if (practiceRequestMatchesCurrent(request)) {
      execution.value = structuredFailure;
    }
    emitPracticeAttempt(request, structuredFailure, {
      httpStatus: error?.response?.status,
      requestError: structuredFailure ? null : error,
    });
    if (practiceRequestMatchesCurrent(request) && !execution.value) {
      executionError.value = "运行请求未完成，请检查网络后重试。";
    }
  } finally {
    if (practiceRequestMatchesCurrent(request)) {
      activeAction.value = "";
    }
  }
}

function verdictLabel(verdict) {
  return VERDICT_LABELS[verdict] || (verdict ? String(verdict) : "未返回结果");
}

function metricValue(value, unit) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric} ${unit}` : "--";
}

function testName(test, index) {
  return firstString(test?.id, test?.name, `测试 ${index + 1}`);
}

function hasValue(value) {
  return value !== undefined && value !== null && value !== "";
}

function formatValue(value) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function formatSavedTime(timestamp) {
  try {
    return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(timestamp);
  } catch {
    return "刚刚";
  }
}
</script>

<style scoped>
.code-practice-panel {
  border: 1px solid color-mix(in srgb, var(--border-subtle) 86%, var(--color-primary));
  border-radius: 16px;
  background: color-mix(in srgb, var(--space-elevated) 92%, var(--space-panel));
  padding: 1rem;
}

.code-practice-panel__header,
.code-practice-panel__editor-toolbar,
.code-practice-panel__actions,
.code-practice-panel__verdict-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.code-practice-panel__eyebrow,
.code-practice-panel__section-label {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.625rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.code-practice-panel__title {
  margin: 0.25rem 0 0;
  color: var(--text-primary);
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.4;
}

.code-practice-panel__state,
.code-practice-panel__test-verdict {
  flex: none;
  border-radius: 999px;
  padding: 0.25rem 0.55rem;
  font-size: 0.6875rem;
  font-weight: 700;
}

.code-practice-panel__state {
  color: var(--text-secondary);
  background: var(--card-bg-hover);
}

.code-practice-panel__state.is-ready,
.code-practice-panel__test-verdict.is-passed {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.code-practice-panel__state.is-error,
.code-practice-panel__state.is-not_configured,
.code-practice-panel__test-verdict.is-failed {
  color: var(--color-error);
  background: var(--color-error-soft);
}

.code-practice-panel__loading,
.code-practice-panel__empty {
  display: grid;
  gap: 0.75rem;
  margin-top: 1rem;
  padding: 1rem;
  border-radius: 12px;
  background: var(--card-bg-hover);
}

.code-practice-panel__loading-line,
.code-practice-panel__loading-editor {
  display: block;
  border-radius: 4px;
  background: color-mix(in srgb, var(--border-subtle) 74%, transparent);
  animation: code-practice-pulse 1.2s ease-in-out infinite alternate;
}

.code-practice-panel__loading-line { width: 48%; height: 0.75rem; }
.code-practice-panel__loading-line.is-wide { width: 72%; }
.code-practice-panel__loading-editor { height: 15rem; }
.code-practice-panel__empty-title { margin: 0; color: var(--text-primary); font-size: 0.9375rem; font-weight: 700; }
.code-practice-panel__empty-detail { margin: 0; color: var(--text-secondary); font-size: 0.8125rem; line-height: 1.6; }
.code-practice-panel__empty button,
.code-practice-panel__actions button { min-height: 2.75rem; }

.code-practice-panel__prompt {
  padding: 0.875rem;
  border-radius: 12px;
  background: var(--card-bg-hover);
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.65;
}

.code-practice-panel__prompt p { margin: 0; }
.code-practice-panel__constraints { margin-top: 0.5rem !important; color: var(--text-muted); }

.code-practice-panel__workspace {
  display: grid;
  gap: 1rem;
  grid-template-columns: minmax(0, 1.25fr) minmax(15rem, 0.75fr);
}

.code-practice-panel__editor-region,
.code-practice-panel__results {
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
}

.code-practice-panel__editor-toolbar {
  min-height: 2.75rem;
  padding: 0 0.75rem;
  background: #111827;
}

.code-practice-panel__draft-status { color: #b6c2d9; font-size: 0.6875rem; }
.code-practice-panel__editor { min-height: 18rem; background: #282c34; }
.code-practice-panel__actions { padding: 0.75rem; background: var(--space-panel); border-top: 1px solid var(--border-subtle); }

.code-practice-panel__results { padding: 0.875rem; background: var(--space-panel); }
.code-practice-panel__test-overview { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; }
.code-practice-panel__test-overview > div { padding: 0.625rem; border-radius: 8px; background: var(--card-bg-hover); }
.code-practice-panel__section-value { margin: 0.25rem 0 0; color: var(--text-primary); font-size: 0.875rem; font-weight: 700; }
.code-practice-panel__test-list { display: grid; gap: 0.5rem; margin-top: 0.875rem; }
.code-practice-panel__test-case { padding: 0.625rem; border: 1px solid var(--border-subtle); border-radius: 8px; }
.code-practice-panel__test-name { margin: 0; color: var(--text-primary); font-size: 0.75rem; font-weight: 700; }
.code-practice-panel__test-message,
.code-practice-panel__execution-message { margin: 0.4rem 0 0; color: var(--text-secondary); font-size: 0.75rem; line-height: 1.5; white-space: pre-wrap; }
.code-practice-panel__test-data { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.25rem 0.5rem; margin: 0.5rem 0 0; color: var(--text-secondary); font-family: "JetBrains Mono", Consolas, monospace; font-size: 0.6875rem; line-height: 1.45; }
.code-practice-panel__test-data dt { color: var(--text-muted); }
.code-practice-panel__test-data dd { min-width: 0; margin: 0; overflow-wrap: anywhere; }
.code-practice-panel__execution { margin-top: 0.875rem; padding-top: 0.875rem; border-top: 1px solid var(--border-subtle); }
.code-practice-panel__verdict { margin: 0.2rem 0 0; color: var(--text-primary); font-size: 0.9375rem; font-weight: 800; }
.code-practice-panel__verdict.is-accepted { color: var(--color-success); }
.code-practice-panel__verdict.is-sandbox_unavailable { color: var(--color-warning); }
.code-practice-panel__verdict.is-wrong_answer,
.code-practice-panel__verdict.is-syntax_error,
.code-practice-panel__verdict.is-runtime_error,
.code-practice-panel__verdict.is-time_limit,
.code-practice-panel__verdict.is-internal_error { color: var(--color-error); }
.code-practice-panel__metrics { display: flex; gap: 0.75rem; margin: 0; text-align: right; }
.code-practice-panel__metrics dt { color: var(--text-muted); font-size: 0.625rem; font-weight: 700; }
.code-practice-panel__metrics dd { margin: 0.2rem 0 0; color: var(--text-primary); font-family: "JetBrains Mono", Consolas, monospace; font-size: 0.6875rem; }
.code-practice-panel__result-placeholder { margin: 1rem 0 0; color: var(--text-muted); font-size: 0.75rem; line-height: 1.5; }

:deep(.cm-editor) { min-height: 18rem; font-size: 0.8125rem; }
:deep(.cm-scroller) { min-height: 18rem; font-family: "JetBrains Mono", Consolas, monospace; }
:deep(.cm-focused) { outline: 2px solid color-mix(in srgb, var(--color-primary) 78%, white); outline-offset: -2px; }

@keyframes code-practice-pulse { from { opacity: 0.45; } to { opacity: 0.9; } }

@media (max-width: 960px) {
  .code-practice-panel__workspace { grid-template-columns: 1fr; }
}

@media (max-width: 480px) {
  .code-practice-panel { padding: 0.75rem; }
  .code-practice-panel__header,
  .code-practice-panel__actions { align-items: flex-start; flex-direction: column; }
  .code-practice-panel__actions > div { width: 100%; }
  .code-practice-panel__actions button { flex: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .code-practice-panel__loading-line,
  .code-practice-panel__loading-editor { animation: none; }
}
</style>
