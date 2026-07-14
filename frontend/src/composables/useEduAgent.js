import { computed, ref } from "vue";
import {
  buildSessionId,
  createSession,
  enrollCourse,
  fetchCourses,
  fetchKnowledgeGraph,
  fetchMyProfile,
  fetchSessionLearningEventHistory,
  fetchSessionProfileProbe,
  fetchSessionResources,
  getSession,
  fetchUserCourses,
  getCaptcha,
  initSessionPath,
  login,
  refreshToken,
  register,
  streamSessionTutor,
  submitSessionLearningEvent,
  submitSessionProfileInput,
  switchCourse,
} from "../services/eduAgentApi";
import { useLearningAssetsStore } from "../stores/learningAssets";

let sharedEduAgent;

const LEARNING_EVENT_TYPES = new Set([
  "lesson_opened",
  "content_viewed",
  "hint_requested",
  "answer_selected",
  "answer_submitted",
  "code_run",
  "code_submitted",
  "lesson_completed",
  "review_completed",
  "tutor_question",
]);

const LEARNING_EVENT_MAX_ATTEMPTS = 2;
const LEARNING_EVENT_RETRY_DELAY_MS = 300;
const TUTOR_STREAM_IDLE_TIMEOUT_MS = 45_000;
const TUTOR_STREAM_MAX_DURATION_MS = 120_000;

function isRetryableLearningEventError(error) {
  const status = Number(error?.response?.status);
  if (Number.isInteger(status) && status > 0) {
    return status === 408 || status === 429 || status >= 500;
  }

  // Axios reports browser/network failures and timeouts without an HTTP
  // response. Retrying once is safe because the event id is idempotent.
  return true;
}

function waitForLearningEventRetry(delayMs) {
  return new Promise((resolve) => {
    setTimeout(resolve, delayMs);
  });
}

function monotonicNow() {
  return typeof performance !== "undefined" && typeof performance.now === "function"
    ? performance.now()
    : Date.now();
}

function createDwellTimer(context = {}) {
  const visible = typeof document === "undefined" || document.visibilityState !== "hidden";
  return {
    ...context,
    elapsedMs: 0,
    startedAt: visible ? monotonicNow() : null,
  };
}

function pauseDwellTimer(timer) {
  if (!timer || timer.startedAt === null) {
    return;
  }

  timer.elapsedMs += Math.max(0, monotonicNow() - timer.startedAt);
  timer.startedAt = null;
}

function resumeDwellTimer(timer) {
  if (!timer || timer.startedAt !== null) {
    return;
  }

  timer.startedAt = monotonicNow();
}

function dwellDuration(timer) {
  if (!timer) {
    return 0;
  }

  const runningMs = timer.startedAt === null ? 0 : Math.max(0, monotonicNow() - timer.startedAt);
  return Math.max(0, Math.round(timer.elapsedMs + runningMs));
}

