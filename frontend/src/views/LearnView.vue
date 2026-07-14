<template>
  <AppPageFrame v-if="routeError">
    <section class="px-4 py-12 sm:px-6">
      <div class="workspace-shell-card mx-auto max-w-xl rounded-xl px-6 py-8 text-center">
        <h1 class="text-xl font-black text-text-primary">无法恢复学习节点</h1>
        <p class="mt-3 text-sm leading-7 text-text-secondary">{{ routeError }}</p>
        <button type="button" class="workspace-shell-btn focus-ring mt-6 px-4 py-2.5 text-sm font-semibold" @click="router.push({ name: 'courses' })">返回课程中心</button>
      </div>
    </section>
  </AppPageFrame>

  <PremiumWorkspace
    v-else
    ref="workspaceRef"
    :boot-mode="bootMode"
    :user="currentUser"
    :current-node="currentNode"
    :cards="currentCards"
    :path-nodes="currentPathNodes"
    :node-title="currentNodeTitle"
    :messages="messages"
    :agent-feedback="agentFeedback"
    :overall-progress="overallProgress"
    :mastered-count="masteredCount"
    :statuses="agentStatuses"
    :info-message="infoMessage"
    :is-busy="isBusy"
    :is-loading-node="isLoadingNode"
    :is-submitting-probe="isSubmittingProbe"
    :probe="probe"
    :probe-collected="probeCollected"
    :probe-total="probeTotal"
    :last-diagnostic="lastDiagnostic"
    :focus-card-type="reviewFocusCardType"
    :review-item-id="reviewItemId"
    :review-phase="reviewPhase"
    :get-card-label="getCardLabel"
    :get-agent-label="getAgentLabel"
    :parse-quiz="parseQuiz"
    :active-course="activeCourse"
    :session-id="sessionId"
    :enrolled-courses="enrolledCourses"
    :learning-view="learningView"
    @select-node="selectNode"
    @submit-quiz="submitCurrentQuiz"
    @send-tutor="sendTutor"
    @submit-probe="submitCurrentProbe"
    @logout="logout"
    @browse-courses="router.push({ name: 'courses' })"
    @switch-course="switchCourse"
    @refresh-resources="refreshCurrentResources"
    @generate-card="generateCard"
    @content-viewed="handleContentViewed"
    @hint-requested="handleHintRequested"
    @answer-selected="handleAnswerSelected"
    @code-run="handleCodeRun"
    @code-submitted="handleCodeSubmission"
    @open-review="openReview"
    @prepare-review-retest="prepareReviewRetest"
    @navigate="navigateWorkspace"
  />
  <p v-if="reviewActionError" class="fixed bottom-5 left-1/2 z-40 max-w-[calc(100%-2rem)] -translate-x-1/2 border border-error/30 bg-space-panel px-4 py-3 text-sm text-text-primary" role="alert">
    {{ reviewActionError }}
  </p>
  <div
    v-if="retestResourceError"
    class="fixed bottom-5 left-1/2 z-40 flex max-w-[calc(100%-2rem)] -translate-x-1/2 flex-wrap items-center gap-3 border border-error/30 bg-space-panel px-4 py-3 text-sm text-text-primary"
    role="alert"
  >
    <span>{{ retestResourceError }}</span>
    <button
      type="button"
      class="workspace-shell-btn focus-ring min-h-11 px-3 py-2 text-sm font-semibold"
      :disabled="retestResourceRetrying"
      @click="retryRetestResource"
    >
      {{ retestResourceRetrying ? "正在加载复测..." : "重新加载复测" }}
    </button>
  </div>
  <div
    v-if="learningAssets.syncError"
    class="fixed left-1/2 top-4 z-50 flex max-w-[calc(100%-2rem)] -translate-x-1/2 flex-wrap items-center gap-3 border border-error/30 bg-space-panel px-4 py-3 text-sm text-text-primary"
    role="alert"
  >
    <span>学习草稿尚未同步到服务端：{{ learningAssets.syncError }}</span>
    <button
      type="button"
      class="workspace-shell-btn focus-ring min-h-11 px-3 py-2 text-sm font-semibold"
      :disabled="learningAssets.syncing"
      @click="learningAssets.flushPending()"
    >
      {{ learningAssets.syncing ? '正在重试...' : '重试同步' }}
    </button>
  </div>
  <p v-if="codeReviewNotice" class="fixed bottom-5 left-1/2 z-40 max-w-[calc(100%-2rem)] -translate-x-1/2 border border-success/30 bg-space-panel px-4 py-3 text-sm text-text-primary" role="status">
    {{ codeReviewNotice }}
  </p>
  <div
    v-if="codeEventError"
    class="fixed bottom-5 left-1/2 z-40 flex max-w-[calc(100%-2rem)] -translate-x-1/2 flex-wrap items-center gap-3 border border-error/30 bg-space-panel px-4 py-3 text-sm text-text-primary"
    role="alert"
  >
    <span>{{ codeEventError }}</span>
    <button
      type="button"
      class="workspace-shell-btn focus-ring min-h-11 px-3 py-2 text-sm font-semibold"
      :disabled="codeEventRetrying"
      @click="retryCodeSubmissionEvent"
    >
      {{ codeEventRetrying ? "正在补记..." : "重试记录" }}
    </button>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppPageFrame from "../components/AppPageFrame.vue";
