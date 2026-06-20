import { computed, reactive, ref } from "vue";
import {
  askTutor, enrollCourse, fetchCourses, fetchKnowledgeGraph, fetchMyProfile,
  fetchProbe, fetchState, fetchUserCourses, getCaptcha, initLearningPath,
  login, refreshToken, register, runPipelineStep, submitProbeAnswer, switchCourse,
} from "../services/eduAgentApi";

// ── 卡片类型 & 角色标签 (全中文) ──
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

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── 导出入口 ──
export function useEduAgent() {
  // --- 认证状态 ---
  const isLoggedIn = ref(false);
  const currentUser = ref(null);
  const userId = computed(() => currentUser.value?.user_id ?? "demo_user");

  // --- 课程状态 ---
  const activeCourse = ref(null);
  const availableCourses = ref([]);
  const enrolledCourses = ref([]);

  // --- 工作台状态 ---
  const bootMode = ref("loading"); // loading | login | course_selection | probe | ready
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
  const messages = ref([]);
  const infoMessage = ref("");
  const agentStatuses = ref([
    { key: "doc", kind: "doc", label: "文档智能体", phase: "待命", progress: 0, active: false },
    { key: "quiz", kind: "quiz", label: "评估智能体", phase: "等待中", progress: 0, active: false },
    { key: "path", kind: "path", label: "路径规划", phase: "未启动", progress: 0, active: false },
  ]);

  // --- 计算属性 ---
  const currentCards = computed(() => resources.value[currentNode.value] ?? []);
  const currentNodeTitle = computed(() => nodeTitles.value[currentNode.value] || currentNode.value || "未选择");
  const masteredCount = computed(() => Object.values(mastery.value).filter(v => (v ?? 0) >= 0.65).length);
  const overallProgress = computed(() => activePath.value.length ? Math.round((masteredCount.value / activePath.value.length) * 100) : 0);
  const currentPathNodes = computed(() =>
    activePath.value.map((id, i) => ({
      id, order: i + 1,
      title: nodeTitles.value[id] || id,
      mastery: mastery.value[id] ?? 0,
    }))
  );

  // --- 工具 ---
  function setInfo(msg) {
    infoMessage.value = msg;
    clearTimeout(setInfo._t);
    setInfo._t = setTimeout(() => infoMessage.value = "", 3000);
  }

  function hydrateState(state) {
    if (!state) return;
    activePath.value = state.active_path ?? [];
    mastery.value = state.dynamic_profile?.knowledge_mastery ?? {};
    capabilityRadar.value = state.dynamic_profile?.capability_radar ?? capabilityRadar.value;
    diagnosticReport.value = state.dynamic_profile?.diagnostic_report_md ?? "";
    resources.value = state.generated_resources ?? {};
    if (!currentNode.value) {
      const first = activePath.value.find(id => (mastery.value[id] ?? 0) < 0.65);
      currentNode.value = state.current_node_id || first || activePath.value[0] || "";
    }
  }

  function refreshStatuses() {
    agentStatuses.value = [
      { key: "doc", kind: "doc", label: "文档智能体", phase: currentCards.value.length ? "资源就绪" : "待命", progress: currentCards.value.length ? 100 : 0, active: true },
      { key: "quiz", kind: "quiz", label: "评估智能体", phase: currentCards.value.some(c => c.card_type === "diagnostic_quiz") ? "测验可用" : "等待中", progress: 50, active: true },
      { key: "path", kind: "path", label: "路径规划", phase: activePath.value.length ? `${activePath.value.length} 个节点` : "生成中", progress: activePath.value.length ? 100 : 10, active: true },
    ];
  }

  // --- 知识图谱加载 ---
  async function loadKnowledgeGraph() {
    try {
      const kg = await fetchKnowledgeGraph(courseId.value);
      knowledgeGraph.value = kg;
      const titles = {};
      (kg.nodes || []).forEach(n => { titles[n.id] = n.title; });
      nodeTitles.value = titles;
    } catch { setInfo("知识图谱加载失败，使用本地缓存"); }
  }

  // --- 认证 ---
  async function tryAutoLogin() {
    const token = window.localStorage.getItem("access_token");
    if (!token) return false;
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
      user_id: userIdInput, password,
      captcha_token: captchaToken, captcha_answer: captchaAnswer,
    });
    currentUser.value = result.user;
    isLoggedIn.value = true;
    return result;
  }

  async function handleRegister(userIdInput, email, password, captchaToken, captchaAnswer) {
    const result = await register({
      user_id: userIdInput, email, password,
      captcha_token: captchaToken, captcha_answer: captchaAnswer,
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
    messages.value = [];
  }

  // --- 冷启动 ---
  async function submitProbe(values) {
    isSubmittingProbe.value = true;
    try {
      const answer = Array.isArray(values) && values.length === 1 ? values[0] : values;
      const resp = await submitProbeAnswer(userId.value, answer, courseId.value);
      if (resp.phase === "complete") {
        probe.value = null;
        probeCollected.value = probeTotal.value;
        await initPathAndEnter();
        return;
      }
      probeCollected.value = resp.collected ?? probeCollected.value;
      const next = await fetchProbe(userId.value, courseId.value);
      probe.value = next.probe;
      probeCollected.value = next.collected ?? probeCollected.value;
    } catch { setInfo("提交失败，请重试"); }
    finally { isSubmittingProbe.value = false; }
  }

  async function initPathAndEnter() {
    await initLearningPath(userId.value, courseId.value);
    const state = await fetchState(userId.value, courseId.value);
    hydrateState(state);
    currentNode.value = activePath.value.find(id => (mastery.value[id] ?? 0) < 0.65) || activePath.value[0] || "";
    bootMode.value = "ready";
    refreshStatuses();
    if (currentNode.value) await loadNode(currentNode.value, true);
  }

  // --- 课程辅助 ---
  const courseId = computed(() => activeCourse.value?.course_id || "data_structures");

  async function loadAvailableCourses(search) {
    try {
      availableCourses.value = await fetchCourses(search);
    } catch { /* ignore */ }
  }

  async function loadUserCourses() {
    try {
      const result = await fetchUserCourses(userId.value);
      enrolledCourses.value = result.courses || [];
      if (result.active_course) {
        activeCourse.value = result.courses.find(c => c.course_id === result.active_course) || null;
      }
      return result;
    } catch { return { courses: [], active_course: "" }; }
  }

  // --- 主启动流程 ---
  async function bootstrap() {
    bootMode.value = "loading";
    isBusy.value = true;
    try {
      await loadKnowledgeGraph();
      await loadAvailableCourses();
      const loggedIn = await tryAutoLogin();
      if (!loggedIn) { bootMode.value = "login"; isBusy.value = false; return; }

      // 检查用户是否有已注册课程
      const enrollment = await loadUserCourses();
      if (!enrollment.active_course || !enrollment.courses.length) {
        // 没有课程 → 显示选课页面
        bootMode.value = "course_selection";
        isBusy.value = false;
        return;
      }

      // 有活跃课程 → 加载该课程的学习状态
      const state = await fetchState(userId.value, courseId.value);
      hydrateState(state);
      if (activePath.value.length) {
        bootMode.value = "ready";
        refreshStatuses();
        if (currentNode.value) await loadNode(currentNode.value, true);
      } else {
        const ps = await fetchProbe(userId.value, courseId.value);
        if (ps.phase === "complete") {
          await initPathAndEnter();
        } else {
          probe.value = ps.probe;
          probeCollected.value = ps.collected ?? 0;
          bootMode.value = "probe";
        }
      }
    } catch {
      setInfo("初始化失败，请检查后端服务");
      bootMode.value = "login";
    } finally { isBusy.value = false; }
  }

  // --- 选课与切换 ---
  async function handleEnrollCourse(courseIdInput) {
    isBusy.value = true;
    try {
      const result = await enrollCourse(userId.value, courseIdInput);
      activeCourse.value = result.course;
      // 加入已选列表
      await loadUserCourses();
      // 开始冷启动测评
      const ps = await fetchProbe(userId.value, courseId.value);
      if (ps.phase === "complete") {
        await initPathAndEnter();
      } else {
        probe.value = ps.probe;
        probeCollected.value = ps.collected ?? 0;
        bootMode.value = "probe";
      }
    } catch (e) {
      setInfo("选课失败：" + (e?.response?.data?.detail || "请重试"));
    } finally { isBusy.value = false; }
  }

  async function handleSwitchCourse(courseIdInput) {
    if (courseIdInput === activeCourse.value?.course_id) return;
    isBusy.value = true;
    try {
      await switchCourse(userId.value, courseIdInput);
      await loadUserCourses();
      // 重置工作台状态
      currentNode.value = "";
      activePath.value = [];
      mastery.value = {};
      resources.value = {};
      messages.value = [];
      probe.value = null;
      // 加载新课程状态
      const state = await fetchState(userId.value, courseId.value);
      hydrateState(state);
      if (activePath.value.length) {
        bootMode.value = "ready";
        refreshStatuses();
        if (currentNode.value) await loadNode(currentNode.value, true);
      } else {
        const ps = await fetchProbe(userId.value, courseId.value);
        if (ps.phase === "complete") {
          await initPathAndEnter();
        } else {
          probe.value = ps.probe;
          probeCollected.value = ps.collected ?? 0;
          bootMode.value = "probe";
        }
      }
    } catch (e) {
      setInfo("切换课程失败：" + (e?.response?.data?.detail || "请重试"));
    } finally { isBusy.value = false; }
  }

  // --- 节点资源加载 ---
  async function loadNode(nodeId, silent = false) {
    if (!nodeId) return;
    currentNode.value = nodeId;
    if (resources.value[nodeId]?.length) { refreshStatuses(); return; }
    isLoadingNode.value = true;
    if (!silent) setInfo(`正在为「${nodeTitles.value[nodeId] || nodeId}」生成学习资源...`);
    try {
      await runPipelineStep({
        user_id: userId.value, course_id: courseId.value, current_node_id: nodeId,
        correctness: 0.7, time_spent_ratio: 1.0, code_pass_rate: 0.7,
      });
      const state = await fetchState(userId.value, courseId.value);
      hydrateState(state);
      currentNode.value = nodeId;
    } catch { setInfo("资源生成失败"); }
    finally { isLoadingNode.value = false; refreshStatuses(); }
  }

  // --- 测验提交 ---
  async function submitQuiz(score) {
    isLoadingNode.value = true;
    try {
      await runPipelineStep({
        user_id: userId.value, course_id: courseId.value, correctness: score,
        time_spent_ratio: 1.0, code_pass_rate: score,
      });
      const state = await fetchState(userId.value, courseId.value);
      hydrateState(state);
      currentNode.value = activePath.value.includes(currentNode.value) ? currentNode.value : (activePath.value[0] || "");
    } catch { setInfo("提交失败"); }
    finally { isLoadingNode.value = false; refreshStatuses(); }
  }

  // --- 辅导对话 ---
  async function sendTutorMessage(query) {
    if (!query.trim()) return;
    const userMsg = { id: `u-${Date.now()}`, role: "user", content: query.trim() };
    const assistantMsg = { id: `a-${Date.now()}`, role: "assistant", content: "", mermaid: "", streaming: true };
    messages.value = [...messages.value, userMsg, assistantMsg];
    try {
      const data = await askTutor({ user_id: userId.value, query: query.trim() });
      const r = data.tutor_response ?? {};
      assistantMsg.content = r.text_explanation || "当前暂无可用回答，请稍后再试。";
      assistantMsg.mermaid = r.mermaid_src || "";
    } catch { assistantMsg.content = "辅导服务暂时不可用。"; }
    finally { assistantMsg.streaming = false; }
  }

  // --- 工具导出 ---
  function getCardLabel(type) { return CARD_CN[type] || type; }
  function getAgentLabel(type) { return AGENT_CN[type] || "文档智能体"; }
  function parseQuiz(content = "") {
    const lines = content.split(/[\n。；;]/).map(s => s.trim()).filter(s => s.length > 12);
    return [
      { id: "q1", prompt: "根据当前资源，选择最贴合核心概念的一项。", options: [lines[0] || "继续阅读后作答", "与时间复杂度无关", "仅适用于图算法", "以上都不对"], answer: 0 },
      { id: "q2", prompt: "以下哪项描述与资源内容一致？", options: [lines[1] || lines[0] || "继续阅读", "二分查找总是最优", "所有算法都是 O(1)", "以上都不对"], answer: 0 },
    ];
  }

  return {
    isLoggedIn, currentUser, userId,
    bootMode, isBusy, isSubmittingProbe, isLoadingNode,
    currentNode, activePath, mastery, capabilityRadar, diagnosticReport,
    knowledgeGraph, nodeTitles, probe, probeCollected, probeTotal,
    resources, currentCards, currentNodeTitle, currentPathNodes,
    messages, infoMessage, agentStatuses, overallProgress, masteredCount,
    activeCourse, availableCourses, enrolledCourses, courseId,
    handleLogin, handleRegister, handleLogout, getCaptcha,
    bootstrap, submitProbe, loadNode, submitQuiz, sendTutorMessage,
    getCardLabel, getAgentLabel, parseQuiz, refreshStatuses,
    loadAvailableCourses, handleEnrollCourse, handleSwitchCourse,
  };
}