function createEventId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `learning-event-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeEventResult(result) {
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    return {};
  }

  // The server derives scores and mastery. Client interaction events keep
  // only the evidence that can be independently checked or audited.
  const { score, correctness, mastery, mastery_score, ...safeResult } = result;
  return safeResult;
}

function isAuthenticationError(error) {
  const status = Number(error?.response?.status);
  return status === 400 || status === 401 || status === 403 || status === 422;
}

const CARD_CN = {
  concept_map: "概念导图",
  code_snippet: "代码示例",
  interactive_exercise: "互动练习",
  video_summary: "视频摘要",
  diagnostic_quiz: "诊断测验",
};

const AGENT_CN = {
  concept_map: "文档智能体",
  code_snippet: "文档智能体",
  interactive_exercise: "辅导智能体",
  video_summary: "文档智能体",
  diagnostic_quiz: "评估智能体",
};

function createEduAgent() {
  const learningAssets = useLearningAssetsStore();
  const isLoggedIn = ref(false);
  const currentUser = ref(null);
  const userId = computed(() => currentUser.value?.user_id ?? "demo_user");

  const activeCourse = ref(null);
  const availableCourses = ref([]);
  const enrolledCourses = ref([]);

  const bootMode = ref("loading");
  const bootstrapError = ref("");
  const isBusy = ref(false);
  const isSubmittingProbe = ref(false);
  const isLoadingNode = ref(false);
  const currentNode = ref("");
  const activePath = ref([]);
  const mastery = ref({});
  const capabilityRadar = ref([0.5, 0.5, 0.5, 0.5, 0.5]);
  const diagnosticReport = ref("");
  const knowledgeGraph = ref({ nodes: [], edges: [] });
  const nodeTitles = ref({});
  const probe = ref(null);
  const probeCollected = ref(0);
  const probeTotal = ref(6);
  const resources = ref({});
  const agentFeedback = ref([]);
  const lastDiagnostic = ref(null);
  const lastMasteryAttribution = ref(null);
  const messages = ref([]);
  const infoMessage = ref("");
  const stepLogs = ref([]);
  const agentStatuses = ref([
    { key: "doc", kind: "doc", label: "文档智能体", phase: "待命", progress: 0, active: false },
    { key: "quiz", kind: "quiz", label: "评估智能体", phase: "等待中", progress: 0, active: false },
    { key: "path", kind: "path", label: "路径规划", phase: "未启动", progress: 0, active: false },
  ]);

  const currentCards = computed(() => resources.value[currentNode.value] ?? []);
  const currentNodeTitle = computed(() => nodeTitles.value[currentNode.value] || currentNode.value || "未选择");
  const masteredCount = computed(() => activePath.value.filter(
    (nodeId) => (mastery.value[nodeId] ?? 0) >= 0.65,
  ).length);
  const overallProgress = computed(() => (
    activePath.value.length ? Math.round((masteredCount.value / activePath.value.length) * 100) : 0
  ));
  const currentPathNodes = computed(() =>
    activePath.value.map((id, index) => ({
      id,
      order: index + 1,
      title: nodeTitles.value[id] || id,
      mastery: mastery.value[id] ?? 0,
    })),
  );
  const courseId = computed(() => activeCourse.value?.course_id || "data_structures");
  const sessionId = computed(() => buildSessionId(userId.value, courseId.value));
  let learningEventQueue = Promise.resolve();
  let lessonTimer = null;
  let contentTimer = null;
  let tutorQuestionAttempt = 0;
  let routePreparationGeneration = 0;
  let routePreparationQueue = Promise.resolve();
  let routeEnhancementGeneration = 0;
  let scheduledRouteEnhancement = null;
  const inFlightResourceRequests = new Map();

  function invalidateRouteEnhancements() {
    routeEnhancementGeneration += 1;
    if (scheduledRouteEnhancement !== null) {
      clearTimeout(scheduledRouteEnhancement);
      scheduledRouteEnhancement = null;
    }
    isLoadingNode.value = false;
    return routeEnhancementGeneration;
  }

  function createRouteEnhancementContext(nodeId, targetCourseId = courseId.value) {
    const generation = invalidateRouteEnhancements();
    const normalizedCourseId = String(targetCourseId || "");
    const normalizedNodeId = String(nodeId || "");
    const targetSessionId = buildSessionId(userId.value, normalizedCourseId);

    currentNode.value = normalizedNodeId;
    lastDiagnostic.value = null;
    isLoadingNode.value = Boolean(normalizedNodeId);

    return {
      generation,
      courseId: normalizedCourseId,
      nodeId: normalizedNodeId,
      sessionId: targetSessionId,
    };
  }

  function isCurrentRouteEnhancement(context) {
    return Boolean(
      context
      && context.generation === routeEnhancementGeneration
      && context.courseId === courseId.value
      && context.sessionId === sessionId.value
      && context.nodeId === currentNode.value,
    );
  }

  function finishRouteEnhancement(context) {
    if (!context || context.generation !== routeEnhancementGeneration) {
      return;
    }
    isLoadingNode.value = false;
    if (isCurrentRouteEnhancement(context)) {
      refreshStatuses();
    }
  }

  function fetchRouteNodeResources(context) {
    const requestKey = `${context.sessionId}:${context.nodeId}`;
    const existingRequest = inFlightResourceRequests.get(requestKey);
    if (existingRequest) {
      return existingRequest;
    }

    const request = fetchSessionResources(context.sessionId, context.nodeId, normalizeResourceOptions())
      .finally(() => {
        if (inFlightResourceRequests.get(requestKey) === request) {
          inFlightResourceRequests.delete(requestKey);
        }
      });
    inFlightResourceRequests.set(requestKey, request);
    return request;
  }

  async function fetchCurrentSession() {
    return getSession(sessionId.value);
  }

  function restoreTutorHistory() {
    const history = Array.isArray(learningAssets.tutorHistory) ? learningAssets.tutorHistory : [];
    const restored = history
      .filter((entry) => entry && (entry.role === "user" || entry.role === "assistant") && entry.content)
      .map((entry, index) => ({
        id: String(entry.key || entry.id || `restored-${index}`),
        role: entry.role,
        content: String(entry.content),
        mermaidSource: typeof entry.mermaid_source === "string" ? entry.mermaid_source : "",
        isStreaming: false,
        createdAt: entry.created_at || "",
      }));
    messages.value = restored;
  }

  async function hydrateLearningAssets() {
    await learningAssets.hydrate(sessionId.value);
    restoreTutorHistory();
  }

  function normalizeResourceOptions(options = {}) {
    if (typeof options === "boolean") {
      return { force: options, cardType: "" };
    }

    return {
      force: Boolean(options?.force),
      cardType: typeof options?.cardType === "string" ? options.cardType : "",
    };
  }

  async function fetchCurrentNodeResources(nodeId, options = {}) {
    return fetchSessionResources(sessionId.value, nodeId, normalizeResourceOptions(options));
  }

  function resourceCardType(resource) {
    return resource?.resource_type || resource?.card_type || resource?.type || "";
  }

  function mergeNodeResources(nodeId, incomingResources, cardType = "") {
    if (!Array.isArray(incomingResources) || !incomingResources.length) {
      return;
    }

    const existingResources = resources.value[nodeId] ?? [];
    const incomingTypes = incomingResources.map(resourceCardType).filter(Boolean);
    const responseContainsAdditionalTypes = cardType && incomingTypes.some((type) => type !== cardType);
    const replacementTypes = new Set(
      (responseContainsAdditionalTypes ? incomingTypes : (cardType ? [cardType] : incomingTypes)),
    );
    const incomingIds = new Set(incomingResources.map((resource) => resource?.resource_id).filter(Boolean));
    const retainedResources = existingResources.filter((resource) => (
      !incomingIds.has(resource?.resource_id) && !replacementTypes.has(resourceCardType(resource))
    ));

    resources.value = {
      ...resources.value,
      [nodeId]: [...retainedResources, ...incomingResources],
    };
  }

  async function fetchCurrentProbe() {
    return fetchSessionProfileProbe(sessionId.value);
  }

  function setInfo(message, durationMs = 3000) {
    infoMessage.value = message;
    clearTimeout(setInfo._timer);
    if (durationMs > 0) {
      setInfo._timer = setTimeout(() => {
        infoMessage.value = "";
      }, durationMs);
    }
  }

  function resetLearningState() {
    invalidateRouteEnhancements();
    currentNode.value = "";
    activePath.value = [];
    mastery.value = {};
    knowledgeGraph.value = { nodes: [], edges: [] };
    nodeTitles.value = {};
    resources.value = {};
    agentFeedback.value = [];
    lastDiagnostic.value = null;
    lastMasteryAttribution.value = null;
    messages.value = [];
    probe.value = null;
    probeCollected.value = 0;
    stepLogs.value = [];
    lessonTimer = null;
    contentTimer = null;
    tutorQuestionAttempt = 0;
  }

  function pathIdsFromDto(state) {
    const dtoNodes = state?.learning_path?.nodes;
    if (Array.isArray(dtoNodes) && dtoNodes.length) {
      return dtoNodes
        .map((node) => (typeof node === "string" ? node : node?.id || node?.node_id))
        .filter(Boolean);
    }

    const legacyPath = state?.active_path ?? state?.legacy?.active_path;
    if (Array.isArray(legacyPath)) {
      return legacyPath
        .map((node) => (typeof node === "string" ? node : node?.id || node?.node_id))
        .filter(Boolean);
    }
    return [];
  }

  function nodeTitlesFromDto(state) {
    const titles = {};
    const dtoNodes = state?.learning_path?.nodes;
    if (!Array.isArray(dtoNodes)) {
      return titles;
    }

    dtoNodes.forEach((node) => {
      if (!node || typeof node === "string") {
        return;
      }
      const nodeId = node.id || node.node_id;
      const title = node.title || node.title_cn || node.name;
      if (nodeId && title) {
        titles[nodeId] = title;
      }
    });
    return titles;
  }

  function masteryFromDto(state) {
    const dtoMastery = state?.dynamic_profile?.knowledge_mastery;
    if (dtoMastery && typeof dtoMastery === "object") {
      return dtoMastery;
    }

    const masteryByNode = {};
    const dtoNodes = state?.learning_path?.nodes;
    if (Array.isArray(dtoNodes)) {
      dtoNodes.forEach((node) => {
        if (node?.id) masteryByNode[node.id] = node.mastery ?? 0;
      });
    }
    return Object.keys(masteryByNode).length ? masteryByNode : {};
  }

  function resourcesFromDto(state) {
    if (state?.resources && typeof state.resources === "object") {
      return state.resources;
    }
    return {};
  }

  function currentNodeFromDto(state) {
    return state?.session?.current_node_id
      || state?.learning_path?.current_node_id
      || state?.current_node_id
      || state?.legacy?.current_node_id
      || "";
  }

  function feedbackFromDto(...responses) {
    return responses.find((item) => Array.isArray(item?.agent_feedback))?.agent_feedback ?? [];
  }

  function logsFromDto(...responses) {
    return responses.find((item) => Array.isArray(item?.step_logs))?.step_logs
      ?? responses.find((item) => Array.isArray(item?.pipeline_log))?.pipeline_log
      ?? [];
  }

  function finiteNumberOrNull(value) {
    if (typeof value === "number") {
      return Number.isFinite(value) ? value : null;
    }
    if (typeof value === "string" && value.trim()) {
      const numberValue = Number(value);
      return Number.isFinite(numberValue) ? numberValue : null;
    }
    return null;
  }

  function positiveInteger(value, fallback = 1) {
    const parsed = Number(value);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
  }

  function boundedDuration(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return 0;
    }
    return Math.min(86_400_000, Math.round(parsed));
  }

  function currentResourceDuration(resourceId) {
    return contentTimer?.resourceId === resourceId ? dwellDuration(contentTimer) : 0;
  }

  function applyLearningEventResponse(response) {
    if (!response || typeof response !== "object") {
      return;
    }

    const responseState = response.state ?? response.session_state;
    if (responseState?.learning_path || responseState?.dynamic_profile) {
      hydrateState(responseState);
    }

    const nextMastery = response.knowledge_mastery
      ?? response.dynamic_profile?.knowledge_mastery
      ?? responseState?.dynamic_profile?.knowledge_mastery;
    if (nextMastery && typeof nextMastery === "object") {
      mastery.value = { ...mastery.value, ...nextMastery };
    }

    const attribution = response.mastery_attribution ?? response.attribution ?? null;
    if (attribution) {
      lastMasteryAttribution.value = attribution;
    }
  }

  function diagnosticFromVerifiedEvent(event, attributions = []) {
    if (!event || typeof event !== "object") {
      return null;
    }

    const verifiedEvidence = event.verified_evidence;
    if (!verifiedEvidence || typeof verifiedEvidence !== "object") {
      return null;
    }

    const masteryResult = event.mastery && typeof event.mastery === "object"
      ? event.mastery
      : {};
    const learningResult = event.learning_result && typeof event.learning_result === "object"
      ? event.learning_result
      : {};
    const attribution = Array.isArray(attributions)
      ? attributions.find((item) => item?.event_id === event.event_id) ?? null
      : null;
    const evaluatedNodeId = masteryResult.evaluated_node_id || event.node_id || "";
    const nextNodeId = learningResult.next_node_id || "";
    const review = event.review && typeof event.review === "object" ? event.review : null;

    return {
      eventId: event.event_id || "",
      eventType: event.event_type || "",
      attribution,
      questionResults: Array.isArray(verifiedEvidence.question_results)
        ? verifiedEvidence.question_results
        : [],
      review,
      remediation: review?.remediation ?? null,
      reviewItems: Array.isArray(review?.created_or_updated_items)
        ? review.created_or_updated_items
        : [],
      retestedItems: Array.isArray(review?.retested_items) ? review.retested_items : [],
      requiresRemediation: Boolean(review?.requires_remediation),
      score: finiteNumberOrNull(learningResult.effective_correctness),
      resourceId: event.resource_id || "",
      evaluatedNodeId,
      evaluatedNodeTitle: nodeTitles.value[evaluatedNodeId] || evaluatedNodeId,
      masteryBefore: masteryResult.before,
      masteryAfter: masteryResult.after,
      advancedToNextNode: Boolean(learningResult.advanced_to_next_node),
      nextNodeId,
      nextNodeTitle: nodeTitles.value[nextNodeId] || nextNodeId,
      masteryThreshold: learningResult.mastery_threshold ?? 0.65,
      step_logs: [],
      agent_feedback: [],
    };
  }

  async function restoreLatestDiagnostic(nodeId, {
    targetSessionId = sessionId.value,
    shouldApply = () => true,
  } = {}) {
    if (!nodeId) {
      return null;
    }

    if (shouldApply()) {
      lastDiagnostic.value = null;
    }
    try {
      const history = await fetchSessionLearningEventHistory(targetSessionId, {
        nodeId,
        limit: 100,
      });
      const events = Array.isArray(history?.events) ? history.events : [];
      const attributions = Array.isArray(history?.mastery_attributions)
        ? history.mastery_attributions
        : [];
      const event = [...events].reverse().find((candidate) => (
        (candidate?.event_type === "lesson_completed" || candidate?.event_type === "review_completed")
        && candidate?.verified_evidence
      ));
      const diagnostic = diagnosticFromVerifiedEvent(event, attributions);
      if (diagnostic && shouldApply()) {
        lastDiagnostic.value = diagnostic;
      }
      return diagnostic;
    } catch (error) {
      // Event-history restoration is an enhancement for a reload. The next
      // fresh diagnostic remains usable if a transient request fails.
      if (shouldApply()) {
        console.warn("Unable to restore the latest diagnostic:", error);
      }
      return null;
    }
  }

  function createLearningEvent(eventType, details = {}) {
    if (!LEARNING_EVENT_TYPES.has(eventType)) {
      throw new Error(`Unsupported learning event type: ${eventType}`);
    }

    const targetUserId = String(details.userId ?? userId.value ?? "");
    const targetCourseId = String(details.courseId ?? courseId.value ?? "");
    const eventId = String(details.eventId ?? details.event_id ?? "").trim();
    return {
      event_id: eventId || createEventId(),
      event_type: eventType,
      user_id: targetUserId,
      course_id: targetCourseId,
      node_id: String(details.nodeId ?? currentNode.value ?? ""),
      resource_id: String(details.resourceId ?? ""),
      question_id: String(details.questionId ?? ""),
      duration_ms: boundedDuration(details.durationMs),
      attempt_number: positiveInteger(details.attemptNumber),
      used_hint: Boolean(details.usedHint),
      result: normalizeEventResult(details.result),
    };
  }

  function recordLearningEvent(eventType, details = {}) {
    const payload = createLearningEvent(eventType, details);
    const targetSessionId = buildSessionId(payload.user_id, payload.course_id);
    const request = learningEventQueue.then(async () => {
      let lastError;
      for (let attempt = 1; attempt <= LEARNING_EVENT_MAX_ATTEMPTS; attempt += 1) {
        try {
          return await submitSessionLearningEvent(targetSessionId, payload);
        } catch (error) {
          lastError = error;
          if (attempt >= LEARNING_EVENT_MAX_ATTEMPTS || !isRetryableLearningEventError(error)) {
            throw error;
          }
          await waitForLearningEventRetry(LEARNING_EVENT_RETRY_DELAY_MS * attempt);
        }
      }
      throw lastError;
    });
    learningEventQueue = request.catch(() => undefined);
    return request.then((response) => {
      applyLearningEventResponse(response);
      return response;
    });
  }

  function reportLearningEvent(eventType, details = {}) {
    void recordLearningEvent(eventType, details).catch((error) => {
      // Interaction telemetry should not make the learning surface unusable.
      console.warn(`Unable to record ${eventType}:`, error);
    });
  }

  async function finishContentView() {
    if (!contentTimer) {
      return null;
    }

    const completedView = contentTimer;
    pauseDwellTimer(completedView);
    contentTimer = null;
    return recordLearningEvent("content_viewed", {
      nodeId: completedView.nodeId,
      courseId: completedView.courseId,
      resourceId: completedView.resourceId,
      durationMs: dwellDuration(completedView),
      attemptNumber: completedView.attemptNumber,
      usedHint: completedView.usedHint,
      result: completedView.result,
    });
  }

  async function startLearningSession({ courseId: targetCourseId, nodeId } = {}) {
    const resolvedCourseId = String(targetCourseId ?? courseId.value ?? "");
    const resolvedNodeId = String(nodeId ?? currentNode.value ?? "");
    if (!resolvedCourseId || !resolvedNodeId) {
      return null;
    }

    if (lessonTimer?.courseId === resolvedCourseId && lessonTimer?.nodeId === resolvedNodeId) {
      return null;
    }

    try {
      await finishContentView();
    } catch (error) {
      console.warn("Unable to finish the previous content view:", error);
    }

    lessonTimer = createDwellTimer({ courseId: resolvedCourseId, nodeId: resolvedNodeId });
    return recordLearningEvent("lesson_opened", {
      courseId: resolvedCourseId,
      nodeId: resolvedNodeId,
      durationMs: 0,
      result: { entry: "learning_route" },
    });
  }

  async function recordContentView(details = {}) {
    const resourceId = String(details.resourceId ?? "");
    if (!resourceId) {
      return null;
    }

    const nodeId = String(details.nodeId ?? currentNode.value ?? "");
    const targetCourseId = String(details.courseId ?? courseId.value ?? "");
    if (contentTimer?.resourceId === resourceId
      && contentTimer?.nodeId === nodeId
      && contentTimer?.courseId === targetCourseId) {
      contentTimer.usedHint = contentTimer.usedHint || Boolean(details.usedHint);
      return null;
    }

    try {
      await finishContentView();
    } catch (error) {
      console.warn("Unable to finish the previous content view:", error);
    }

    contentTimer = createDwellTimer({
      nodeId,
      courseId: targetCourseId,
      resourceId,
      attemptNumber: positiveInteger(details.attemptNumber),
      usedHint: Boolean(details.usedHint),
      result: normalizeEventResult(details.result),
    });
    return null;
  }

  function recordHintRequest(details = {}) {
    const resourceId = String(details.resourceId ?? "");
    if (contentTimer?.resourceId === resourceId) {
      contentTimer.usedHint = true;
    }
    return recordLearningEvent("hint_requested", {
      ...details,
      durationMs: details.durationMs ?? currentResourceDuration(resourceId),
      usedHint: true,
    });
  }

  function recordAnswerSelection(details = {}) {
    const resourceId = String(details.resourceId ?? "");
    return recordLearningEvent("answer_selected", {
      ...details,
      durationMs: details.durationMs ?? currentResourceDuration(resourceId),
      result: {
        ...normalizeEventResult(details.result),
        selected_option_index: details.selectedOptionIndex ?? details.result?.selected_option_index,
      },
    });
  }

  function recordCodeRun(details = {}) {
    const resourceId = String(details.resourceId ?? "");
    const result = normalizeEventResult(details.result);
    return recordLearningEvent("code_run", {
      ...details,
      durationMs: details.durationMs ?? currentResourceDuration(resourceId),
      result: {
        ...result,
        ...(Array.isArray(details.testResults) ? { test_results: details.testResults } : {}),
      },
    });
  }

  function recordCodeSubmission(details = {}) {
    const resourceId = String(details.resourceId ?? "");
    const result = normalizeEventResult(details.result);
    return recordLearningEvent("code_submitted", {
      ...details,
      durationMs: details.durationMs ?? currentResourceDuration(resourceId),
      result: {
        ...result,
        ...(Array.isArray(details.testResults) ? { test_results: details.testResults } : {}),
      },
    });
  }

  async function flushLearningActivity() {
    try {
      await finishContentView();
    } catch (error) {
      console.warn("Unable to flush content dwell time:", error);
    }
    if (lessonTimer) {
      pauseDwellTimer(lessonTimer);
    }
  }

  async function endLearningSession() {
    await flushLearningActivity();
    lessonTimer = null;
  }

  function handleDocumentVisibility() {
    const shouldPause = typeof document !== "undefined" && document.visibilityState === "hidden";
    if (shouldPause) {
      pauseDwellTimer(lessonTimer);
      pauseDwellTimer(contentTimer);
      return;
    }
    resumeDwellTimer(lessonTimer);
    resumeDwellTimer(contentTimer);
  }

  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", handleDocumentVisibility);
  }

  function hydrateState(state) {
    if (!state) {
      return;
    }

    activePath.value = pathIdsFromDto(state);
    nodeTitles.value = {
      ...nodeTitles.value,
      ...nodeTitlesFromDto(state),
    };
    mastery.value = masteryFromDto(state);
    capabilityRadar.value = state.dynamic_profile?.capability_radar ?? capabilityRadar.value;
    diagnosticReport.value = state.dynamic_profile?.diagnostic_report_md ?? "";
    resources.value = resourcesFromDto(state);
    agentFeedback.value = state.agent_feedback ?? [];

    // 从持久化的 pipeline_log 提取最新 Agent 运行记录
    const pipelineLog = state.pipeline_log ?? [];
    if (pipelineLog.length) {
      stepLogs.value = pipelineLog.filter((l) => l.agent).slice(-10);
    }

    if (!currentNode.value) {
      const firstPending = activePath.value.find((id) => (mastery.value[id] ?? 0) < 0.65);
      currentNode.value = currentNodeFromDto(state) || firstPending || activePath.value[0] || "";
    }
  }

  function refreshStatuses() {
    const cards = currentCards.value;
    const hasCards = cards.length > 0;
    const hasQuiz = cards.some((card) => card.card_type === "diagnostic_quiz");
    const hasTutorResponse = Boolean(lastDiagnostic.value?.tutor_response ||
      (typeof lastDiagnostic.value === "object" && lastDiagnostic.value !== null));
    const pathLength = activePath.value.length;
    const masteredCount = activePath.value.filter(
      (nodeId) => (mastery.value[nodeId] ?? 0) >= 0.65,
    ).length;
    const radarValues = capabilityRadar.value;
    const hasRadar = Array.isArray(radarValues) && radarValues.some((v) => v !== 0.5);
    const currentStepLogs = lastDiagnostic.value?.step_logs || stepLogs.value;
    const evalLog = currentStepLogs.find((l) => l.agent === "Evaluator");
    const validLog = currentStepLogs.find((l) => l.agent === "Validator");
    const evaluatorCorrectness = finiteNumberOrNull(evalLog?.effective_correctness);

    agentStatuses.value = [
      {
        key: "doc",
        kind: "doc",
        label: "文档智能体",
        phase: hasCards ? `已生成 ${cards.length} 张卡片` : "待命",
        // Resource readiness is binary at this boundary; the backend does not
        // expose a generation percentage, so do not manufacture one here.
        progress: 0,
        active: true,
      },
      {
        key: "quiz",
        kind: "quiz",
        label: "评估智能体",
        phase: hasQuiz ? "测验就绪" : hasCards ? "准备中" : "等待中",
        progress: 0,
        active: true,
      },
      {
        key: "path",
        kind: "path",
        label: "路径规划",
        phase: pathLength ? `${pathLength} 节点 / 已掌握 ${masteredCount}` : "生成中",
        progress: pathLength ? Math.round((masteredCount / pathLength) * 100) : 0,
        active: true,
      },
      {
        key: "eval",
        kind: "eval",
        label: "行为评估",
        phase: !evalLog
          ? "待首次评估"
          : evaluatorCorrectness === null
            ? "评估已完成，暂无准确率"
            : `准确率 ${Math.round(evaluatorCorrectness * 100)}%`,
        progress: 0,
        active: Boolean(evalLog),
      },
      {
        key: "valid",
        kind: "valid",
        label: "质量校验",
        phase: validLog ? `通过率 ${Math.round((validLog.overall_pass_rate ?? 1) * 100)}%` : "待校验",
        progress: validLog ? Math.round((validLog.overall_pass_rate ?? 1) * 100) : 0,
        active: Boolean(validLog),
      },
      {
        key: "profile",
        kind: "profile",
        label: "画像分析",
        phase: hasRadar ? "能力雷达已生成" : hasTutorResponse ? "辅导记录可用" : "等待数据",
        progress: 0,
        active: hasRadar || hasTutorResponse,
      },
    ];
  }

  async function loadKnowledgeGraph(targetCourseId = courseId.value) {
    try {
      const kg = await fetchKnowledgeGraph(targetCourseId);
      knowledgeGraph.value = kg;
      const titles = {};
      (kg.nodes || []).forEach((node) => {
        titles[node.id] = node.title;
      });
      nodeTitles.value = { ...nodeTitles.value, ...titles };
    } catch {
      setInfo("知识图谱加载失败，已回退到本地缓存。");
    }
  }

  async function tryAutoLogin() {
    const token = window.localStorage.getItem("access_token");
    if (!token) {
      return false;
    }

    try {
      const user = await fetchMyProfile();
      currentUser.value = user;
      isLoggedIn.value = true;
      return true;
    } catch (profileError) {
      if (!isAuthenticationError(profileError)) {
        throw profileError;
      }
      try {
        await refreshToken();
        const user = await fetchMyProfile();
        currentUser.value = user;
        isLoggedIn.value = true;
        return true;
      } catch (refreshError) {
        if (!isAuthenticationError(refreshError)) {
          throw refreshError;
        }
        window.localStorage.removeItem("access_token");
        window.localStorage.removeItem("refresh_token");
        return false;
      }
    }
  }

  async function handleLogin(userIdInput, password, captchaToken, captchaAnswer) {
    const result = await login({
      user_id: userIdInput,
      password,
      captcha_token: captchaToken,
      captcha_answer: captchaAnswer,
    });
    currentUser.value = result.user;
    isLoggedIn.value = true;
    bootstrapError.value = "";
    return result;
  }

  async function handleRegister(userIdInput, email, password, captchaToken, captchaAnswer) {
    const result = await register({
      user_id: userIdInput,
      email,
      password,
      captcha_token: captchaToken,
      captcha_answer: captchaAnswer,
    });
    currentUser.value = result.user;
    isLoggedIn.value = true;
    bootstrapError.value = "";
    return result;
  }

  function handleLogout() {
    routePreparationGeneration += 1;
    window.localStorage.removeItem("access_token");
    window.localStorage.removeItem("refresh_token");
    currentUser.value = null;
    isLoggedIn.value = false;
    isBusy.value = false;
    bootMode.value = "login";
    bootstrapError.value = "";
    learningAssets.reset();
    resetLearningState();
  }

  async function submitProbe(values) {
    isSubmittingProbe.value = true;
    try {
      const answer = Array.isArray(values) && values.length === 1 ? values[0] : values;
      const response = await submitSessionProfileInput(sessionId.value, answer);

      if (response.phase === "complete") {
        probe.value = null;
        probeCollected.value = probeTotal.value;
        await initPathAndEnter();
        return;
      }

      probeCollected.value = response.collected ?? probeCollected.value;
      const next = await fetchCurrentProbe();
      probe.value = next.probe;
      probeCollected.value = next.collected ?? probeCollected.value;
    } catch {
      setInfo("提交测评失败，请重试。");
    } finally {
      isSubmittingProbe.value = false;
    }
  }

  async function initPathAndEnter() {
    await initSessionPath(sessionId.value);
    await createSession({ course_id: courseId.value });
    const state = await fetchCurrentSession();
    hydrateState(state);
    await hydrateLearningAssets();
    currentNode.value = activePath.value.find((id) => (mastery.value[id] ?? 0) < 0.65) || activePath.value[0] || "";
    bootMode.value = "ready";
    refreshStatuses();
    return state;
  }

  async function loadAvailableCourses(search) {
    try {
      availableCourses.value = await fetchCourses(search);
    } catch {
      return null;
    }
    return availableCourses.value;
  }

  async function loadUserCourses() {
    const result = await fetchUserCourses();
    enrolledCourses.value = result.courses || [];
    if (result.active_course) {
      activeCourse.value = result.courses.find((course) => course.course_id === result.active_course) || null;
    }
    return result;
  }

  async function bootstrap() {
    invalidateRouteEnhancements();
    bootMode.value = "loading";
    bootstrapError.value = "";
    isBusy.value = true;
    try {
      await loadAvailableCourses();

      const loggedIn = await tryAutoLogin();
      if (!loggedIn) {
        bootMode.value = "login";
        isBusy.value = false;
        return;
      }

      const enrollment = await loadUserCourses();
      if (!enrollment.active_course || !enrollment.courses.length) {
        bootMode.value = "course_selection";
        isBusy.value = false;
        return;
      }

      const state = await fetchCurrentSession();
      hydrateState(state);
      await hydrateLearningAssets();

      if (activePath.value.length) {
        bootMode.value = "ready";
        refreshStatuses();
      } else {
        const probeState = await fetchCurrentProbe();
        if (probeState.phase === "complete") {
          await initPathAndEnter();
        } else {
          probe.value = probeState.probe;
          probeCollected.value = probeState.collected ?? 0;
          bootMode.value = "probe";
        }
      }
    } catch (error) {
      const message = error?.response?.data?.detail || error?.message || "请检查后端服务。";
      bootstrapError.value = `初始化失败：${message}`;
      setInfo(bootstrapError.value, 10000);
      bootMode.value = "login";
    } finally {
      isBusy.value = false;
    }
  }

  async function handleEnrollCourse(courseIdInput) {
    isBusy.value = true;
    try {
      const result = await enrollCourse(courseIdInput);
      activeCourse.value = result.course;
      await loadUserCourses();
      resetLearningState();
      await hydrateLearningAssets();

      const probeState = await fetchCurrentProbe();
      if (probeState.phase === "complete") {
        await initPathAndEnter();
      } else {
        probe.value = probeState.probe;
        probeCollected.value = probeState.collected ?? 0;
        bootMode.value = "probe";
      }
    } catch (error) {
      setInfo(`选课失败：${error?.response?.data?.detail || "请稍后重试"}`);
    } finally {
      isBusy.value = false;
    }
  }

  async function handleSwitchCourse(courseIdInput) {
    if (courseIdInput === activeCourse.value?.course_id) {
      return;
    }

    isBusy.value = true;
    try {
      await switchCourse(courseIdInput);
      await loadUserCourses();
      resetLearningState();

      const state = await fetchCurrentSession();
      hydrateState(state);
      await hydrateLearningAssets();
      if (activePath.value.length) {
        bootMode.value = "ready";
        refreshStatuses();
      } else {
        const probeState = await fetchCurrentProbe();
        if (probeState.phase === "complete") {
          await initPathAndEnter();
        } else {
          probe.value = probeState.probe;
          probeCollected.value = probeState.collected ?? 0;
          bootMode.value = "probe";
        }
      }
    } catch (error) {
      setInfo(`切换课程失败：${error?.response?.data?.detail || "请稍后重试"}`);
    } finally {
      isBusy.value = false;
    }
  }

  async function runRouteEnhancements(context, { silent = false } = {}) {
    if (!isCurrentRouteEnhancement(context)) {
      finishRouteEnhancement(context);
      return { nodeId: context.nodeId, stale: true };
    }

    // Restore the small event-history payload before starting model-backed
    // resource generation. The latter can occupy the API worker for minutes.
    const diagnostic = await restoreLatestDiagnostic(context.nodeId, {
      targetSessionId: context.sessionId,
      shouldApply: () => isCurrentRouteEnhancement(context),
    });
    if (!isCurrentRouteEnhancement(context)) {
      finishRouteEnhancement(context);
      return { nodeId: context.nodeId, diagnostic, stale: true };
    }

    const nodeLabel = nodeTitles.value[context.nodeId] || context.nodeId;
    try {
      const resourceResult = await fetchRouteNodeResources(context);
      if (!isCurrentRouteEnhancement(context)) {
        return { nodeId: context.nodeId, diagnostic, resourceResult, stale: true };
      }

      const nodeResources = Array.isArray(resourceResult?.resources) ? resourceResult.resources : [];
      mergeNodeResources(context.nodeId, nodeResources);
      const cardCount = nodeResources.length || (resources.value[context.nodeId] || []).length;
      if (!silent) {
        setInfo(cardCount ? `${nodeLabel}: ${cardCount} resources loaded.` : `${nodeLabel}: resources synchronized.`);
      }
      return { nodeId: context.nodeId, diagnostic, resourceResult };
    } catch (error) {
      if (isCurrentRouteEnhancement(context)) {
        const message = error?.response?.data?.detail || error?.message || "Unknown error";
        setInfo(`Could not synchronize resources: ${message}`, 10000);
      }
      return { nodeId: context.nodeId, diagnostic, error };
    } finally {
      finishRouteEnhancement(context);
    }
  }

  // This explicit API remains awaitable for callers that intentionally wait
  // for a node's generated resources. Route restoration uses the scheduler
  // below so path readiness and URL repair never wait for model generation.
  async function hydrateNode(nodeId, { silent = false } = {}) {
    if (!nodeId) {
      return null;
    }

    const context = createRouteEnhancementContext(nodeId);
    return runRouteEnhancements(context, { silent });
  }

  function scheduleRouteEnhancements(nodeId, targetCourseId, { silent = true } = {}) {
    if (!nodeId) {
      return null;
    }

    const context = createRouteEnhancementContext(nodeId, targetCourseId);
    // A timer guarantees prepareLearningRoute() resolves with its ready status
    // before the expensive resource request is even issued.
    scheduledRouteEnhancement = setTimeout(() => {
      scheduledRouteEnhancement = null;
      if (!isCurrentRouteEnhancement(context)) {
        finishRouteEnhancement(context);
        return;
      }
      void runRouteEnhancements(context, { silent });
    }, 0);
    return context;
  }

  function prepareLearningRoute(courseIdInput, nodeIdInput = "") {
    const generation = ++routePreparationGeneration;
    invalidateRouteEnhancements();
    isBusy.value = true;
    bootMode.value = "loading";

    const request = routePreparationQueue.then(() => runLearningRoutePreparation(
      courseIdInput,
      nodeIdInput,
      generation,
    ));
    routePreparationQueue = request.catch(() => undefined);
    return request;
  }

  async function runLearningRoutePreparation(courseIdInput, nodeIdInput, generation) {
    const isCurrentPreparation = () => generation === routePreparationGeneration;
    const staleResult = () => ({ status: "stale", courseId: courseIdInput, nodeId: nodeIdInput });

    try {
      if (!isCurrentPreparation()) return staleResult();
      const loggedIn = isLoggedIn.value && currentUser.value
        ? true
        : await tryAutoLogin();
      if (!isCurrentPreparation()) return staleResult();
      if (!loggedIn) {
        bootMode.value = "login";
        return { status: "unauthenticated" };
      }

      await loadAvailableCourses();
      if (!isCurrentPreparation()) return staleResult();
      const enrollment = await loadUserCourses();
      if (!isCurrentPreparation()) return staleResult();
      const targetCourse = enrollment.courses?.find((course) => course.course_id === courseIdInput);
      if (!targetCourse) {
        bootMode.value = "course_selection";
        return { status: "not_enrolled" };
      }

      if (activeCourse.value?.course_id !== courseIdInput) {
        await switchCourse(courseIdInput);
        if (!isCurrentPreparation()) return staleResult();
        await loadUserCourses();
        if (!isCurrentPreparation()) return staleResult();
        resetLearningState();
      }

      let state = await fetchCurrentSession();
      if (!isCurrentPreparation()) return staleResult();
      hydrateState(state);
      await hydrateLearningAssets();
      if (!isCurrentPreparation()) return staleResult();

      if (!activePath.value.length) {
        const probeState = await fetchCurrentProbe();
        if (!isCurrentPreparation()) return staleResult();
        if (probeState.phase === "complete") {
          state = await initPathAndEnter();
          if (!isCurrentPreparation()) return staleResult();
        } else {
          probe.value = probeState.probe;
          probeCollected.value = probeState.collected ?? 0;
          bootMode.value = "probe";
          return { status: "needs_probe" };
        }
      }

      const sessionNodeId = currentNodeFromDto(state);
      const firstPendingNodeId = activePath.value.find((id) => (mastery.value[id] ?? 0) < 0.65);
      const fallbackNodeId = sessionNodeId || firstPendingNodeId || activePath.value[0] || "";
      const resolvedNodeId = activePath.value.includes(nodeIdInput) ? nodeIdInput : fallbackNodeId;
      if (!resolvedNodeId) {
        return { status: "empty_path" };
      }

      currentNode.value = resolvedNodeId;
      bootMode.value = "ready";
      refreshStatuses();
      scheduleRouteEnhancements(resolvedNodeId, courseIdInput, { silent: true });
      return { status: "ready", courseId: courseIdInput, nodeId: resolvedNodeId };
    } catch (error) {
      if (!isCurrentPreparation()) return staleResult();
      const message = error?.response?.data?.detail || error?.message || "Could not synchronize the course state.";
      setInfo(message, 8000);
      return { status: "error", error };
    } finally {
      if (isCurrentPreparation()) {
        isBusy.value = false;
      }
    }
  }

  async function recordNodeBrowse(nodeId) {
    if (!nodeId) {
      return false;
    }

    try {
      await startLearningSession({ nodeId });
      return true;
    } catch (error) {
      const message = error?.response?.data?.detail || error?.message || "Unknown error";
      setInfo(`Could not record the lesson opening: ${message}`, 8000);
      return false;
    }
  }

  async function loadNode(nodeId, silent = false) {
    if (!nodeId) {
      return;
    }

    currentNode.value = nodeId;
    isLoadingNode.value = true;
    const nodeLabel = nodeTitles.value[nodeId] || nodeId;
    setInfo(`正在为「${nodeLabel}」生成学习资源...`);

    try {
      await startLearningSession({ nodeId });
      const resourceResult = await fetchCurrentNodeResources(nodeId);
      const state = await fetchCurrentSession();
      hydrateState(state);
      currentNode.value = currentNodeFromDto(state) || nodeId;
      const nodeResources = Array.isArray(resourceResult?.resources) ? resourceResult.resources : [];
      mergeNodeResources(nodeId, nodeResources);
      const cardCount = nodeResources.length || (resourcesFromDto(state)?.[currentNode.value] || []).length;
      if (!silent) {
        setInfo(cardCount ? `${nodeLabel} 已加载 ${cardCount} 份资源。` : `${nodeLabel} 资源生成完成。`);
      }
    } catch (e) {
      const message = e?.response?.data?.detail || e?.message || "未知错误";
      setInfo(`资源生成失败：${message}`, 10000);
      console.error("loadNode failed:", e);
    } finally {
      isLoadingNode.value = false;
      refreshStatuses();
    }
  }

  async function submitQuiz(submission) {
    const eventKind = typeof submission?.eventKind === "string" ? submission.eventKind : "completion";
    if (eventKind === "answer_submitted") {
      const resourceId = typeof submission?.resourceId === "string" ? submission.resourceId : "";
      const questionId = typeof submission?.questionId === "string" ? submission.questionId : "";
      const selectedOptionIndex = Number(submission?.selectedOptionIndex);
      if (!resourceId || !questionId || !Number.isInteger(selectedOptionIndex)) {
        const error = new Error("Question submission details are incomplete.");
        setInfo(error.message, 6000);
        throw error;
      }

      return recordLearningEvent("answer_submitted", {
        eventId: submission?.eventId,
        nodeId: currentNode.value,
        resourceId,
        questionId,
        durationMs: currentResourceDuration(resourceId),
        attemptNumber: positiveInteger(submission?.attemptNumber),
        usedHint: Boolean(submission?.usedHint),
        result: { answer_index: selectedOptionIndex },
      });
    }

    const resourceId = typeof submission?.resourceId === "string" ? submission.resourceId : "";
    const answers = Array.isArray(submission?.answers)
      ? submission.answers
        .map((answer) => {
          const questionId = answer?.questionId ?? answer?.question_id;
          const selectedOptionIndex = answer?.selectedOptionIndex
            ?? answer?.selected_option_index
            ?? answer?.answer_index;
          const parsedOptionIndex = Number(selectedOptionIndex);
          if (questionId === undefined || questionId === null || !Number.isInteger(parsedOptionIndex)) {
            return null;
          }
          return {
            question_id: String(questionId),
            answer_index: parsedOptionIndex,
          };
        })
        .filter(Boolean)
      : [];

    if (!resourceId || !answers.length) {
      const error = new Error("诊断作答信息不完整，无法提交服务端评分。");
      setInfo(error.message, 6000);
      throw error;
    }

    isLoadingNode.value = true;
    const evaluatedNodeId = currentNode.value;
    const previousMastery = mastery.value[evaluatedNodeId] ?? 0;
    const attemptNumber = positiveInteger(submission?.attemptNumber);
    const usedHint = Boolean(submission?.usedHint);
    const durationMs = currentResourceDuration(resourceId);
    const completionEventType = submission?.isReview === true
      ? "review_completed"
      : "lesson_completed";

    try {
      const response = await recordLearningEvent(completionEventType, {
        eventId: submission?.eventId,
        nodeId: evaluatedNodeId,
        resourceId,
        durationMs,
        attemptNumber,
        usedHint,
        result: {
          evidence_type: "diagnostic_quiz",
          answers,
        },
      });
      let state = response?.state ?? response?.session_state ?? null;
      let stateRefreshError = null;
      try {
        state = await fetchCurrentSession();
        hydrateState(state);
      } catch (error) {
        // The learning event already has an authoritative server receipt.
        // A follow-up GET failure must not unlock the same evidence for a
        // second mastery update under a new event id.
        stateRefreshError = error;
        hydrateState(state);
      }
      currentNode.value = currentNodeFromDto(state)
        || response.current_node_id
        || evaluatedNodeId;

      const nextNodeId = response.next_node_id || currentNodeFromDto(state) || "";
      const responseLogs = logsFromDto(response, state);
      const responseFeedback = feedbackFromDto(response, state);
      const attribution = response.mastery_attribution ?? response.attribution ?? null;
      const verifiedEvidence = response.verified_evidence
        ?? response.event?.verified_evidence
        ?? attribution?.evidence
        ?? {};
      const review = response.review && typeof response.review === "object" ? response.review : null;
      lastDiagnostic.value = {
        eventId: response.event_id || "",
        eventType: completionEventType,
        attribution,
        questionResults: Array.isArray(verifiedEvidence?.question_results)
          ? verifiedEvidence.question_results
          : [],
        review,
        remediation: review?.remediation ?? null,
        reviewItems: Array.isArray(review?.created_or_updated_items)
          ? review.created_or_updated_items
          : [],
        retestedItems: Array.isArray(review?.retested_items) ? review.retested_items : [],
        requiresRemediation: Boolean(review?.requires_remediation),
        score: finiteNumberOrNull(response.effective_correctness),
        resourceId,
        evaluatedNodeId: response.evaluated_node_id || attribution?.node_id || evaluatedNodeId,
        evaluatedNodeTitle: nodeTitles.value[response.evaluated_node_id || evaluatedNodeId] || response.evaluated_node_id || evaluatedNodeId,
        masteryBefore: response.mastery_before ?? attribution?.mastery_before ?? previousMastery,
        masteryAfter: response.mastery_after
          ?? attribution?.mastery_after
          ?? response.knowledge_mastery?.[evaluatedNodeId]
          ?? masteryFromDto(state)?.[evaluatedNodeId]
          ?? previousMastery,
        advancedToNextNode: Boolean(response.advanced_to_next_node),
        nextNodeId,
        nextNodeTitle: nodeTitles.value[nextNodeId] || nextNodeId,
        masteryThreshold: response.mastery_threshold ?? 0.65,
        step_logs: responseLogs,
        agent_feedback: responseFeedback,
      };
      agentFeedback.value = responseFeedback;
      if (responseLogs.length) {
        stepLogs.value = responseLogs.filter((l) => l.agent);
      }

      if (lastDiagnostic.value.advancedToNextNode) {
        setInfo(`诊断通过，已推进到「${lastDiagnostic.value.nextNodeTitle || "下一节点"}」。`);
      } else if (lastDiagnostic.value.requiresRemediation) {
        const count = lastDiagnostic.value.reviewItems.length;
        setInfo(`诊断未达标，已生成 ${count || "对应"} 个补救任务：复盘错题、完成相似题练习后再复测。`, 10000);
      } else {
        setInfo("诊断已记录，当前节点暂未达标，已保留并刷新本节点学习资源。");
      }
      if (stateRefreshError) {
        setInfo("诊断已由服务端记录，但最新会话状态暂未刷新；重新进入本节点即可同步。", 10000);
      }
      return lastDiagnostic.value;
    } catch (error) {
      const failureMessage = error?.response?.data?.detail || error?.message || "提交诊断失败，请重试。";
      lastDiagnostic.value = {
        resourceId,
        evaluatedNodeId,
        failed: true,
        failureMessage,
      };
      setInfo(failureMessage, 8000);
      throw error;
    } finally {
      isLoadingNode.value = false;
      refreshStatuses();
    }
  }

  async function refreshNodeResources(nodeId, options = {}) {
    if (!nodeId) {
      return { ok: false, error: new Error("缺少要加载的学习节点。") };
    }

    const { force, cardType } = normalizeResourceOptions(options);
    const nodeLabel = nodeTitles.value[nodeId] || nodeId;
    isLoadingNode.value = true;
    setInfo(force ? `正在重新生成「${nodeLabel}」的学习资源...` : `正在生成「${nodeLabel}」的学习资源...`);

    try {
      const result = await fetchCurrentNodeResources(nodeId, { force, cardType });
      const nodeResources = Array.isArray(result.resources) ? result.resources : [];
      mergeNodeResources(nodeId, nodeResources, cardType);
      const cardCount = nodeResources.length;
      setInfo(
        result.status === "already_exists"
          ? `「${nodeLabel}」资源已就绪（${cardCount} 份），无需重新生成。`
          : `「${nodeLabel}」已生成 ${cardCount} 份新资源。`
      );
      return { ok: true, result, resources: nodeResources };
    } catch (e) {
      const message = e?.response?.data?.detail || e?.message || "未知错误";
      setInfo(`资源生成失败：${message}`, 10000);
      return { ok: false, error: e };
    } finally {
      isLoadingNode.value = false;
      refreshStatuses();
    }
  }

  async function sendTutorMessage(query, contextType = "concept", codeSnippet = "", errorMessage = "") {
    if (typeof query !== "string" || !query.trim()) {
      return;
    }

    tutorQuestionAttempt += 1;
    reportLearningEvent("tutor_question", {
      nodeId: currentNode.value,
      durationMs: dwellDuration(lessonTimer),
      attemptNumber: tutorQuestionAttempt,
      result: {
        context_type: contextType,
        question_length: query.trim().length,
        has_code_snippet: Boolean(codeSnippet),
        has_error_message: Boolean(errorMessage),
      },
    });

    const ctxLabel = {
      concept: "概念讲解",
      problem_solving: "解题思路",
      code_debug: "代码调试",
      study_advice: "学习建议",
      exam_prep: "考前冲刺",
    }[contextType] || "概念讲解";
    const displayQuery = contextType === "code_debug" && codeSnippet
      ? `[${ctxLabel}]\n\`\`\`\n${codeSnippet}\n\`\`\`\n${errorMessage ? `错误：${errorMessage}\n` : ""}${query.trim()}`
      : query.trim();

    const userMsg = { id: `u-${Date.now()}`, role: "user", content: displayQuery };
    const assistantMsgId = `a-${Date.now()}`;
    messages.value = [
      ...messages.value,
      userMsg,
      {
        id: assistantMsgId,
        role: "assistant",
        content: "",
        mermaidSource: "",
        isStreaming: true,
        streamStatus: "streaming",
      },
    ];

    // Helper: patch the assistant message by id (avoids stale closure on assistantMsg object)
    const patch = (fields) => {
      const idx = messages.value.findIndex((m) => m.id === assistantMsgId);
      if (idx === -1) return;
      const next = [...messages.value];
      next[idx] = { ...next[idx], ...fields };
      messages.value = next;
    };

    let accumulated = "";
    let streamFailure = null;
    let streamCompleted = false;
    let transportClosed = false;
    let idleTimeoutId = null;
    let maxDurationTimeoutId = null;
    let rejectStreamFailure;
    const abortController = new AbortController();
    const streamFailurePromise = new Promise((_, reject) => {
      rejectStreamFailure = reject;
    });

    const stopStreamTimers = () => {
      if (idleTimeoutId !== null) {
        clearTimeout(idleTimeoutId);
        idleTimeoutId = null;
      }
      if (maxDurationTimeoutId !== null) {
        clearTimeout(maxDurationTimeoutId);
        maxDurationTimeoutId = null;
      }
    };

    const onStreamError = (error) => {
      if (transportClosed || streamCompleted || streamFailure) {
        return;
      }
      streamFailure = error instanceof Error ? error : new Error("辅导服务暂时不可用。");
      patch({
        content: accumulated || "发送失败，输入已保留，可以重试。",
        isStreaming: false,
        streamStatus: "error",
        streamError: streamFailure.message,
      });
      abortController.abort(streamFailure);
      rejectStreamFailure(streamFailure);
    };

    const armIdleTimeout = () => {
      if (idleTimeoutId !== null) {
        clearTimeout(idleTimeoutId);
      }
      idleTimeoutId = setTimeout(() => {
        const error = new Error("辅导响应超时，输入已保留，请重试。");
        error.name = "TimeoutError";
        onStreamError(error);
      }, TUTOR_STREAM_IDLE_TIMEOUT_MS);
    };

    const streamHandlers = {
      signal: abortController.signal,
      onToken(token) {
        if (transportClosed || streamCompleted || streamFailure) return;
        armIdleTimeout();
        accumulated += token;
        patch({ content: accumulated });
      },
      onReset() {
        if (transportClosed || streamCompleted || streamFailure) return;
        armIdleTimeout();
        accumulated = "";
        patch({ content: accumulated });
      },
      onDone() {
        if (transportClosed || streamCompleted || streamFailure) return;
        streamCompleted = true;
        patch({ isStreaming: false, streamStatus: "complete", streamError: "" });
        refreshStatuses();
        // A logical SSE done event is terminal even if an intermediary keeps
        // the HTTP body open. Abort the reader so the transport can settle.
        abortController.abort();
      },
      onError: onStreamError,
    };

    armIdleTimeout();
    maxDurationTimeoutId = setTimeout(() => {
      const error = new Error("辅导响应时间过长，输入已保留，请重试。");
      error.name = "TimeoutError";
      onStreamError(error);
    }, TUTOR_STREAM_MAX_DURATION_MS);

    try {
      const transportPromise = Promise.resolve().then(() => streamSessionTutor(
        sessionId.value,
        {
          question: query.trim(),
          context_type: contextType,
          code_snippet: codeSnippet,
          error_message: errorMessage,
        },
        streamHandlers,
      ));
      await Promise.race([transportPromise, streamFailurePromise]);
      if (!streamCompleted && !streamFailure) {
        streamHandlers.onError(new Error("辅导连接意外结束，输入已保留，请重试。"));
      }
    } catch (error) {
      // Some transports reject directly instead of invoking handlers.onError.
      // Route every rejection through the same visible failure state.
      streamHandlers.onError(error);
    } finally {
      stopStreamTimers();
      transportClosed = true;
      abortController.abort();
    }

    if (streamFailure) {
      throw streamFailure;
    }
    return { status: "ok" };
  }

  function getCardLabel(type) {
    return CARD_CN[type] || type;
  }

  function getAgentLabel(type) {
    return AGENT_CN[type] || "文档智能体";
  }

  function parseQuiz() {
    return [];
  }

  return {
    isLoggedIn,
    currentUser,
    userId,
    bootMode,
    bootstrapError,
    isBusy,
    isSubmittingProbe,
    isLoadingNode,
    currentNode,
    activePath,
    mastery,
    capabilityRadar,
    diagnosticReport,
    knowledgeGraph,
    nodeTitles,
    probe,
    probeCollected,
    probeTotal,
    resources,
    lastDiagnostic,
    lastMasteryAttribution,
    currentCards,
    currentNodeTitle,
    currentPathNodes,
    messages,
    infoMessage,
    agentStatuses,
    agentFeedback,
    overallProgress,
    masteredCount,
    activeCourse,
    availableCourses,
    enrolledCourses,
    courseId,
    sessionId,
    handleLogin,
    handleRegister,
    handleLogout,
    getCaptcha,
    bootstrap,
    submitProbe,
    hydrateNode,
    prepareLearningRoute,
    startLearningSession,
    flushLearningActivity,
    endLearningSession,
    recordContentView,
    recordHintRequest,
    recordAnswerSelection,
    recordCodeRun,
    recordCodeSubmission,
    recordLearningEvent,
    recordNodeBrowse,
    loadNode,
    refreshNodeResources,
    submitQuiz,
    sendTutorMessage,
    getCardLabel,
    getAgentLabel,
    parseQuiz,
    refreshStatuses,
    loadAvailableCourses,
    loadKnowledgeGraph,
    handleEnrollCourse,
    handleSwitchCourse,
  };
}

export function useEduAgent() {
  if (!sharedEduAgent) {
    sharedEduAgent = createEduAgent();
  }

  return sharedEduAgent;
}