import PremiumWorkspace from "../components/PremiumWorkspace.vue";
import { useEduAgent } from "../composables/useEduAgent";
import { useLearningAssetsStore } from "../stores/learningAssets";
import { prepareSessionReviewRetest } from "../services/eduAgentApi";
import { reportNextTaskReady } from "../services/clientTelemetry";

const props = defineProps({
  courseId: { type: String, required: true },
  nodeId: { type: String, required: true },
});

const route = useRoute();
const router = useRouter();
const learningAssets = useLearningAssetsStore();
const routeError = ref("");
const reviewActionError = ref("");
const retestResourceError = ref("");
const retestResourceRetrying = ref(false);
const pendingRetestResource = ref(null);
const codeReviewNotice = ref("");
const codeEventError = ref("");
const codeEventRetrying = ref(false);
const pendingCodeSubmission = ref(null);
const pendingCodeSubmissions = ref([]);
const workspaceRef = ref(null);
const courseIdBySessionId = new Map();
const LEARNING_ASSET_FLUSH_TIMEOUT_MS = 800;
let hydratedRouteKey = "";
let routeSyncGeneration = 0;

const {
  activeCourse,
  agentFeedback,
  agentStatuses,
  bootMode,
  currentCards,
  currentNode,
  currentNodeTitle,
  currentPathNodes,
  currentUser,
  endLearningSession,
  enrolledCourses,
  getAgentLabel,
  getCardLabel,
  handleLogout,
  infoMessage,
  isBusy,
  isLoadingNode,
  isSubmittingProbe,
  lastDiagnostic,
  masteredCount,
  messages,
  overallProgress,
  sessionId,
  parseQuiz,
  prepareLearningRoute,
  recordAnswerSelection,
  recordCodeRun,
  recordCodeSubmission,
  recordContentView,
  recordHintRequest,
  recordLearningEvent,
  refreshNodeResources,
  probe,
  probeCollected,
  probeTotal,
  sendTutorMessage,
  submitProbe,
  submitQuiz,
  startLearningSession,
  flushLearningActivity,
} = useEduAgent();

watch(
  () => [sessionId.value, props.courseId],
  ([activeSessionId, activeCourseId]) => {
    if (activeSessionId && activeCourseId) {
      courseIdBySessionId.set(String(activeSessionId), String(activeCourseId));
    }
  },
  { immediate: true, flush: "sync" },
);

