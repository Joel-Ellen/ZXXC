import { computed, reactive, ref } from "vue";
import {
  askTutor,
  fetchKnowledgeGraph,
  fetchProbe,
  fetchState,
  initLearningPath,
  runPipelineStep,
  submitProbeAnswer,
} from "../services/eduAgentApi";

const NODE_TITLES = {
  N01: "算法复杂度分析",
  N02: "线性表与顺序存储",
  N03: "链表与链式存储",
  N04: "栈及其应用",
  N05: "队列及其应用",
  N06: "树与二叉树基础",
  N07: "二叉搜索树",
  N08: "AVL 平衡树",
  N09: "散列表与哈希",
  N10: "图的基本概念与存储",
  N11: "图的遍历 DFS/BFS",
  N12: "最小生成树",
  N13: "最短路径算法",
  N14: "拓扑排序与关键路径",
  N15: "排序算法基础",
  N16: "高级排序算法",
  N17: "查找与索引技术",
  N18: "动态规划入门",
  N19: "贪心算法与回溯",
  N20: "数据结构综合应用",
};

const CARD_LABELS = {
  concept_map: "概念导图",
  code_snippet: "代码示例",
  interactive_exercise: "互动练习",
  video_summary: "视频摘要",
  diagnostic_quiz: "诊断测验",
};

const CARD_AGENT_LABELS = {
  concept_map: "Doc Agent",
  code_snippet: "Doc Agent",
  interactive_exercise: "Tutor Agent",
  video_summary: "Doc Agent",
  diagnostic_quiz: "Quiz Agent",
};

