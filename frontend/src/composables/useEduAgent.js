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
  requestResourceGeneration,
  resetSession,
  streamResourceGeneration,
  streamSessionTutor,
  submitSessionLearningEvent,
  submitSessionProfileInput,
  switchCourse,
} from "../services/eduAgentApi";
import {
  reportResourceCacheRead,
  reportResourceConceptReady,
} from "../services/clientTelemetry";
import { RESOURCE_GENERATION_ASYNC_ENABLED } from "../services/resourceGenerationConfig";
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
const RESOURCE_CARD_TYPES = [
  "concept_map",
  "code_snippet",
  "interactive_exercise",
  "video_summary",
  "diagnostic_quiz",
];
const RESOURCE_STREAM_MAX_RECONNECTS = 2;
const RESOURCE_STREAM_RECONNECT_DELAY_MS = 500;
const RESOURCE_GENERATION_POLL_INTERVAL_MS = 750;
const RESOURCE_GENERATION_POLL_MAX_ATTEMPTS = 80;

function isRetryableLearningEventError(error) {
  const status = Number(error?.response?.status);
  return !Number.isInteger(status) || status <= 0 || status === 408 || status === 429 || status >= 500;
}

function waitForLearningEventRetry(delayMs) {
  return new Promise((resolve) => setTimeout(resolve, delayMs));
}

function monotonicNow() {
  return typeof performance !== "undefined" && typeof performance.now === "function"
    ? performance.now()
    : Date.now();
}

function createDwellTimer(context = {}) {
  const visible = typeof document === "undefined" || document.visibilityState !== "hidden";
  return { ...context, elapsedMs: 0, startedAt: visible ? monotonicNow() : null };
}

function pauseDwellTimer(timer) {
  if (!timer || timer.startedAt === null) return;
  timer.elapsedMs += Math.max(0, monotonicNow() - timer.startedAt);
  timer.startedAt = null;
}

function resumeDwellTimer(timer) {
  if (!timer || timer.startedAt !== null) return;
  timer.startedAt = monotonicNow();
}

function dwellDuration(timer) {
  if (!timer) return 0;
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
  if (!result || typeof result !== "object" || Array.isArray(result)) return {};
  const { score, correctness, mastery, mastery_score, ...safeResult } = result;
  return safeResult;
}

function finiteNumberOrNull(value) {
  const parsed = typeof value === "string" && value.trim() ? Number(value) : value;
  return typeof parsed === "number" && Number.isFinite(parsed) ? parsed : null;
}