const learningView = computed(() => {
  const view = typeof route.query.view === "string" ? route.query.view : "";
  return ["coach", "path", "notes"].includes(view) ? view : "learn";
});
const reviewItemId = computed(() => queryValue(route.query.reviewItem));
const reviewPhase = computed(() => queryValue(route.query.reviewPhase));
const reviewFocusCardType = computed(() => {
  if (reviewPhase.value === "retest") return "diagnostic_quiz";
  if (reviewPhase.value === "code_resubmission") return "code_snippet";
  if (reviewItemId.value) return "interactive_exercise";
  return "";
});
const currentRouteKey = computed(() => `${props.courseId}/${props.nodeId}`);

watch(
  () => [reviewItemId.value, reviewPhase.value, props.nodeId],
  ([itemId, phase, nodeId]) => {
    const pending = pendingRetestResource.value;
    if (!pending) return;
    if (phase !== "retest" || pending.reviewItemId !== itemId || pending.nodeId !== nodeId) {
      clearRetestResourceFailure();
    }
  },
  { flush: "sync" },
);

watch(currentRouteKey, synchronizeCurrentRoute, { immediate: true });

watch(
  () => [currentNode.value, bootMode.value],
  ([nodeId, mode]) => {
    if (
      mode !== "ready"
      || !nodeId
      || nodeId === "setup"
      || props.nodeId !== "setup"
    ) {
      return;
    }
    void router.replace({
      name: "learn",
      params: { courseId: props.courseId, nodeId },
      query: route.query,
    });
  },
  { flush: "post", immediate: true },
);

watch(
  () => bootMode.value,
  (mode) => {
    if (mode === "ready") {
      void reportNextTaskReady({ surface: "learn" });
    }
  },
  { flush: "post", immediate: true },
);

function reportEventFailure(eventType, error) {
  console.warn(`Unable to record ${eventType}:`, error);
}

function handleContentViewed(payload) {
  void recordContentView(payload).catch((error) => reportEventFailure("content_viewed", error));
}

function handleHintRequested(payload) {
  void recordHintRequest(payload).catch((error) => reportEventFailure("hint_requested", error));
}

function handleAnswerSelected(payload) {
  void recordAnswerSelection(payload).catch((error) => reportEventFailure("answer_selected", error));
}

function handleCodeRun(payload) {
  const event = capturedCodeEvent(payload);
  void recordCodeRun(event).catch((error) => reportEventFailure("code_run", error));
}

async function handleCodeSubmission(payload) {
  payload = capturedCodeEvent(payload);
  const event = {
    courseId: props.courseId,
    nodeId: props.nodeId,
    ...payload,
    eventId: codeSubmissionEventId(payload),
    reviewItemId: reviewItemId.value,
    reviewPhase: reviewPhase.value,
  };
  pendingCodeSubmission.value = event;
  upsertPendingCodeSubmission(event);
  if (codeEventMatchesRoute(event)) {
    codeReviewNotice.value = "";
  }
  await recordCodeSubmissionEvent(event);
}

async function recordCodeSubmissionEvent(event) {
  let response;
  try {
    response = await recordCodeSubmission(event);
  } catch (error) {
    codeEventError.value = `${event.nodeId || "当前节点"} 的判题结果已显示，但学习记录尚未保存。`;
    upsertPendingCodeSubmission({ ...event, failed: true });
    reportEventFailure("code_submitted", error);
    return;
  }

  removePendingCodeSubmission(event);
  const review = response?.review;
  const activeReviewItemId = event.reviewItemId;
  const completedItem = activeReviewItemId && review?.retested_items?.some(
    (item) => item?.review_item_id === activeReviewItemId && item?.status === "completed",
  );

  const eventStillMatchesRoute = codeEventMatchesRoute(event);
  if (!eventStillMatchesRoute) {
    currentNode.value = props.nodeId;
    return;
  }
  if (completedItem) {
    codeReviewNotice.value = "服务端已验证本次代码提交，补救任务已完成。";
    const query = { ...route.query };
    delete query.reviewItem;
    delete query.reviewPhase;
    try {
      await router.replace({ name: "learn", params: route.params, query });
    } catch (error) {
      reportEventFailure("review_navigation", error);
    }
    return;
  }

  const createdItems = Array.isArray(review?.created_or_updated_items)
    ? review.created_or_updated_items
    : [];
  if (createdItems.length) {
    codeReviewNotice.value = "代码提交未通过，服务端已将补救任务加入复习中心。";
  }
}