function toPercent(value) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function makeDefaultStatuses() {
  return [
    { key: "doc", label: "Doc Agent", kind: "doc", phase: "待命", progress: 0, active: false },
    { key: "quiz", label: "Quiz Agent", kind: "quiz", phase: "等待中", progress: 0, active: false },
    { key: "path", label: "Path Agent", kind: "doc", phase: "路径就绪", progress: 100, active: true },
  ];
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function parseQuizFromContent(content = "") {
  const lines = content
    .split(/[\n。；;]/)
    .map((line) => line.trim())
    .filter((line) => line.length > 18);

  const fallback = [
    "根据当前资源，选择最贴合核心概念的一项。",
    "根据当前资源，选择最接近实践建议的一项。",
  ];

  return fallback.map((prompt, index) => {
    const excerpt = lines[index] || lines[0] || "继续阅读卡片内容后作答。";
    return {
      id: `q-${index}`,
      prompt,
      options: [
        excerpt.slice(0, 72),
        "该知识点无需关注时间复杂度",
        "该知识点只适用于图算法",
        "以上都不符合",
      ],
      answer: 0,
    };
  });
}

function createStreamObject() {
  return reactive({ latest: "", done: false });
}

export function useEduAgent() {
  const userId = ref("demo_user");
  const bootMode = ref("loading");
  const isBusy = ref(false);
  const isSubmittingProbe = ref(false);
  const isLoadingNode = ref(false);
  const currentNode = ref("");
  const activePath = ref([]);
  const currentCourse = ref("数据结构智能伴学");
  const mastery = ref({});
  const capabilityRadar = ref([0.52, 0.48, 0.54, 0.46, 0.58]);
  const diagnosticReport = ref("");
  const cEpoch = ref(0);
  const knowledgeGraph = ref({ nodes: [], edges: [] });
  const probe = ref(null);
  const probeCollected = ref(0);
  const probeTotal = ref(6);
  const resources = ref({});
  const messages = ref([
    {
      id: "welcome-message",
      role: "assistant",
      content: "欢迎来到 EduAgent。完成冷启动探针后，我们会自动生成你的个性化学习路径。",
      mermaidSource: "",
      isStreaming: false,
    },
  ]);
  const assistantDeliveryCount = ref(0);
  const agentStatuses = ref(makeDefaultStatuses());
  const pipelineLogs = ref([]);
  const infoMessage = ref("");

  const currentCards = computed(() => resources.value[currentNode.value] ?? []);
  const currentNodeTitle = computed(() => NODE_TITLES[currentNode.value] ?? currentNode.value ?? "未选择节点");
  const masteredCount = computed(
    () => Object.values(mastery.value).filter((value) => (value ?? 0) >= 0.65).length,
  );
  const overallProgress = computed(() => {
    if (!activePath.value.length) {
      return 0;
    }
    return Math.round((masteredCount.value / activePath.value.length) * 100);
  });
  const currentPathNodes = computed(() =>
    activePath.value.map((id, index) => ({
      id,
      order: index + 1,
      title: NODE_TITLES[id] ?? id,
      mastery: mastery.value[id] ?? 0,
    })),
  );

  function hydrateState(state) {
    activePath.value = state.active_path ?? [];
    mastery.value = state.dynamic_profile?.knowledge_mastery ?? {};
    capabilityRadar.value = state.dynamic_profile?.capability_radar ?? capabilityRadar.value;
    diagnosticReport.value = state.dynamic_profile?.diagnostic_report_md ?? diagnosticReport.value;
    resources.value = state.generated_resources ?? {};
    cEpoch.value = state.c_epoch ?? 0;
    pipelineLogs.value = state.pipeline_log ?? [];

    if (!currentNode.value) {
      const firstPending = activePath.value.find((nodeId) => (mastery.value[nodeId] ?? 0) < 0.65);
      currentNode.value = state.current_node_id || firstPending || activePath.value[0] || "";
    }
  }

  function setInfo(message) {
    infoMessage.value = message;
    window.clearTimeout(setInfo.timeoutId);
    setInfo.timeoutId = window.setTimeout(() => {
      infoMessage.value = "";
    }, 2800);
  }

  async function loadGraphIfNeeded() {
    if (knowledgeGraph.value.nodes.length) {
      return;
    }
    try {
      knowledgeGraph.value = await fetchKnowledgeGraph();
    } catch (error) {
      setInfo("知识图谱暂时不可用，已回退到路径树视图。");
    }
  }

  async function refreshState() {
    const state = await fetchState(userId.value);
    hydrateState(state);
    return state;
  }

  function setIdleStatuses() {
    agentStatuses.value = [
      { key: "doc", label: "Doc Agent", kind: "doc", phase: currentCards.value.length ? "资源已同步" : "待命", progress: currentCards.value.length ? 100 : 0, active: currentCards.value.length > 0 },
      { key: "quiz", label: "Quiz Agent", kind: "quiz", phase: currentCards.value.some((card) => card.card_type === "diagnostic_quiz") ? "测验待执行" : "等待中", progress: currentCards.value.some((card) => card.card_type === "diagnostic_quiz") ? 100 : 0, active: true },
      { key: "path", label: "Path Agent", kind: "doc", phase: activePath.value.length ? `主路径 ${activePath.value.length} 节点` : "路径生成中", progress: activePath.value.length ? 100 : 12, active: true },
    ];
  }

  async function animateResourceGeneration() {
    const frames = [
      [
        { key: "doc", label: "Doc Agent", kind: "doc", phase: "解析节点结构", progress: 24, active: true },
        { key: "quiz", label: "Quiz Agent", kind: "quiz", phase: "题型装配中", progress: 6, active: true },
        { key: "path", label: "Path Agent", kind: "doc", phase: "路径稳定", progress: 100, active: true },
      ],
      [
        { key: "doc", label: "Doc Agent", kind: "doc", phase: "多模态资源生成中", progress: 58, active: true },
        { key: "quiz", label: "Quiz Agent", kind: "quiz", phase: "诊断题校验中", progress: 38, active: true },
        { key: "path", label: "Path Agent", kind: "doc", phase: "依赖链就绪", progress: 100, active: true },
      ],
      [
        { key: "doc", label: "Doc Agent", kind: "doc", phase: "内容安全校验", progress: 84, active: true },
        { key: "quiz", label: "Quiz Agent", kind: "quiz", phase: "评分策略同步", progress: 72, active: true },
        { key: "path", label: "Path Agent", kind: "doc", phase: "主路径已锁定", progress: 100, active: true },
      ],
    ];

    for (const frame of frames) {
      agentStatuses.value = frame;
      await sleep(220);
    }
  }

  async function bootstrap() {
    bootMode.value = "loading";
    isBusy.value = true;

    try {
      await Promise.all([refreshState(), loadGraphIfNeeded()]);
      if (activePath.value.length) {
        bootMode.value = "ready";
        if (currentNode.value) {
          await loadNode(currentNode.value, { silent: true });
        }
      } else {
        const probeState = await fetchProbe(userId.value);
        if (probeState.phase === "complete") {
          await initPathAndEnter();
        } else {
          probe.value = probeState.probe;
          probeCollected.value = probeState.collected ?? 0;
          bootMode.value = "probe";
        }
      }
    } catch (error) {
      setInfo("初始化失败，工作台已进入离线回退模式。");
      bootMode.value = "ready";
    } finally {
      isBusy.value = false;
      setIdleStatuses();
    }
  }

  async function initPathAndEnter() {
    await initLearningPath(userId.value);
    const state = await refreshState();
    currentNode.value =
      activePath.value.find((nodeId) => (mastery.value[nodeId] ?? 0) < 0.65) ||
      state.current_node_id ||
      activePath.value[0] ||
      "";
    bootMode.value = "ready";
    setIdleStatuses();
    if (currentNode.value) {
      await loadNode(currentNode.value, { silent: true });
    }
  }

  async function submitProbe(values) {
    isSubmittingProbe.value = true;
    try {
      const answer = Array.isArray(values) && values.length === 1 ? values[0] : values;
      const response = await submitProbeAnswer(userId.value, answer);
      if (response.phase === "complete") {
        probe.value = null;
        probeCollected.value = probeTotal.value;
        await initPathAndEnter();
        return;
      }

      probeCollected.value = response.collected ?? probeCollected.value;
      const next = await fetchProbe(userId.value);
      probe.value = next.probe;
      probeCollected.value = next.collected ?? probeCollected.value;
      bootMode.value = "probe";
    } catch (error) {
      setInfo("探针提交失败，请稍后重试。");
    } finally {
      isSubmittingProbe.value = false;
    }
  }

  async function loadNode(nodeId, options = {}) {
    if (!nodeId) {
      return;
    }

    currentNode.value = nodeId;
    if (resources.value[nodeId]?.length) {
      setIdleStatuses();
      return;
    }

    isLoadingNode.value = true;
    if (!options.silent) {
      setInfo(`正在装配 ${NODE_TITLES[nodeId] ?? nodeId} 的学习资源。`);
    }

    try {
      await animateResourceGeneration();
      await runPipelineStep({
        user_id: userId.value,
        current_node_id: nodeId,
        correctness: 0.7,
        time_spent_ratio: 1.0,
        code_pass_rate: 0.7,
      });
      await refreshState();
      currentNode.value = nodeId;
    } catch (error) {
      setInfo("资源生成失败，请稍后重试。");
    } finally {
      isLoadingNode.value = false;
      setIdleStatuses();
    }
  }

  async function submitQuiz(score) {
    isLoadingNode.value = true;
    agentStatuses.value = [
      { key: "doc", label: "Doc Agent", kind: "doc", phase: "结果回传中", progress: 100, active: true },
      { key: "quiz", label: "Quiz Agent", kind: "quiz", phase: "评分中", progress: 68, active: true },
      { key: "path", label: "Path Agent", kind: "doc", phase: "重算后续路径", progress: 42, active: true },
    ];

    try {
      await runPipelineStep({
        user_id: userId.value,
        correctness: score,
        time_spent_ratio: 1.0,
        code_pass_rate: score,
      });
      await refreshState();
      currentNode.value = activePath.value.includes(currentNode.value) ? currentNode.value : activePath.value[0] ?? "";
    } catch (error) {
      setInfo("测验提交失败，请稍后重试。");
    } finally {
      isLoadingNode.value = false;
      setIdleStatuses();
    }
  }

  async function streamAssistantMessage(message, text, mermaidSource) {
    const chunkSize = 18;
    for (let cursor = 0; cursor < text.length; cursor += chunkSize) {
      message.tokenStream.latest = text.slice(cursor, cursor + chunkSize);
      await sleep(8);
    }
    message.content = text;
    message.mermaidSource = mermaidSource;
    message.isStreaming = false;
    message.tokenStream.done = true;
    assistantDeliveryCount.value += 1;
  }

  async function sendTutorMessage(query) {
    if (!query.trim()) {
      return;
    }

    const userMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: query.trim(),
      mermaidSource: "",
      isStreaming: false,
    };
    const assistantMessage = {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      mermaidSource: "",
      tokenStream: createStreamObject(),
      isStreaming: true,
    };
    messages.value = [...messages.value, userMessage, assistantMessage];

    try {
      const data = await askTutor({ user_id: userId.value, query: query.trim() });
      const response = data.tutor_response ?? {};
      const answer =
        response.text_explanation?.trim() ||
        "当前辅导结果为空，请尝试换一种提问方式。";
      const mermaidSource = response.mermaid_src?.trim() ?? "";
      await streamAssistantMessage(assistantMessage, answer, mermaidSource);
    } catch (error) {
      await streamAssistantMessage(
        assistantMessage,
        "辅导服务暂时不可用，请稍后再试。",
        "",
      );
    }
  }

  function getNodeTitle(nodeId) {
    return NODE_TITLES[nodeId] ?? nodeId;
  }

  function getCardLabel(cardType) {
    return CARD_LABELS[cardType] ?? cardType;
  }

  function getAgentLabel(cardType) {
    return CARD_AGENT_LABELS[cardType] ?? "Doc Agent";
  }

  return {
    userId,
    bootMode,
    isBusy,
    isSubmittingProbe,
    isLoadingNode,
    currentNode,
    activePath,
    currentCourse,
    mastery,
    capabilityRadar,
    diagnosticReport,
    cEpoch,
    knowledgeGraph,
    probe,
    probeCollected,
    probeTotal,
    resources,
    currentCards,
    currentNodeTitle,
    currentPathNodes,
    messages,
    assistantDeliveryCount,
    agentStatuses,
    overallProgress,
    masteredCount,
    infoMessage,
    bootstrap,
    submitProbe,
    loadNode,
    submitQuiz,
    sendTutorMessage,
    getNodeTitle,
    getCardLabel,
    getAgentLabel,
    parseQuizFromContent,
    refreshState,
  };
}