function positiveInteger(value, fallback = 1) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function boundedDuration(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.min(86_400_000, Math.round(parsed)) : 0;
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

<<<<<<< HEAD
const RESOURCE_CARD_TYPES = [
  "concept_map",
  "code_snippet",
  "interactive_exercise",
  "video_summary",
  "diagnostic_quiz",
];

export function useEduAgent() {
=======
function createEduAgent() {
  const learningAssets = useLearningAssetsStore();
>>>>>>> origin/main
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
  const resourceGenerationStates = ref({});
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
  let resourceGenerationVersion = 0;
  let resourceGenerationController = null;
  let quizStartedAt = Date.now();

  const currentCards = computed(() => resources.value[currentNode.value] ?? []);
  const currentResourceCardStates = computed(() => (
    resourceGenerationStates.value[currentNode.value]?.cards ?? {}
  ));
  const currentNodeTitle = computed(() => nodeTitles.value[currentNode.value] || currentNode.value || "未选择");
  const masteredCount = computed(() => Object.values(mastery.value).filter((value) => (value ?? 0) >= 0.65).length);
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
  const inFlightGenerationRequests = new Map();
  const resourceGenerationStreams = new Map();

  function invalidateRouteEnhancements() {
    routeEnhancementGeneration += 1;
    if (scheduledRouteEnhancement !== null) {
      clearTimeout(scheduledRouteEnhancement);
      scheduledRouteEnhancement = null;
    }
    cancelResourceGenerationStreams();
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
      resourceTimingStartedAt: monotonicNow(),
      cacheReadReported: false,
      conceptReadyReported: false,
    };
  }

  function createCurrentResourceContext(nodeId) {
    return {
      generation: routeEnhancementGeneration,
      courseId: courseId.value,
      nodeId: String(nodeId || ""),
      sessionId: sessionId.value,
      resourceTimingStartedAt: monotonicNow(),
      cacheReadReported: false,
      conceptReadyReported: false,
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
    if (!context || context.generation !== routeEnhancementGeneration) return;
    isLoadingNode.value = false;
    if (isCurrentRouteEnhancement(context)) refreshStatuses();
  }

  function fetchRouteNodeResources(context) {
    const requestKey = `${context.sessionId}:${context.nodeId}`;
    const existingRequest = inFlightResourceRequests.get(requestKey);
    if (existingRequest) return existingRequest;

    const startedAt = monotonicNow();
    const request = fetchSessionResources(context.sessionId, context.nodeId)
      .then((result) => {
        reportRouteCacheRead(context, result, {
          durationMs: Math.max(0, Math.round(monotonicNow() - startedAt)),
        });
        return result;
      })
      .catch((error) => {
        reportRouteCacheRead(context, null, {
          durationMs: Math.max(0, Math.round(monotonicNow() - startedAt)),
          outcome: "failure",
        });
        throw error;
      })
      .finally(() => {
        if (inFlightResourceRequests.get(requestKey) === request) {
          inFlightResourceRequests.delete(requestKey);
        }
      });
    inFlightResourceRequests.set(requestKey, request);
    return request;
  }

  async function fetchCurrentSession() {
    try {
      return await getSession(sessionId.value);
    } catch (error) {
      if (error?.response?.status !== 404) {
        throw error;
      }
      return createSession({ course_id: courseId.value });
    }
  }

  function restoreTutorHistory() {
    const history = Array.isArray(learningAssets.tutorHistory) ? learningAssets.tutorHistory : [];
    messages.value = history
      .filter((entry) => entry && (entry.role === "user" || entry.role === "assistant") && entry.content)
      .map((entry, index) => ({
        id: String(entry.key || entry.id || `restored-${index}`),
        role: entry.role,
        content: String(entry.content),
        mermaidSource: typeof entry.mermaid_source === "string" ? entry.mermaid_source : "",
        isStreaming: false,
        createdAt: entry.created_at || "",
      }));
  }

<<<<<<< HEAD
=======
  async function hydrateLearningAssets() {
    await learningAssets.hydrate(sessionId.value);
    restoreTutorHistory();
  }

  function normalizeResourceOptions(options = {}) {
    if (typeof options === "boolean") return { force: options, cardType: "", cardTypes: [] };
    const cardType = typeof options?.cardType === "string" ? options.cardType : "";
    const cardTypes = normalizeCardTypes(options?.cardTypes ?? cardType);
    return {
      force: Boolean(options?.force),
      cardType,
      cardTypes,
    };
  }

>>>>>>> origin/main
  async function fetchCurrentNodeResources(nodeId) {
    return fetchSessionResources(sessionId.value, nodeId);
  }

  function resourceCardType(resource) {
    return resource?.resource_type || resource?.card_type || resource?.type || "";
  }

<<<<<<< HEAD
=======
  function mergeNodeResources(nodeId, incomingResources, cardType = "") {
    if (!Array.isArray(incomingResources) || !incomingResources.length) return;

    const existingResources = resources.value[nodeId] ?? [];
    const incomingTypes = incomingResources.map(resourceCardType).filter(Boolean);
    const responseContainsAdditionalTypes = cardType && incomingTypes.some((type) => type !== cardType);
    const replacementTypes = new Set(
      responseContainsAdditionalTypes ? incomingTypes : (cardType ? [cardType] : incomingTypes),
    );
    const incomingIds = new Set(incomingResources.map((resource) => resource?.resource_id).filter(Boolean));
    const retainedResources = existingResources.filter((resource) => (
      !incomingIds.has(resource?.resource_id) && !replacementTypes.has(resourceCardType(resource))
    ));
    resources.value = {
      ...resources.value,
      [nodeId]: [...retainedResources, ...incomingResources],
    };
    markResourceCardsReady(nodeId, incomingResources);
  }

  function normalizeCardTypes(cardTypes) {
    const values = Array.isArray(cardTypes) ? cardTypes : [cardTypes];
    return [...new Set(values
      .map((cardType) => String(cardType || "").trim())
      .filter((cardType) => RESOURCE_CARD_TYPES.includes(cardType)))];
  }

>>>>>>> origin/main
  function resourceListFromResponse(response) {
    const candidates = [
      response?.resources,
      response?.existing_resources,
      response?.data?.resources,
      response?.data?.existing_resources,
    ];
<<<<<<< HEAD
    return candidates.find((value) => Array.isArray(value) && value.length)
      ?? candidates.find(Array.isArray)
      ?? [];
  }

  function mergeNodeResources(nodeId, incomingResources) {
    if (!Array.isArray(incomingResources) || !incomingResources.length) return;
    const incomingTypes = new Set(incomingResources.map(resourceCardType).filter(Boolean));
    const incomingIds = new Set(incomingResources.map((resource) => resource?.resource_id).filter(Boolean));
    const retained = (resources.value[nodeId] ?? []).filter((resource) => (
      !incomingIds.has(resource?.resource_id) && !incomingTypes.has(resourceCardType(resource))
    ));
    resources.value = {
      ...resources.value,
      [nodeId]: [...retained, ...incomingResources],
    };
=======
    return candidates.find((value) => Array.isArray(value)) ?? [];
  }

  function resourceTimingDuration(context) {
    const startedAt = Number(context?.resourceTimingStartedAt);
    if (!Number.isFinite(startedAt)) return 0;
    return Math.max(0, Math.round(monotonicNow() - startedAt));
  }

  function hasConceptMap(resourceCards) {
    return (Array.isArray(resourceCards) ? resourceCards : []).some((resource) => (
      resourceCardType(resource) === "concept_map"
    ));
  }

  function reportRouteCacheRead(context, response, {
    durationMs = 0,
    outcome = "success",
  } = {}) {
    if (!context || context.cacheReadReported) return;
    context.cacheReadReported = true;
    void reportResourceCacheRead({
      durationMs,
      cacheHit: outcome === "success" && hasConceptMap(resourceListFromResponse(response)),
      outcome,
    });
  }

  function reportConceptReady(context, { cacheHit = false } = {}) {
    if (!context || context.conceptReadyReported) return;
    context.conceptReadyReported = true;
    void reportResourceConceptReady({
      durationMs: resourceTimingDuration(context),
      cacheHit,
      outcome: "success",
    });
  }

  function responseCardTypes(response, field) {
    const values = response?.[field];
    if (!Array.isArray(values)) return null;
    return normalizeCardTypes(values.map((value) => (
      typeof value === "string" ? value : resourceCardType(value)
    )));
  }

  function missingResourceCardTypes(nodeResources) {
    const readyTypes = new Set((Array.isArray(nodeResources) ? nodeResources : [])
      .map(resourceCardType)
      .filter(Boolean));
    return RESOURCE_CARD_TYPES.filter((cardType) => !readyTypes.has(cardType));
  }

  function resourceCardState(nodeId, cardType) {
    return resourceGenerationStates.value[nodeId]?.cards?.[cardType] ?? null;
  }

  function updateResourceGenerationState(nodeId, updater) {
    const previous = resourceGenerationStates.value[nodeId] ?? {
      status: "idle",
      jobId: "",
      cards: {},
    };
    const next = updater({ ...previous, cards: { ...previous.cards } });
    resourceGenerationStates.value = {
      ...resourceGenerationStates.value,
      [nodeId]: next,
    };
    return next;
  }

  function updateResourceCardStates(nodeId, cardTypes, update) {
    const normalizedCardTypes = normalizeCardTypes(cardTypes);
    if (!normalizedCardTypes.length) return;
    updateResourceGenerationState(nodeId, (state) => {
      const cards = { ...state.cards };
      normalizedCardTypes.forEach((cardType) => {
        const previous = cards[cardType] ?? { status: "idle", error: "", jobId: "" };
        const patch = typeof update === "function" ? update(previous, cardType) : update;
        cards[cardType] = { ...previous, ...patch };
      });
      return { ...state, cards };
    });
  }

  function setResourceGenerationJob(nodeId, patch) {
    updateResourceGenerationState(nodeId, (state) => ({ ...state, ...patch }));
  }

  function markResourceCardsReady(nodeId, resourceCards) {
    const cardTypes = normalizeCardTypes((Array.isArray(resourceCards) ? resourceCards : [])
      .map(resourceCardType));
    updateResourceCardStates(nodeId, cardTypes, { status: "ready", error: "" });
  }

  function markResourceCardsQueued(nodeId, cardTypes, { jobId = "", status = "queued" } = {}) {
    updateResourceCardStates(nodeId, cardTypes, { status, jobId, error: "" });
  }

  function markResourceCardsFailed(nodeId, cardTypes, error) {
    const message = error instanceof Error ? error.message : String(error || "Resource generation failed.");
    updateResourceCardStates(nodeId, cardTypes, { status: "failed", error: message });
>>>>>>> origin/main
  }

  function generationCardsFromEvent(data) {
    const candidates = [
      data?.resource,
      data?.card,
      ...(Array.isArray(data?.resources) ? data.resources : []),
    ];
<<<<<<< HEAD
    return candidates.filter((candidate) => candidate && resourceCardType(candidate));
  }

  function missingResourceCardTypes(nodeResources) {
    const existingTypes = new Set((nodeResources ?? []).map(resourceCardType).filter(Boolean));
    return RESOURCE_CARD_TYPES.filter((cardType) => !existingTypes.has(cardType));
  }

  function normalizeResourceOptions(options = {}) {
    if (typeof options === "boolean") return { force: options, cardTypes: [] };
    const values = options?.cardTypes ?? options?.cardType ?? [];
    const cardTypes = [...new Set((Array.isArray(values) ? values : [values])
      .map((value) => String(value || "").trim())
      .filter((value) => RESOURCE_CARD_TYPES.includes(value)))];
    return { force: Boolean(options?.force), cardTypes };
  }

  function createEventId(prefix = "event") {
    const randomPart = typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID().replaceAll("-", "")
      : Math.random().toString(16).slice(2);
    return `${prefix}-${Date.now()}-${randomPart}`;
  }

  function abortResourceGeneration() {
    resourceGenerationVersion += 1;
    resourceGenerationController?.abort();
    resourceGenerationController = null;
=======
    if (
      data
      && typeof data === "object"
      && !Array.isArray(data)
      && (data.resource_id || data.id || data.body_markdown || data.structured_payload)
    ) {
      candidates.push(data);
    }
    return candidates.filter((candidate) => (
      candidate
      && typeof candidate === "object"
      && Boolean(resourceCardType(candidate))
    ));
  }

  function generationCardTypesFromEvent(data, fallbackCardTypes = []) {
    const eventTypes = generationCardsFromEvent(data).map(resourceCardType);
    if (data?.card_type) eventTypes.push(data.card_type);
    if (data?.resource_type) eventTypes.push(data.resource_type);
    return normalizeCardTypes(eventTypes.length ? eventTypes : fallbackCardTypes);
  }

  function generationFailureMessage(data, fallback = "Resource generation failed.") {
    return data?.error || data?.detail || data?.message || fallback;
  }

  function cancelResourceGenerationStreams() {
    resourceGenerationStreams.forEach((entry) => {
      entry.cancelled = true;
      if (entry.retryTimer) clearTimeout(entry.retryTimer);
      entry.controller?.abort();
    });
    resourceGenerationStreams.clear();
  }

  function releaseResourceGenerationStream(entry) {
    if (entry.retryTimer) clearTimeout(entry.retryTimer);
    if (resourceGenerationStreams.get(entry.jobId) === entry) {
      resourceGenerationStreams.delete(entry.jobId);
    }
  }

  function isActiveResourceGenerationStream(entry) {
    return Boolean(
      entry
      && !entry.cancelled
      && resourceGenerationStreams.get(entry.jobId) === entry
      && isCurrentRouteEnhancement(entry.context),
    );
  }

  function finishConceptLoading(entry, { notifyReady = true } = {}) {
    if (!entry.cardTypes.includes("concept_map")) return;
    if (notifyReady) reportConceptReady(entry.context);
    finishRouteEnhancement(entry.context);
    if (notifyReady && !entry.conceptReadyNotified) {
      entry.conceptReadyNotified = true;
      entry.onConceptReady?.();
    }
  }

  function failUnresolvedGenerationCards(entry, error) {
    const unresolvedTypes = entry.cardTypes.filter((cardType) => (
      resourceCardState(entry.context.nodeId, cardType)?.status !== "ready"
    ));
    markResourceCardsFailed(entry.context.nodeId, unresolvedTypes, error);
    if (unresolvedTypes.includes("concept_map")) finishConceptLoading(entry, { notifyReady: false });
  }

  function scheduleResourceGenerationReconnect(entry, error) {
    if (!isActiveResourceGenerationStream(entry)) {
      releaseResourceGenerationStream(entry);
      return;
    }
    if (entry.reconnectAttempts >= RESOURCE_STREAM_MAX_RECONNECTS) {
      failUnresolvedGenerationCards(entry, error);
      setResourceGenerationJob(entry.context.nodeId, { status: "failed" });
      releaseResourceGenerationStream(entry);
      return;
    }

    entry.reconnectAttempts += 1;
    entry.retryTimer = setTimeout(() => {
      entry.retryTimer = null;
      void consumeResourceGenerationStream(entry);
    }, RESOURCE_STREAM_RECONNECT_DELAY_MS * entry.reconnectAttempts);
  }

  function scheduleResourceGenerationPoll(entry, error) {
    if (!isActiveResourceGenerationStream(entry)) {
      releaseResourceGenerationStream(entry);
      return;
    }
    entry.pollAttempts += 1;
    if (entry.pollAttempts >= RESOURCE_GENERATION_POLL_MAX_ATTEMPTS) {
      failUnresolvedGenerationCards(entry, error);
      setResourceGenerationJob(entry.context.nodeId, { status: "failed", jobId: entry.jobId });
      releaseResourceGenerationStream(entry);
      return;
    }
    entry.retryTimer = setTimeout(() => {
      entry.retryTimer = null;
      void consumeResourceGenerationPoll(entry);
    }, RESOURCE_GENERATION_POLL_INTERVAL_MS);
  }

  async function consumeResourceGenerationPoll(entry) {
    if (!isActiveResourceGenerationStream(entry)) {
      releaseResourceGenerationStream(entry);
      return;
    }

    try {
      const response = await fetchRouteNodeResources(entry.context);
      if (!isActiveResourceGenerationStream(entry)) {
        releaseResourceGenerationStream(entry);
        return;
      }
      const resourceCards = resourceListFromResponse(response);
      if (resourceCards.length) mergeNodeResources(entry.context.nodeId, resourceCards);
      if (hasConceptMap(resourceCards)) finishConceptLoading(entry);

      const unresolvedTypes = entry.cardTypes.filter((cardType) => (
        resourceCardState(entry.context.nodeId, cardType)?.status !== "ready"
      ));
      if (!unresolvedTypes.length) {
        entry.terminal = true;
        setResourceGenerationJob(entry.context.nodeId, { status: "completed", jobId: entry.jobId });
        releaseResourceGenerationStream(entry);
        return;
      }
      scheduleResourceGenerationPoll(entry, new Error("Resource generation is still pending."));
    } catch (error) {
      scheduleResourceGenerationPoll(entry, error);
    }
  }

  async function consumeResourceGenerationStream(entry) {
    if (!isActiveResourceGenerationStream(entry)) {
      releaseResourceGenerationStream(entry);
      return;
    }

    entry.controller = typeof AbortController === "undefined" ? null : new AbortController();
    let streamError = null;
    try {
      await streamResourceGeneration(entry.jobId, {
        signal: entry.controller?.signal,
        lastEventId: entry.lastEventId,
        onEvent: (event) => {
          if (event?.id) entry.lastEventId = event.id;
        },
        onQueued: () => {
          if (!isActiveResourceGenerationStream(entry)) return;
          setResourceGenerationJob(entry.context.nodeId, { status: "queued", jobId: entry.jobId });
          markResourceCardsQueued(entry.context.nodeId, entry.cardTypes, { jobId: entry.jobId });
        },
        onCardReady: (data) => {
          if (!isActiveResourceGenerationStream(entry)) return;
          const resourceCards = generationCardsFromEvent(data);
          if (!resourceCards.length) return;
          mergeNodeResources(entry.context.nodeId, resourceCards);
          if (resourceCards.some((resource) => resourceCardType(resource) === "concept_map")) {
            finishConceptLoading(entry);
          }
        },
        onCardFailed: (data) => {
          if (!isActiveResourceGenerationStream(entry)) return;
          const failedCardTypes = generationCardTypesFromEvent(data, entry.cardTypes);
          markResourceCardsFailed(entry.context.nodeId, failedCardTypes, generationFailureMessage(data));
          if (failedCardTypes.includes("concept_map")) {
            finishConceptLoading(entry, { notifyReady: false });
          }
          setResourceGenerationJob(entry.context.nodeId, { status: "partial_failed", jobId: entry.jobId });
        },
        onCompleted: (data) => {
          if (!isActiveResourceGenerationStream(entry)) return;
          entry.terminal = true;
          failUnresolvedGenerationCards(entry, "The generation job completed without a card payload.");
          setResourceGenerationJob(entry.context.nodeId, { status: "completed", jobId: entry.jobId });

          // The backend owns the concept-map -> supporting-bundle handoff so
          // a page close or SSE disconnect cannot suppress the remaining
          // cards. Subscribe to the durable child job when this page is live.
          const followUpJobId = String(data?.follow_up_job_id || "");
          const followUpCardTypes = normalizeCardTypes(data?.follow_up_card_types);
          const pendingFollowUpCardTypes = followUpCardTypes.filter((cardType) => (
            resourceCardState(entry.context.nodeId, cardType)?.status !== "ready"
          ));
          if (followUpJobId && pendingFollowUpCardTypes.length) {
            markResourceCardsQueued(entry.context.nodeId, pendingFollowUpCardTypes, { jobId: followUpJobId });
            setResourceGenerationJob(entry.context.nodeId, { status: "queued", jobId: followUpJobId });
            startResourceGenerationStream(entry.context, followUpJobId, {
              cardTypes: pendingFollowUpCardTypes,
            });
          }
        },
        onFailed: (data) => {
          if (!isActiveResourceGenerationStream(entry)) return;
          entry.terminal = true;
          const failedCardTypes = generationCardTypesFromEvent(data, entry.cardTypes);
          markResourceCardsFailed(entry.context.nodeId, failedCardTypes, generationFailureMessage(data));
          if (failedCardTypes.includes("concept_map")) finishConceptLoading(entry, { notifyReady: false });
          setResourceGenerationJob(entry.context.nodeId, { status: "failed", jobId: entry.jobId });
        },
        onError: (error) => {
          streamError = error;
        },
      });
    } catch (error) {
      streamError = error;
    }

    if (!isActiveResourceGenerationStream(entry) || entry.terminal) {
      releaseResourceGenerationStream(entry);
      return;
    }
    scheduleResourceGenerationReconnect(entry, streamError || new Error("Resource generation stream disconnected."));
  }

  function startResourceGenerationStream(context, jobId, options = {}) {
    if (!jobId || !isCurrentRouteEnhancement(context)) return null;
    const existing = resourceGenerationStreams.get(jobId);
    if (existing) return existing;

    const entry = {
      context,
      jobId,
      cardTypes: normalizeCardTypes(options.cardTypes),
      onConceptReady: options.onConceptReady,
      transport: RESOURCE_GENERATION_ASYNC_ENABLED ? "sse" : "poll",
      conceptReadyNotified: false,
      reconnectAttempts: 0,
      pollAttempts: 0,
      retryTimer: null,
      controller: null,
      lastEventId: "",
      terminal: false,
      cancelled: false,
    };
    resourceGenerationStreams.set(jobId, entry);
    if (entry.transport === "sse") {
      void consumeResourceGenerationStream(entry);
    } else {
      void consumeResourceGenerationPoll(entry);
    }
    return entry;
  }

  function generationRequestKey(context, cardTypes, force, priority) {
    return `${context.sessionId}:${context.nodeId}:${Boolean(force)}:${String(priority || "normal")}:${normalizeCardTypes(cardTypes).sort().join(",")}`;
  }

  async function requestGenerationForContext(context, cardTypes, {
    force = false,
    priority = "",
    onConceptReady,
  } = {}) {
    const requestedCardTypes = normalizeCardTypes(cardTypes);
    if (!requestedCardTypes.length || !isCurrentRouteEnhancement(context)) return null;

    const requestKey = generationRequestKey(context, requestedCardTypes, force, priority);
    const inFlightRequest = inFlightGenerationRequests.get(requestKey);
    if (inFlightRequest) return inFlightRequest;

    const request = (async () => {
      try {
        const result = await requestResourceGeneration(context.sessionId, context.nodeId, {
          cardTypes: requestedCardTypes,
          force,
          priority,
        });
        if (!isCurrentRouteEnhancement(context)) return { ...result, stale: true };

        const existingResources = resourceListFromResponse(result);
        if (existingResources.length) mergeNodeResources(context.nodeId, existingResources);

        const resultTypes = new Set(existingResources.map(resourceCardType));
        const acceptedCardTypes = responseCardTypes(result, "requested_card_types") ?? requestedCardTypes;
        const missingCardTypes = responseCardTypes(result, "missing_card_types")
          ?? responseCardTypes(result, "missing_resources");
        const pendingCardTypes = missingCardTypes ?? acceptedCardTypes.filter((cardType) => (
          force || !resultTypes.has(cardType)
        ));
        const excludedCardTypes = requestedCardTypes.filter((cardType) => !acceptedCardTypes.includes(cardType));
        const retainedResources = (resources.value[context.nodeId] ?? []).filter((resource) => (
          excludedCardTypes.includes(resourceCardType(resource))
        ));
        if (retainedResources.length) markResourceCardsReady(context.nodeId, retainedResources);
        const jobId = String(result?.job_id || "");
        if (pendingCardTypes.length) {
          markResourceCardsQueued(context.nodeId, pendingCardTypes, { jobId });
        }
        setResourceGenerationJob(context.nodeId, {
          status: result?.status || (jobId ? "queued" : "completed"),
          jobId,
        });

        let conceptReadyNotified = false;
        const notifyConceptReady = ({ cacheHit = false } = {}) => {
          if (conceptReadyNotified || !requestedCardTypes.includes("concept_map")) return;
          conceptReadyNotified = true;
          reportConceptReady(context, { cacheHit });
          finishRouteEnhancement(context);
          onConceptReady?.();
        };
        if (!force && resultTypes.has("concept_map")) notifyConceptReady({ cacheHit: true });

        if (jobId && pendingCardTypes.length) {
          const monitoredCardTypes = !RESOURCE_GENERATION_ASYNC_ENABLED
            && requestedCardTypes.length === 1
            && requestedCardTypes[0] === "concept_map"
            ? RESOURCE_CARD_TYPES
            : pendingCardTypes;
          startResourceGenerationStream(context, jobId, {
            cardTypes: monitoredCardTypes,
            onConceptReady: () => notifyConceptReady(),
          });
        } else if (pendingCardTypes.length) {
          markResourceCardsFailed(
            context.nodeId,
            pendingCardTypes,
            "The resource generation service did not return a job id.",
          );
          if (pendingCardTypes.includes("concept_map")) finishRouteEnhancement(context);
        }
        return result;
      } catch (error) {
        if (isCurrentRouteEnhancement(context)) {
          markResourceCardsFailed(context.nodeId, requestedCardTypes, error);
          if (requestedCardTypes.includes("concept_map")) finishRouteEnhancement(context);
        }
        throw error;
      }
    })().finally(() => {
      if (inFlightGenerationRequests.get(requestKey) === request) {
        inFlightGenerationRequests.delete(requestKey);
      }
    });

    inFlightGenerationRequests.set(requestKey, request);
    return request;
>>>>>>> origin/main
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
<<<<<<< HEAD
    abortResourceGeneration();
=======
    invalidateRouteEnhancements();
>>>>>>> origin/main
    currentNode.value = "";
    activePath.value = [];
    mastery.value = {};
    knowledgeGraph.value = { nodes: [], edges: [] };
    nodeTitles.value = {};
    resources.value = {};
    resourceGenerationStates.value = {};
    inFlightGenerationRequests.clear();
    agentFeedback.value = [];
    lastDiagnostic.value = null;
    lastMasteryAttribution.value = null;
    messages.value = [];
    probe.value = null;
    probeCollected.value = 0;
    stepLogs.value = [];
<<<<<<< HEAD
    quizStartedAt = Date.now();
=======
    lessonTimer = null;
    contentTimer = null;
    tutorQuestionAttempt = 0;
>>>>>>> origin/main
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
    if (!Array.isArray(dtoNodes)) return titles;

    dtoNodes.forEach((node) => {
      if (!node || typeof node === "string") return;
      const nodeId = node.id || node.node_id;
      const title = node.title || node.title_cn || node.name;
      if (nodeId && title) titles[nodeId] = title;
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

  function currentResourceDuration(resourceId) {
    return contentTimer?.resourceId === resourceId ? dwellDuration(contentTimer) : 0;
  }

  function applyLearningEventResponse(response) {
    if (!response || typeof response !== "object") return;
    const responseState = response.state ?? response.session_state;
    if (responseState?.learning_path || responseState?.dynamic_profile) hydrateState(responseState);

    const nextMastery = response.knowledge_mastery
      ?? response.dynamic_profile?.knowledge_mastery
      ?? responseState?.dynamic_profile?.knowledge_mastery;
    if (nextMastery && typeof nextMastery === "object") {
      mastery.value = { ...mastery.value, ...nextMastery };
    }
    const attribution = response.mastery_attribution ?? response.attribution ?? null;
    if (attribution) lastMasteryAttribution.value = attribution;
  }

  function diagnosticFromVerifiedEvent(event, attributions = []) {
    if (!event?.verified_evidence || typeof event.verified_evidence !== "object") return null;
    const masteryResult = event.mastery && typeof event.mastery === "object" ? event.mastery : {};
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
      questionResults: Array.isArray(event.verified_evidence.question_results)
        ? event.verified_evidence.question_results
        : [],
      review,
      remediation: review?.remediation ?? null,
      reviewItems: Array.isArray(review?.created_or_updated_items) ? review.created_or_updated_items : [],
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
    if (!nodeId) return null;
    if (shouldApply()) lastDiagnostic.value = null;
    try {
      const history = await fetchSessionLearningEventHistory(targetSessionId, { nodeId, limit: 100 });
      const events = Array.isArray(history?.events) ? history.events : [];
      const attributions = Array.isArray(history?.mastery_attributions)
        ? history.mastery_attributions
        : [];
      const event = [...events].reverse().find((candidate) => (
        (candidate?.event_type === "lesson_completed" || candidate?.event_type === "review_completed")
        && candidate?.verified_evidence
      ));
      const diagnostic = diagnosticFromVerifiedEvent(event, attributions);
      if (diagnostic && shouldApply()) lastDiagnostic.value = diagnostic;
      return diagnostic;
    } catch (error) {
      if (shouldApply()) console.warn("Unable to restore the latest diagnostic:", error);
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
          if (attempt >= LEARNING_EVENT_MAX_ATTEMPTS || !isRetryableLearningEventError(error)) throw error;
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
      console.warn(`Unable to record ${eventType}:`, error);
    });
  }

  async function finishContentView() {
    if (!contentTimer) return null;
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
    if (!resolvedCourseId || !resolvedNodeId) return null;
    if (lessonTimer?.courseId === resolvedCourseId && lessonTimer?.nodeId === resolvedNodeId) return null;
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
    if (!resourceId) return null;
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
    if (contentTimer?.resourceId === resourceId) contentTimer.usedHint = true;
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
    return recordLearningEvent("code_run", {
      ...details,
      durationMs: details.durationMs ?? currentResourceDuration(resourceId),
      result: {
        ...normalizeEventResult(details.result),
        ...(Array.isArray(details.testResults) ? { test_results: details.testResults } : {}),
      },
    });
  }

  function recordCodeSubmission(details = {}) {
    const resourceId = String(details.resourceId ?? "");
    return recordLearningEvent("code_submitted", {
      ...details,
      durationMs: details.durationMs ?? currentResourceDuration(resourceId),
      result: {
        ...normalizeEventResult(details.result),
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
    if (lessonTimer) pauseDwellTimer(lessonTimer);
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

  function hydrateState(state, { preservePathOrder = false } = {}) {
    if (!state) {
      return;
    }

    const nextPath = pathIdsFromDto(state);
    if (preservePathOrder && activePath.value.length) {
      const currentOrder = activePath.value.filter((nodeId) => nextPath.includes(nodeId));
      const newNodes = nextPath.filter((nodeId) => !currentOrder.includes(nodeId));
      activePath.value = [...currentOrder, ...newNodes];
    } else {
      activePath.value = nextPath;
    }
    nodeTitles.value = { ...nodeTitles.value, ...nodeTitlesFromDto(state) };
    mastery.value = masteryFromDto(state);
    capabilityRadar.value = state.dynamic_profile?.capability_radar ?? capabilityRadar.value;
    diagnosticReport.value = state.dynamic_profile?.diagnostic_report_md ?? "";
    resources.value = resourcesFromDto(state);
    Object.entries(resources.value).forEach(([nodeId, nodeResources]) => {
      markResourceCardsReady(nodeId, Array.isArray(nodeResources) ? nodeResources : []);
    });
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
    const masteryEntries = Object.entries(mastery.value);
    const masteredCount = masteryEntries.filter(([, v]) => (v ?? 0) >= 0.65).length;
    const radarValues = capabilityRadar.value;
    const hasRadar = Array.isArray(radarValues) && radarValues.some((v) => v !== 0.5);
    const currentStepLogs = lastDiagnostic.value?.step_logs || stepLogs.value;
    const evalLog = currentStepLogs.find((l) => l.agent === "Evaluator");
    const validLog = currentStepLogs.find((l) => l.agent === "Validator");

    agentStatuses.value = [
      {
        key: "doc",
        kind: "doc",
        label: "文档智能体",
        phase: hasCards ? `已生成 ${cards.length} 张卡片` : "待命",
        progress: hasCards ? 100 : 0,
        active: true,
      },
      {
        key: "quiz",
        kind: "quiz",
        label: "评估智能体",
        phase: hasQuiz ? "测验就绪" : hasCards ? "准备中" : "等待中",
        progress: hasQuiz ? 100 : hasCards ? 50 : 0,
        active: true,
      },
      {
        key: "path",
        kind: "path",
        label: "路径规划",
        phase: pathLength ? `${pathLength} 节点 / 已掌握 ${masteredCount}` : "生成中",
        progress: pathLength ? Math.round((masteredCount / pathLength) * 100) : 10,
        active: true,
      },
      {
        key: "eval",
        kind: "eval",
        label: "行为评估",
        phase: evalLog ? `准确率 ${Math.round((evalLog.effective_correctness ?? evalLog.mastery_delta ?? 0.7) * 100)}%` : "待首次评估",
        progress: evalLog ? 100 : 0,
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
        progress: hasRadar ? 100 : hasTutorResponse ? 60 : 0,
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
    } catch {
      try {
        await refreshToken();
        const user = await fetchMyProfile();
        currentUser.value = user;
        isLoggedIn.value = true;
        return true;
      } catch {
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
<<<<<<< HEAD
    await createSession({ course_id: courseId.value });
=======
>>>>>>> origin/main
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
    try {
      const result = await fetchUserCourses();
      enrolledCourses.value = result.courses || [];
      if (result.active_course) {
        activeCourse.value = result.courses.find((course) => course.course_id === result.active_course) || null;
      }
      return result;
    } catch {
      return { courses: [], active_course: "" };
    }
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
    } catch {
      setInfo("初始化失败，请检查后端服务。");
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

  async function restartProbe() {
    const previousMode = bootMode.value;
    isBusy.value = true;
    bootMode.value = "loading";
    try {
      await resetSession(userId.value, courseId.value);
      resetLearningState();
      const probeState = await fetchCurrentProbe();
      probe.value = probeState.probe;
      probeCollected.value = probeState.collected ?? 0;
      bootMode.value = "probe";
    } catch (error) {
      setInfo(`重新开始测试失败：${error?.response?.data?.detail || "请稍后重试"}`);
      bootMode.value = previousMode;
    } finally {
      isBusy.value = false;
    }
  }

  async function runRouteEnhancements(context, { silent = false } = {}) {
    if (!isCurrentRouteEnhancement(context)) {
      finishRouteEnhancement(context);
      return { nodeId: context.nodeId, stale: true };
    }

    const diagnosticPromise = restoreLatestDiagnostic(context.nodeId, {
      targetSessionId: context.sessionId,
      shouldApply: () => isCurrentRouteEnhancement(context),
    });
    const nodeLabel = nodeTitles.value[context.nodeId] || context.nodeId;
    try {
      const resourceResult = await fetchRouteNodeResources(context);
      if (!isCurrentRouteEnhancement(context)) {
        return { nodeId: context.nodeId, resourceResult, stale: true };
      }
      const nodeResources = resourceListFromResponse(resourceResult);
      mergeNodeResources(context.nodeId, nodeResources);
      if (!isCurrentRouteEnhancement(context)) {
        return { nodeId: context.nodeId, resourceResult, stale: true };
      }

      const missingCardTypes = missingResourceCardTypes(resources.value[context.nodeId] ?? []);
      const missingSupportingCardTypes = missingCardTypes.filter((cardType) => cardType !== "concept_map");
      let supportingRequested = false;
      const requestSupportingCards = () => {
        if (supportingRequested || !isCurrentRouteEnhancement(context)) return;
        supportingRequested = true;
        const requestedCardTypes = missingSupportingCardTypes.filter((cardType) => (
          resourceCardState(context.nodeId, cardType)?.status !== "ready"
        ));
        if (!requestedCardTypes.length) return;
        markResourceCardsQueued(context.nodeId, requestedCardTypes);
        void requestGenerationForContext(context, requestedCardTypes, {
          priority: "supporting_bundle",
        }).catch((error) => {
          if (!isCurrentRouteEnhancement(context)) return;
          const message = error?.response?.data?.detail || error?.message || "Unknown error";
          setInfo(`Could not start supporting resources: ${message}`, 10000);
        });
      };

      if (missingCardTypes.includes("concept_map")) {
        markResourceCardsQueued(context.nodeId, ["concept_map"]);
        markResourceCardsQueued(context.nodeId, missingSupportingCardTypes, { status: "waiting" });
        await requestGenerationForContext(context, ["concept_map"], {
          priority: "concept_map",
        });
      } else {
        reportConceptReady(context, { cacheHit: true });
        finishRouteEnhancement(context);
        requestSupportingCards();
      }

      const diagnostic = await diagnosticPromise;
      if (!isCurrentRouteEnhancement(context)) {
        return { nodeId: context.nodeId, diagnostic, resourceResult, stale: true };
      }
      const cardCount = nodeResources.length || (resources.value[context.nodeId] || []).length;
      if (!silent) {
        setInfo(cardCount ? `${nodeLabel}: ${cardCount} resources loaded.` : `${nodeLabel}: resources synchronized.`);
      }
      return { nodeId: context.nodeId, diagnostic, resourceResult };
    } catch (error) {
      if (isCurrentRouteEnhancement(context)) {
        const message = error?.response?.data?.detail || error?.message || "Unknown error";
        setInfo(`资源生成失败：${message}`, 10000);
      }
      finishRouteEnhancement(context);
      return { nodeId: context.nodeId, error };
    }
  }

  async function hydrateNode(nodeId, { silent = false } = {}) {
    if (!nodeId) return null;
    const context = createRouteEnhancementContext(nodeId);
    return runRouteEnhancements(context, { silent });
  }

  function scheduleRouteEnhancements(nodeId, targetCourseId, { silent = true } = {}) {
    if (!nodeId) return null;
    const context = createRouteEnhancementContext(nodeId, targetCourseId);
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
      const loggedIn = isLoggedIn.value && currentUser.value ? true : await tryAutoLogin();
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
      if (!resolvedNodeId) return { status: "empty_path" };

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
      if (isCurrentPreparation()) isBusy.value = false;
    }
  }

  async function recordNodeBrowse(nodeId) {
    if (!nodeId) return false;
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

<<<<<<< HEAD
    abortResourceGeneration();
    const loadGeneration = resourceGenerationVersion;
    currentNode.value = nodeId;
    isLoadingNode.value = true;
=======
    const context = createRouteEnhancementContext(nodeId);
>>>>>>> origin/main
    const nodeLabel = nodeTitles.value[nodeId] || nodeId;
    setInfo(`正在为「${nodeLabel}」生成学习资源...`);
    let delegatedToResourceFlow = false;

    try {
      await startLearningSession({ nodeId });
      if (!isCurrentRouteEnhancement(context)) return { nodeId, stale: true };
      const state = await fetchCurrentSession();
      if (!isCurrentRouteEnhancement(context)) return { nodeId, stale: true };
      hydrateState(state, { preservePathOrder: true });
      currentNode.value = nodeId;
<<<<<<< HEAD
      quizStartedAt = Date.now();
      await refreshNodeResources(nodeId, { force: false, silent });
=======
      delegatedToResourceFlow = true;
      return runRouteEnhancements(context, { silent });
>>>>>>> origin/main
    } catch (e) {
      const message = e?.response?.data?.detail || e?.message || "未知错误";
      setInfo(`资源生成失败：${message}`, 10000);
      console.error("loadNode failed:", e);
      return { nodeId, error: e };
    } finally {
<<<<<<< HEAD
      if (loadGeneration === resourceGenerationVersion) {
        isLoadingNode.value = false;
      }
=======
      if (!delegatedToResourceFlow) finishRouteEnhancement(context);
>>>>>>> origin/main
      refreshStatuses();
    }
  }

  async function submitQuiz(submission) {
<<<<<<< HEAD
    const resourceId = String(submission?.resourceId || "");
    const answers = Array.isArray(submission?.answers)
      ? submission.answers.map((answer) => ({
        question_id: String(answer?.questionId ?? answer?.question_id ?? ""),
        answer_index: Number(answer?.selectedOptionIndex ?? answer?.answer_index),
      })).filter((answer) => answer.question_id && Number.isInteger(answer.answer_index))
      : [];
    if (!resourceId || !answers.length) {
      const error = new Error("诊断答题记录不完整，请重新作答。");
      setInfo(error.message, 8000);
      submission?.onFailure?.(error);
      return null;
=======
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
      ? submission.answers.map((answer) => {
        const questionId = answer?.questionId ?? answer?.question_id;
        const answerIndex = Number(answer?.selectedOptionIndex ?? answer?.selected_option_index ?? answer?.answer_index);
        return questionId !== undefined && Number.isInteger(answerIndex)
          ? { question_id: String(questionId), answer_index: answerIndex }
          : null;
      }).filter(Boolean)
      : [];
    if (!resourceId || !answers.length) {
      const error = new Error("Diagnostic answer evidence is incomplete.");
      setInfo(error.message, 6000);
      throw error;
>>>>>>> origin/main
    }

    isLoadingNode.value = true;
    const evaluatedNodeId = currentNode.value;
    const previousMastery = mastery.value[evaluatedNodeId] ?? 0;
    const completionEventType = submission?.isReview === true ? "review_completed" : "lesson_completed";

    try {
<<<<<<< HEAD
      const response = await submitSessionLearningEvent(sessionId.value, {
        event_id: String(submission?.eventId || createEventId("diagnostic")),
        event_type: submission?.isReview ? "review_completed" : "lesson_completed",
        user_id: userId.value,
        course_id: courseId.value,
        node_id: evaluatedNodeId,
        resource_id: resourceId,
        question_id: "",
        duration_ms: Math.max(0, Math.round(Number(submission?.durationMs) || (Date.now() - quizStartedAt))),
        attempt_number: Math.max(1, Math.round(Number(submission?.attemptNumber) || 1)),
        used_hint: Boolean(submission?.usedHint),
        result: {
          evidence_type: "diagnostic_quiz",
          answers,
        },
      });
      const state = await fetchCurrentSession();
      hydrateState(state);
=======
      const response = await recordLearningEvent(completionEventType, {
        eventId: submission?.eventId,
        nodeId: evaluatedNodeId,
        resourceId,
        durationMs: currentResourceDuration(resourceId),
        attemptNumber: positiveInteger(submission?.attemptNumber),
        usedHint: Boolean(submission?.usedHint),
        result: { evidence_type: "diagnostic_quiz", answers },
      });
      let state = response?.state ?? response?.session_state ?? null;
      let stateRefreshError = null;
      try {
        state = await fetchCurrentSession();
        hydrateState(state);
      } catch (error) {
        // The learning event already has an authoritative server receipt.
        // A follow-up GET failure must not unlock the same evidence for a second mastery update.
        stateRefreshError = error;
        hydrateState(state);
      }
>>>>>>> origin/main
      currentNode.value = currentNodeFromDto(state) || response.current_node_id || evaluatedNodeId;

      const nextNodeId = response.next_node_id || currentNodeFromDto(state) || "";
      const responseLogs = logsFromDto(response, state);
      const responseFeedback = feedbackFromDto(response, state);
      const attribution = response.mastery_attribution ?? response.attribution ?? null;
      const verifiedEvidence = response.verified_evidence ?? response.event?.verified_evidence ?? attribution?.evidence ?? {};
<<<<<<< HEAD
      lastDiagnostic.value = {
        eventId: response.event_id || "",
        score: response.effective_correctness ?? null,
        questionResults: Array.isArray(verifiedEvidence?.question_results) ? verifiedEvidence.question_results : [],
=======
      const review = response.review && typeof response.review === "object" ? response.review : null;
      lastDiagnostic.value = {
        eventId: response.event_id || "",
        eventType: completionEventType,
        attribution,
        questionResults: Array.isArray(verifiedEvidence?.question_results) ? verifiedEvidence.question_results : [],
        review,
        remediation: review?.remediation ?? null,
        reviewItems: Array.isArray(review?.created_or_updated_items) ? review.created_or_updated_items : [],
        retestedItems: Array.isArray(review?.retested_items) ? review.retested_items : [],
        requiresRemediation: Boolean(review?.requires_remediation),
        score: finiteNumberOrNull(response.effective_correctness),
        resourceId,
>>>>>>> origin/main
        evaluatedNodeId: response.evaluated_node_id || attribution?.node_id || evaluatedNodeId,
        evaluatedNodeTitle: nodeTitles.value[response.evaluated_node_id || evaluatedNodeId] || response.evaluated_node_id || evaluatedNodeId,
        masteryBefore: response.mastery_before ?? attribution?.mastery_before ?? previousMastery,
        masteryAfter: response.mastery_after ?? attribution?.mastery_after ?? response.knowledge_mastery?.[evaluatedNodeId] ?? masteryFromDto(state)?.[evaluatedNodeId] ?? previousMastery,
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
        setInfo("Diagnostic recorded; remediation tasks are ready.", 10000);
      } else {
        setInfo("诊断已记录，系统已根据答题证据更新当前节点掌握度。");
      }
<<<<<<< HEAD
      submission?.onRecorded?.(lastDiagnostic.value);
      quizStartedAt = Date.now();
      if (lastDiagnostic.value.advancedToNextNode && currentNode.value) {
        await refreshNodeResources(currentNode.value, { force: false, silent: true });
      }
      return lastDiagnostic.value;
    } catch (error) {
      const message = error?.response?.data?.detail || error?.message || "提交诊断失败。";
      setInfo(message, 8000);
      submission?.onFailure?.(error);
      return null;
=======
      if (stateRefreshError) setInfo("Diagnostic recorded; session refresh is temporarily unavailable.", 10000);
      return lastDiagnostic.value;
    } catch (error) {
      const failureMessage = error?.response?.data?.detail || error?.message || "Diagnostic submission failed.";
      lastDiagnostic.value = { resourceId, evaluatedNodeId, failed: true, failureMessage };
      setInfo(failureMessage, 8000);
      throw error;
>>>>>>> origin/main
    } finally {
      isLoadingNode.value = false;
      refreshStatuses();
    }
  }

  async function refreshNodeResources(nodeId, options = {}) {
<<<<<<< HEAD
    if (!nodeId) return { ok: false };

    const { force, cardTypes } = normalizeResourceOptions(options);
    const silent = Boolean(options?.silent);
    abortResourceGeneration();
    const generation = resourceGenerationVersion;
    const controller = typeof AbortController === "undefined" ? null : new AbortController();
    resourceGenerationController = controller;
=======
    if (!nodeId) return { ok: false, error: new Error("Missing learning node.") };

    const { force, cardType, cardTypes } = normalizeResourceOptions(options);
>>>>>>> origin/main
    const nodeLabel = nodeTitles.value[nodeId] || nodeId;
    const requestedCardTypes = cardTypes.length
      ? cardTypes
      : (cardType ? normalizeCardTypes(cardType) : RESOURCE_CARD_TYPES);
    const context = createCurrentResourceContext(nodeId);
    if (!isCurrentRouteEnhancement(context)) {
      return { ok: false, error: new Error("The learning node changed before generation started.") };
    }

    setInfo(
      force
        ? `正在重新生成「${nodeLabel}」的学习资源...`
        : `正在同步「${nodeLabel}」的学习资源...`,
    );

    try {
<<<<<<< HEAD
      const cachedResult = await fetchCurrentNodeResources(nodeId);
      if (generation !== resourceGenerationVersion || currentNode.value !== nodeId) {
        return { ok: false, stale: true };
      }
      mergeNodeResources(nodeId, resourceListFromResponse(cachedResult));

      const requestedTypes = cardTypes.length ? cardTypes : RESOURCE_CARD_TYPES;
      const missingTypes = missingResourceCardTypes(resources.value[nodeId] ?? []);
      const typesToGenerate = force
        ? requestedTypes
        : requestedTypes.filter((cardType) => missingTypes.includes(cardType));
      if (!typesToGenerate.length) {
        if (!silent) setInfo(`「${nodeLabel}」资源已就绪。`);
        return { ok: true, status: "already_exists", resources: resources.value[nodeId] ?? [] };
      }

      const generationResult = await requestResourceGeneration(sessionId.value, nodeId, {
        cardTypes: typesToGenerate,
        force,
        priority: typesToGenerate.includes("concept_map") ? "concept_map" : "card",
      });
      mergeNodeResources(nodeId, resourceListFromResponse(generationResult));
      if (generation !== resourceGenerationVersion || currentNode.value !== nodeId) {
        return { ok: false, stale: true };
      }

      let jobId = String(generationResult?.job_id || "");
      let streamFailure = null;
      while (jobId && generation === resourceGenerationVersion && currentNode.value === nodeId) {
        let followUpJobId = "";
        await streamResourceGeneration(jobId, {
          signal: controller?.signal,
          onCardReady(data) {
            if (generation !== resourceGenerationVersion || currentNode.value !== nodeId) return;
            mergeNodeResources(nodeId, generationCardsFromEvent(data));
          },
          onCardFailed(data) {
            const message = data?.error || data?.detail || "部分资源生成失败";
            setInfo(message, 8000);
          },
          onCompleted(data) {
            followUpJobId = String(data?.follow_up_job_id || "");
          },
          onFailed(data) {
            streamFailure = new Error(data?.error || data?.detail || "资源生成任务失败");
          },
          onError(error) {
            streamFailure = error;
          },
        });
        jobId = followUpJobId;
      }

      if (generation !== resourceGenerationVersion || currentNode.value !== nodeId) {
        return { ok: false, stale: true };
      }
      const finalResult = await fetchCurrentNodeResources(nodeId);
      mergeNodeResources(nodeId, resourceListFromResponse(finalResult));
      const finalCards = resources.value[nodeId] ?? [];
      if (streamFailure && !finalCards.length) throw streamFailure;
      if (!silent) setInfo(`「${nodeLabel}」已加载 ${finalCards.length} 份学习资源。`);
      return { ok: true, status: "completed", resources: finalCards };
=======
      const readResult = await fetchCurrentNodeResources(nodeId);
      if (!isCurrentRouteEnhancement(context)) {
        return { ok: false, stale: true, error: new Error("The learning node changed during synchronization.") };
      }
      const existingResources = resourceListFromResponse(readResult);
      if (existingResources.length) mergeNodeResources(nodeId, existingResources);

      const existingTypes = new Set(existingResources.map(resourceCardType));
      const cardTypesToGenerate = force
        ? requestedCardTypes
        : requestedCardTypes.filter((type) => !existingTypes.has(type));
      if (!cardTypesToGenerate.length) {
        setInfo(`「${nodeLabel}」资源已就绪，无需重新生成。`);
        return { ok: true, result: readResult, resources: existingResources, status: "already_exists" };
      }

      markResourceCardsQueued(nodeId, cardTypesToGenerate, { status: "queued" });
      const startsConceptFirstBundle = !force
        && cardTypesToGenerate.length === 1
        && cardTypesToGenerate[0] === "concept_map";
      if (startsConceptFirstBundle) {
        markResourceCardsQueued(
          nodeId,
          missingResourceCardTypes(resources.value[nodeId] ?? []).filter((cardType) => cardType !== "concept_map"),
          { status: "waiting" },
        );
      }
      const result = await requestGenerationForContext(context, cardTypesToGenerate, {
        force,
        priority: cardTypesToGenerate.includes("concept_map") ? "concept_map" : "card",
      });
      setInfo(`「${nodeLabel}」已提交 ${cardTypesToGenerate.length} 张资源的生成任务。`);
      return { ok: true, result, resources: existingResources, status: result?.status || "queued" };
>>>>>>> origin/main
    } catch (e) {
      if (e?.name === "AbortError") return { ok: false, stale: true };
      const message = e?.response?.data?.detail || e?.message || "未知错误";
      setInfo(`资源生成失败：${message}`, 10000);
      return { ok: false, error: e };
    } finally {
<<<<<<< HEAD
      if (generation === resourceGenerationVersion) {
        resourceGenerationController = null;
        isLoadingNode.value = false;
        refreshStatuses();
      }
=======
      refreshStatuses();
>>>>>>> origin/main
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
      if (idleTimeoutId !== null) clearTimeout(idleTimeoutId);
      if (maxDurationTimeoutId !== null) clearTimeout(maxDurationTimeoutId);
      idleTimeoutId = null;
      maxDurationTimeoutId = null;
    };
    const onStreamError = (error) => {
      if (transportClosed || streamCompleted || streamFailure) return;
      streamFailure = error instanceof Error ? error : new Error("Tutor service is unavailable.");
      patch({
        content: accumulated || "Send failed. Your draft was preserved for retry.",
        isStreaming: false,
        streamStatus: "error",
        streamError: streamFailure.message,
      });
      abortController.abort(streamFailure);
      rejectStreamFailure(streamFailure);
    };
    const armIdleTimeout = () => {
      if (idleTimeoutId !== null) clearTimeout(idleTimeoutId);
      idleTimeoutId = setTimeout(() => {
        const error = new Error("Tutor response timed out. Your draft was preserved for retry.");
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
        abortController.abort();
      },
      onError: onStreamError,
    };

    armIdleTimeout();
    maxDurationTimeoutId = setTimeout(() => {
      const error = new Error("Tutor response exceeded the maximum duration.");
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
        streamHandlers.onError(new Error("Tutor connection ended unexpectedly."));
      }
    } catch (error) {
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

  function parseQuiz(content = "") {
    const lines = content
      .split(/[\n。；;]/)
      .map((line) => line.trim())
      .filter((line) => line.length > 12);

    return [
      {
        id: "q1",
        prompt: "根据当前资源，选择最贴合核心概念的一项。",
        options: [
          lines[0] || "继续阅读后作答",
          "与时间复杂度无关",
          "仅适用于图算法",
          "以上都不对",
        ],
        answer: 0,
      },
      {
        id: "q2",
        prompt: "以下哪项描述与资源内容一致？",
        options: [
          lines[1] || lines[0] || "继续阅读",
          "二分查找总是最优",
          "所有算法都是 O(1)",
          "以上都不对",
        ],
        answer: 0,
      },
    ];
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
    resourceGenerationStates,
    lastDiagnostic,
    lastMasteryAttribution,
    currentCards,
    currentResourceCardStates,
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
    restartProbe,
  };
}

export function useEduAgent() {
  if (!sharedEduAgent) sharedEduAgent = createEduAgent();
  return sharedEduAgent;
}