async function retryCodeSubmissionEvent() {
  const failedEvents = pendingCodeSubmissions.value.filter((event) => event.failed === true);
  if (!failedEvents.length || codeEventRetrying.value) {
    return;
  }
  codeEventRetrying.value = true;
  codeReviewNotice.value = "";
  try {
    await Promise.all(failedEvents.map((event) => recordCodeSubmissionEvent(event)));
  } finally {
    codeEventRetrying.value = false;
  }
}

function capturedCodeEvent(payload = {}) {
  const capturedSessionId = String(payload?.sessionId || sessionId.value || "");
  return {
    ...payload,
    sessionId: capturedSessionId,
    courseId: String(
      payload?.courseId
        || courseIdBySessionId.get(capturedSessionId)
        || props.courseId
        || "",
    ),
    nodeId: String(payload?.nodeId || props.nodeId || ""),
  };
}

function codeEventMatchesRoute(event) {
  return Boolean(
    event?.courseId === props.courseId
      && event?.nodeId === props.nodeId
      && (!event?.sessionId || event.sessionId === sessionId.value),
  );
}

function pendingCodeEventKey(event) {
  return String(event?.eventId || "");
}

function upsertPendingCodeSubmission(event) {
  const key = pendingCodeEventKey(event);
  if (!key) return;
  const index = pendingCodeSubmissions.value.findIndex(
    (candidate) => pendingCodeEventKey(candidate) === key,
  );
  if (index >= 0) {
    pendingCodeSubmissions.value = pendingCodeSubmissions.value.map(
      (candidate, candidateIndex) => candidateIndex === index ? event : candidate,
    );
  } else {
    pendingCodeSubmissions.value = [...pendingCodeSubmissions.value, event];
  }
  syncPendingCodeEventState();
}

function removePendingCodeSubmission(event) {
  const key = pendingCodeEventKey(event);
  pendingCodeSubmissions.value = pendingCodeSubmissions.value.filter(
    (candidate) => pendingCodeEventKey(candidate) !== key,
  );
  syncPendingCodeEventState();
}

function syncPendingCodeEventState() {
  const failedEvents = pendingCodeSubmissions.value.filter((event) => event.failed === true);
  pendingCodeSubmission.value = failedEvents[0] || pendingCodeSubmissions.value[0] || null;
  if (!failedEvents.length) {
    codeEventError.value = "";
    return;
  }
  if (failedEvents.length === 1) {
    codeEventError.value = `${failedEvents[0].nodeId || "当前节点"} 的判题结果已显示，但学习记录尚未保存。`;
    return;
  }
  const nodeCount = new Set(failedEvents.map((event) => event.nodeId).filter(Boolean)).size;
  codeEventError.value = `${failedEvents.length} 次代码判题结果尚未保存，涉及 ${nodeCount || 1} 个学习节点。`;
}

function codeSubmissionEventId(payload) {
  const receipt = payload?.result?.submission_id || payload?.attemptNumber || 1;
  return [
    "eduagent",
    "code",
    payload?.sessionId || sessionId.value,
    payload?.courseId || props.courseId,
    payload?.nodeId || props.nodeId,
    payload?.resourceId || "resource",
    receipt,
  ]
    .map((part) => String(part ?? "").trim().replace(/\s+/g, "_"))
    .join(":");
}

function handlePageHide() {
  void flushLearningActivity().catch((error) => reportEventFailure("content_viewed", error));
}

onMounted(() => {
  window.addEventListener("pagehide", handlePageHide);
});

onBeforeUnmount(() => {
  window.removeEventListener("pagehide", handlePageHide);
  void endLearningSession().catch((error) => reportEventFailure("content_viewed", error));
});

