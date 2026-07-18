import { computed, ref } from "vue";
import {
  advanceSession,
  buildSessionId,
  createSession,
  enrollCourse,
  fetchCourses,
  fetchKnowledgeGraph,
  fetchMyProfile,
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
import { useLearningAssetsStore } from "../stores/learningAssets";

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

const RESOURCE_CARD_TYPES = [
  "concept_map",
  "code_snippet",
  "interactive_exercise",
  "video_summary",
  "diagnostic_quiz",
];

const TUTOR_STREAM_IDLE_TIMEOUT_MS = 45_000;
const TUTOR_STREAM_MAX_DURATION_MS = 120_000;

export function useEduAgent() {
  const learningAssets = useLearningAssetsStore();
  const isLoggedIn = ref(false);
  const currentUser = ref(null);
  const userId = computed(() => currentUser.value?.user_id ?? "demo_user");

  const activeCourse = ref(null);
  const availableCourses = ref([]);
  const enrolledCourses = ref([]);

  const bootMode = ref("loading");
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

  function tutorHistoryEntries() {
    return Array.isArray(learningAssets.tutorHistory)
      ? learningAssets.tutorHistory
      : [];
  }

  function upsertTutorFeedback({ question = "", response = "", contextType = "concept", mermaidSource = "" } = {}) {
    if (!response) return;

    const tutorFeedback = {
      agent: "Tutor",
      stage: "AI 问答智能体",
      status: "success",
      headline: "本轮问答辅导已完成",
      summary: `已围绕「${currentNodeTitle.value}」完成针对性讲解，回答内容已同步到当前会话。`,
      details_md: response,
      structured_data: {
        query: question,
        context_type: contextType,
      },
      artifacts: {
        mermaid_src: mermaidSource,
      },
    };

    agentFeedback.value = [
      tutorFeedback,
      ...agentFeedback.value.filter((item) => String(item?.agent || "").toLowerCase() !== "tutor"),
    ];
  }

  function syncTutorFeedbackFromHistory(history) {
    let assistantIndex = -1;
    for (let index = history.length - 1; index >= 0; index -= 1) {
      if (history[index]?.role === "assistant" && history[index]?.content) {
        assistantIndex = index;
        break;
      }
    }
    if (assistantIndex < 0) return;

    const assistant = history[assistantIndex];
    let question = null;
    for (let index = assistantIndex - 1; index >= 0; index -= 1) {
      const candidate = history[index];
      if (candidate?.role !== "user") continue;
      if (!assistant.exchange_id || !candidate.exchange_id || candidate.exchange_id === assistant.exchange_id) {
        question = candidate;
        break;
      }
    }

    upsertTutorFeedback({
      question: String(question?.content || ""),
      response: String(assistant.content),
      contextType: assistant.context_type || question?.context_type || "concept",
      mermaidSource: assistant.mermaid_source || "",
    });
  }

  function restoreTutorHistory({ preserveCurrentIfEmpty = false } = {}) {
    const history = tutorHistoryEntries();
    const restored = history
      .filter((entry) => entry && (entry.role === "user" || entry.role === "assistant") && entry.content)
      .map((entry, index) => ({
        id: String(entry.key || entry.id || `restored-${index}`),
        role: entry.role,
        content: String(entry.content),
        mermaidSource: typeof entry.mermaid_source === "string" ? entry.mermaid_source : "",
        isStreaming: false,
        streamStatus: "complete",
        createdAt: entry.created_at || "",
      }));

    if (!restored.length && preserveCurrentIfEmpty && messages.value.length) return;
    messages.value = restored;
    syncTutorFeedbackFromHistory(history);
  }

  async function hydrateLearningAssets(options = {}) {
    await learningAssets.hydrate(sessionId.value);
    restoreTutorHistory(options);
  }

  async function advanceCurrentSession(payload) {
    return advanceSession(sessionId.value, payload);
  }

  async function fetchCurrentNodeResources(nodeId) {
    return fetchSessionResources(sessionId.value, nodeId);
  }

  function resourceCardType(resource) {
    return resource?.resource_type || resource?.card_type || resource?.type || "";
  }

  function resourceListFromResponse(response) {
    const candidates = [
      response?.resources,
      response?.existing_resources,
      response?.data?.resources,
      response?.data?.existing_resources,
    ];
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
  }

  function generationCardsFromEvent(data) {
    const candidates = [
      data?.resource,
      data?.card,
      ...(Array.isArray(data?.resources) ? data.resources : []),
    ];
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
    abortResourceGeneration();
    currentNode.value = "";
    activePath.value = [];
    mastery.value = {};
    resources.value = {};
    agentFeedback.value = [];
    lastDiagnostic.value = null;
    messages.value = [];
    probe.value = null;
    probeCollected.value = 0;
    stepLogs.value = [];
    quizStartedAt = Date.now();
  }

  function pathIdsFromDto(state) {
    const dtoNodes = state?.learning_path?.nodes;
    if (Array.isArray(dtoNodes)) {
      return dtoNodes.map((node) => node?.id).filter(Boolean);
    }
    return [];
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
    return state?.session?.current_node_id || state?.learning_path?.current_node_id || "";
  }

  function feedbackFromDto(...responses) {
    return responses.find((item) => Array.isArray(item?.agent_feedback))?.agent_feedback ?? [];
  }

  function logsFromDto(...responses) {
    return responses.find((item) => Array.isArray(item?.step_logs))?.step_logs
      ?? responses.find((item) => Array.isArray(item?.pipeline_log))?.pipeline_log
      ?? [];
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

  async function loadKnowledgeGraph() {
    try {
      const kg = await fetchKnowledgeGraph(courseId.value);
      knowledgeGraph.value = kg;
      const titles = {};
      (kg.nodes || []).forEach((node) => {
        titles[node.id] = node.title;
      });
      nodeTitles.value = titles;
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
    window.localStorage.removeItem("access_token");
    window.localStorage.removeItem("refresh_token");
    currentUser.value = null;
    isLoggedIn.value = false;
    bootMode.value = "login";
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
    await createSession({ course_id: courseId.value });
    await initSessionPath(sessionId.value);
    const state = await fetchCurrentSession();
    hydrateState(state);
    await hydrateLearningAssets();
    currentNode.value = activePath.value.find((id) => (mastery.value[id] ?? 0) < 0.65) || activePath.value[0] || "";
    bootMode.value = "ready";
    refreshStatuses();
    if (currentNode.value) {
      await loadNode(currentNode.value, true);
    }
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
    bootMode.value = "loading";
    isBusy.value = true;
    try {
      await loadKnowledgeGraph();
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
        if (currentNode.value) {
          await loadNode(currentNode.value, true);
        }
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
      learningAssets.reset();
      resetLearningState();

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
        if (currentNode.value) {
          await loadNode(currentNode.value, true);
        }
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
      learningAssets.reset();
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

  async function loadNode(nodeId, silent = false) {
    if (!nodeId) {
      return;
    }

    abortResourceGeneration();
    const loadGeneration = resourceGenerationVersion;
    currentNode.value = nodeId;
    isLoadingNode.value = true;
    const nodeLabel = nodeTitles.value[nodeId] || nodeId;
    setInfo(`正在为「${nodeLabel}」生成学习资源...`);

    try {
      await advanceCurrentSession({
        interaction_type: "load_node",
        user_id: userId.value,
        course_id: courseId.value,
        current_node_id: nodeId,
        correctness: 0.7,
        time_spent_ratio: 1.0,
        code_pass_rate: 0.7,
      });
      const state = await fetchCurrentSession();
      hydrateState(state, { preservePathOrder: true });
      currentNode.value = nodeId;
      quizStartedAt = Date.now();
      await refreshNodeResources(nodeId, { force: false, silent });
    } catch (e) {
      const message = e?.response?.data?.detail || e?.message || "未知错误";
      setInfo(`资源生成失败：${message}`, 10000);
      console.error("loadNode failed:", e);
    } finally {
      if (loadGeneration === resourceGenerationVersion) {
        isLoadingNode.value = false;
      }
      refreshStatuses();
    }
  }

  async function submitQuiz(submission) {
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
    }

    isLoadingNode.value = true;
    const evaluatedNodeId = currentNode.value;
    const previousMastery = mastery.value[evaluatedNodeId] ?? 0;
    const evaluatedNodeResources = Array.isArray(resources.value[evaluatedNodeId])
      ? [...resources.value[evaluatedNodeId]]
      : [];

    try {
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
      hydrateState(state, { preservePathOrder: true });
      // 提交后服务端可能已指向下一章；返回答题页前保留本章节点和资源。
      if (evaluatedNodeResources.length) {
        resources.value = {
          ...resources.value,
          [evaluatedNodeId]: evaluatedNodeResources,
        };
      }
      try {
        const cachedResources = await fetchCurrentNodeResources(evaluatedNodeId);
        mergeNodeResources(evaluatedNodeId, resourceListFromResponse(cachedResources));
      } catch {
        // 已保留内存快照；缓存读取失败不应影响测验结果提交。
      }
      currentNode.value = evaluatedNodeId;

      const nextNodeId = response.next_node_id || currentNodeFromDto(state) || "";
      const responseLogs = logsFromDto(response, state);
      const responseFeedback = feedbackFromDto(response, state);
      const attribution = response.mastery_attribution ?? response.attribution ?? null;
      const verifiedEvidence = response.verified_evidence ?? response.event?.verified_evidence ?? attribution?.evidence ?? {};
      lastDiagnostic.value = {
        eventId: response.event_id || "",
        score: response.effective_correctness ?? null,
        questionResults: Array.isArray(verifiedEvidence?.question_results) ? verifiedEvidence.question_results : [],
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
        setInfo(`诊断通过，可以前往「${lastDiagnostic.value.nextNodeTitle || "下一节点"}」。`);
      } else {
        setInfo("诊断已记录，系统已根据答题证据更新当前节点掌握度。");
      }
      submission?.onRecorded?.(lastDiagnostic.value);
      quizStartedAt = Date.now();
      return lastDiagnostic.value;
    } catch (error) {
      const message = error?.response?.data?.detail || error?.message || "提交诊断失败。";
      setInfo(message, 8000);
      submission?.onFailure?.(error);
      return null;
    } finally {
      isLoadingNode.value = false;
      refreshStatuses();
    }
  }

  async function refreshNodeResources(nodeId, options = {}) {
    if (!nodeId) return { ok: false };

    const { force, cardTypes } = normalizeResourceOptions(options);
    const silent = Boolean(options?.silent);
    abortResourceGeneration();
    const generation = resourceGenerationVersion;
    const controller = typeof AbortController === "undefined" ? null : new AbortController();
    resourceGenerationController = controller;
    const nodeLabel = nodeTitles.value[nodeId] || nodeId;
    isLoadingNode.value = true;
    setInfo(force ? `正在重新生成「${nodeLabel}」的学习资源...` : `正在生成「${nodeLabel}」的学习资源...`);

    try {
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
    } catch (e) {
      if (e?.name === "AbortError") return { ok: false, stale: true };
      const message = e?.response?.data?.detail || e?.message || "未知错误";
      setInfo(`资源生成失败：${message}`, 10000);
      return { ok: false, error: e };
    } finally {
      if (generation === resourceGenerationVersion) {
        resourceGenerationController = null;
        isLoadingNode.value = false;
        refreshStatuses();
      }
    }
  }

  async function sendTutorMessage(query, contextType = "concept", codeSnippet = "", errorMessage = "") {
    if (typeof query !== "string" || !query.trim()) {
      return;
    }

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
      streamFailure = error instanceof Error ? error : new Error("辅导服务暂时不可用。");
      patch({
        content: accumulated || (streamFailure.status === 401
          ? "登录状态已失效，请重新登录。"
          : "发送失败，请重试。"),
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
        const error = new Error("辅导响应超时，请重试。");
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
        patch({ content: "" });
      },
      onDone() {
        if (transportClosed || streamCompleted || streamFailure) return;
        streamCompleted = true;
        patch({ isStreaming: false, streamStatus: "complete", streamError: "" });
        upsertTutorFeedback({
          question: displayQuery,
          response: accumulated,
          contextType,
        });
        refreshStatuses();
        abortController.abort();
      },
      onError: onStreamError,
    };

    armIdleTimeout();
    maxDurationTimeoutId = setTimeout(() => {
      const error = new Error("辅导响应时间过长，请重试。");
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
        streamHandlers.onError(new Error("辅导连接意外结束，请重试。"));
      }
    } catch (error) {
      streamHandlers.onError(error);
    } finally {
      stopStreamTimers();
      transportClosed = true;
      abortController.abort();
    }

    if (streamFailure) throw streamFailure;
    await hydrateLearningAssets({ preserveCurrentIfEmpty: true });
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
    handleLogin,
    handleRegister,
    handleLogout,
    getCaptcha,
    bootstrap,
    submitProbe,
    loadNode,
    refreshNodeResources,
    submitQuiz,
    sendTutorMessage,
    getCardLabel,
    getAgentLabel,
    parseQuiz,
    refreshStatuses,
    loadAvailableCourses,
    handleEnrollCourse,
    handleSwitchCourse,
    restartProbe,
  };
}