async function synchronizeCurrentRoute() {
  const routeKey = currentRouteKey.value;
  await flushWorkspaceAssets();
  if (routeKey !== currentRouteKey.value) {
    return;
  }
  // The URL is authoritative. Set the node eagerly so a late request for a
  // previous history entry cannot keep the old node visible.
  currentNode.value = props.nodeId;
  return synchronizeRoute();
}

async function synchronizeRoute() {
  const routeKey = currentRouteKey.value;
  const generation = ++routeSyncGeneration;
  if (routeKey === hydratedRouteKey) {
    return;
  }

  routeError.value = "";
  const result = await prepareLearningRoute(props.courseId, props.nodeId);
  if (generation !== routeSyncGeneration || routeKey !== currentRouteKey.value) {
    currentNode.value = props.nodeId;
    return;
  }

  if (result.status === "ready") {
    hydratedRouteKey = `${result.courseId}/${result.nodeId}`;
    if (result.courseId !== props.courseId || result.nodeId !== props.nodeId) {
      await router.replace({
        name: "learn",
        params: { courseId: result.courseId, nodeId: result.nodeId },
        query: route.query,
      });
      return;
    }
    void startLearningSession({ courseId: result.courseId, nodeId: result.nodeId })
      .catch((error) => reportEventFailure("lesson_opened", error));
    return;
  }

  if (result.status === "needs_probe") {
    hydratedRouteKey = currentRouteKey.value;
    return;
  }

  if (result.status === "not_enrolled") {
    await router.replace({ name: "course-detail", params: { courseId: props.courseId } });
    return;
  }

  if (result.status === "unauthenticated") {
    await router.replace({ name: "login", query: { redirect: route.fullPath } });
    return;
  }

  routeError.value = result.error?.response?.data?.detail || "请检查课程状态后重试。";
}

async function selectNode(nodeId) {
  if (!nodeId) {
    return;
  }

  const query = routeQueryWithoutReviewContext();
  const isLeavingPathView = query.view === "path";
  if (isLeavingPathView) {
    delete query.view;
  }

  if (nodeId === currentNode.value) {
    if (isLeavingPathView) {
      await router.push({ name: "learn", params: route.params, query });
    }
    return;
  }

  // The route is authoritative; hydration records lesson_opened only after
  // the selected node and its resources are actually ready to view.
  await flushWorkspaceAssets();
  hydratedRouteKey = "";
  await router.push({ name: "learn", params: { courseId: props.courseId, nodeId }, query });
}

async function switchCourse(courseId) {
  if (!courseId || courseId === props.courseId) {
    return;
  }
  await flushWorkspaceAssets();
  hydratedRouteKey = "";
  await router.push({
    name: "learn",
    params: { courseId, nodeId: "setup" },
    query: routeQueryWithoutReviewContext(),
  });
}

async function submitCurrentQuiz(submission) {
  const capturedSubmission = capturedCodeEvent(submission);
  if (submission?.eventKind === "answer_submitted") {
    try {
      const response = await submitQuiz(capturedSubmission);
      submission.onRecorded?.(response);
      return response;
    } catch (error) {
      submission.onFailure?.(error);
      reportEventFailure("answer_submitted", error);
      return null;
    }
  }

  const activeReviewItemId = reviewItemId.value;
  try {
    const response = await submitQuiz(capturedSubmission);
    submission?.onRecorded?.(response);
  } catch (error) {
    submission?.onFailure?.(error);
    reportEventFailure(submission?.isReview ? "review_completed" : "lesson_completed", error);
    return null;
  }
  const submissionStillMatchesRoute = capturedSubmission.courseId === props.courseId
    && capturedSubmission.nodeId === props.nodeId
    && (!capturedSubmission.sessionId || capturedSubmission.sessionId === sessionId.value);
  if (!submissionStillMatchesRoute) {
    currentNode.value = props.nodeId;
    return lastDiagnostic.value;
  }
  const retestedItem = activeReviewItemId && lastDiagnostic.value?.retestedItems?.find(
    (item) => item?.review_item_id === activeReviewItemId,
  );
  if (retestedItem?.status === "completed") {
    const query = { ...route.query };
    delete query.reviewItem;
    delete query.reviewPhase;
    await router.replace({ name: "learn", params: route.params, query });
    return;
  }
  if (retestedItem?.phase === "material_review") {
    await router.replace({
      name: "learn",
      params: {
        courseId: props.courseId,
        nodeId: retestedItem.node_id || props.nodeId,
      },
      query: {
        ...route.query,
        reviewItem: activeReviewItemId,
        reviewPhase: "material_review",
      },
    });
    return;
  }
  await replaceWithCurrentNode();
}

function openReview() {
  void router.push({ name: "review" });
}

async function prepareReviewRetest(practiceSubmission) {
  const itemId = typeof practiceSubmission === "string"
    ? practiceSubmission
    : String(practiceSubmission?.reviewItemId || "");
  reviewActionError.value = "";
  clearRetestResourceFailure();
  if (!itemId || !practiceSubmission || typeof practiceSubmission === "string") {
    reviewActionError.value = "请先完成并提交当前定向练习。";
    return;
  }
  try {
    let practiceEventId = String(practiceSubmission.practiceEventId || "");
    if (!practiceEventId) {
      const practiceResponse = await recordLearningEvent("answer_submitted", {
        nodeId: props.nodeId,
        resourceId: practiceSubmission.resourceId,
        questionId: practiceSubmission.questionId,
        durationMs: practiceSubmission.durationMs,
        attemptNumber: practiceSubmission.attemptNumber,
        usedHint: practiceSubmission.usedHint,
        result: {
          review_item_id: itemId,
          answer_index: practiceSubmission.selectedOptionIndex,
        },
      });
      const verification = practiceResponse?.practice_verification
        || practiceResponse?.event?.practice_verification;
      if (!verification?.verified) {
        throw new Error("服务端无法验证这次定向练习，请重新加载练习后再试。");
      }
      if (!verification.correct) {
        if (typeof practiceSubmission.onIncorrect === "function") {
          practiceSubmission.onIncorrect(verification);
        } else {
          reviewActionError.value = "这次练习答案未通过服务端验证，请调整后再次提交。";
        }
        return;
      }
      practiceEventId = String(practiceResponse?.event_id || "");
      if (!practiceEventId) {
        throw new Error("服务端未返回练习事件凭据，请重试。");
      }
      practiceSubmission.onPracticeRecorded?.(practiceEventId);
    }

    const result = await prepareSessionReviewRetest(
      sessionId.value,
      itemId,
      practiceEventId,
    );
    if (result?.status !== "ok" || !result?.learning_task?.node_id) {
      throw new Error(result?.detail || "无法生成新的复测，请稍后重试。");
    }
    practiceSubmission.onPrepared?.(result);
    await router.replace({
      name: "learn",
      params: { courseId: props.courseId, nodeId: result.learning_task.node_id },
      query: {
        ...route.query,
        reviewItem: itemId,
        reviewPhase: "retest",
      },
    });
    // The POST has already issued the server-owned retest. Fetch only that
    // card after changing the route; asking for every resource type can start
    // unrelated long-running generation and hide a ready retest behind a
    // timeout.
    const cardType = result.learning_task.focus_resource_type || "diagnostic_quiz";
    const retryContext = {
      reviewItemId: itemId,
      practiceEventId,
      nodeId: result.learning_task.node_id,
      cardType,
      retestResourceId: String(result.learning_task.retest_resource_id || ""),
    };
    const resourceOutcome = await refreshNodeResources(result.learning_task.node_id, {
      force: false,
      cardType,
    });
    if (!resourceOutcome?.ok) {
      pendingRetestResource.value = retryContext;
      retestResourceError.value = retestResourceFailureMessage(resourceOutcome?.error);
    }
  } catch (error) {
    if (typeof practiceSubmission.onFailure === "function") {
      practiceSubmission.onFailure(error);
    } else {
      reviewActionError.value = error?.response?.data?.detail || error?.message || "无法生成新的复测，请稍后重试。";
    }
  }
}

function retestResourceFailureMessage(error) {
  const detail = error?.response?.data?.detail || error?.message || "复测题暂时不可用。";
  return `复测已创建，但复测题加载失败：${detail}`;
}

function clearRetestResourceFailure() {
  pendingRetestResource.value = null;
  retestResourceError.value = "";
  retestResourceRetrying.value = false;
}

async function retryRetestResource() {
  const pending = pendingRetestResource.value;
  if (!pending || retestResourceRetrying.value) return;
  if (
    reviewPhase.value !== "retest"
    || reviewItemId.value !== pending.reviewItemId
    || props.nodeId !== pending.nodeId
  ) {
    clearRetestResourceFailure();
    return;
  }

  retestResourceRetrying.value = true;
  const outcome = await refreshNodeResources(pending.nodeId, {
    force: false,
    cardType: pending.cardType,
  });
  if (outcome?.ok) {
    clearRetestResourceFailure();
    return;
  }
  retestResourceRetrying.value = false;
  retestResourceError.value = retestResourceFailureMessage(outcome?.error);
}

async function submitCurrentProbe(values) {
  await submitProbe(values);
  await replaceWithCurrentNode();
}

async function refreshCurrentResources() {
  await refreshNodeResources(currentNode.value, { force: true });
}

async function generateCard(payload) {
  await refreshNodeResources(payload?.nodeId || currentNode.value, {
    force: Boolean(payload?.force),
    cardType: payload?.cardType || "",
  });
}

async function sendTutor(payload) {
  try {
    if (typeof payload === "string") {
      await sendTutorMessage(payload);
      return;
    }
    await sendTutorMessage(payload.text, payload.contextType, payload.codeSnippet, payload.errorMessage);
    payload.onSuccess?.();
  } catch (error) {
    payload?.onFailure?.(error);
    reportEventFailure("tutor_question", error);
  }
}

async function replaceWithCurrentNode() {
  if (!currentNode.value || currentNode.value === props.nodeId) {
    return;
  }
  hydratedRouteKey = `${props.courseId}/${currentNode.value}`;
  await router.replace({
    name: "learn",
    params: { courseId: props.courseId, nodeId: currentNode.value },
    query: route.query,
  });
}

async function navigateWorkspace(key) {
  if (["coach", "learn", "path", "notes"].includes(key)) {
    if (learningView.value === key) {
      return;
    }
    const query = { ...route.query };
    if (key === "learn") {
      delete query.view;
    } else {
      query.view = key;
    }
    // A view is part of the learner's location. Preserve the prior view in
    // browser history so Back/Forward restores the same course and node.
    await router.push({ name: "learn", params: route.params, query });
    return;
  }

  const routeNames = {
    home: "app-workspace",
    courses: "courses",
    progress: "progress",
    review: "review",
    account: "account",
    settings: "settings",
  };
  if (routeNames[key]) {
    await router.push({ name: routeNames[key] });
  }
}

async function logout() {
  await flushWorkspaceAssets();
  handleLogout();
  await router.replace({ name: "login" });
}

async function flushWorkspaceAssets() {
  const flush = workspaceRef.value?.flushLearningAssets;
  if (typeof flush !== "function") {
    return;
  }

  try {
    const pending = flush();
    if (!pending || typeof pending.then !== "function") {
      return;
    }
    await settleWithin(pending, LEARNING_ASSET_FLUSH_TIMEOUT_MS);
  } catch (error) {
    reportEventFailure("learning_assets_flush", error);
  }
}

async function settleWithin(promise, timeoutMs) {
  let timeoutId;
  try {
    await Promise.race([
      Promise.resolve(promise).catch(() => undefined),
      new Promise((resolve) => {
        timeoutId = window.setTimeout(resolve, timeoutMs);
      }),
    ]);
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
  }
}

function queryValue(value) {
  return typeof value === "string" ? value : "";
}

function routeQueryWithoutReviewContext() {
  const query = { ...route.query };
  delete query.reviewItem;
  delete query.reviewPhase;
  return query;
}
</script>
