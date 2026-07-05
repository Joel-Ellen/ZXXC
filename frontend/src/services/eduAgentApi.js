import apiClient, { tokenStore } from "./apiClient";

// ── 认证 ──
export async function getCaptcha() {
  const { data } = await apiClient.get("/auth/captcha-json");
  return data;
}

export async function register(payload) {
  const { data } = await apiClient.post("/auth/register", payload);
  if (data.access_token) tokenStore.setTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
  return data;
}

export async function login(payload) {
  const { data } = await apiClient.post("/auth/login", payload);
  if (data.access_token) tokenStore.setTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
  return data;
}

export async function refreshToken() {
  const rt = tokenStore.getRefreshToken();
  if (!rt) return null;
  const { data } = await apiClient.post("/auth/refresh", { refresh_token: rt });
  if (data.access_token) tokenStore.setTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
  return data;
}

export async function fetchMyProfile() {
  const { data } = await apiClient.get("/auth/me");
  return data;
}

// ── 学习流水线 ──

// Session-style API (new stable boundary)
export function buildSessionId(userId, courseId = "data_structures") {
  return `${userId || "demo_user"}:${courseId || "data_structures"}`;
}

export async function createSession({ user_id, course_id = "data_structures" } = {}) {
  const { data } = await apiClient.post("/sessions", { user_id, course_id });
  return data;
}

export async function getSession(sessionId) {
  const { data } = await apiClient.get(`/sessions/${encodeURIComponent(sessionId)}`);
  return data;
}

export async function submitSessionProfileInput(sessionId, answer) {
  const { data } = await apiClient.post(`/sessions/${encodeURIComponent(sessionId)}/profile-input`, { answer });
  return data;
}

export async function advanceSession(sessionId, payload = {}) {
  const { data } = await apiClient.post(`/sessions/${encodeURIComponent(sessionId)}/advance`, payload);
  return data;
}

export async function submitSessionBehavior(sessionId, payload = {}) {
  const { data } = await apiClient.post(`/sessions/${encodeURIComponent(sessionId)}/behavior`, payload);
  return data;
}

export async function askSessionTutor(sessionId, payload = {}) {
  const { data } = await apiClient.post(`/sessions/${encodeURIComponent(sessionId)}/tutor`, payload);
  return data;
}

export async function replanSession(sessionId, payload = {}) {
  const { data } = await apiClient.post(`/sessions/${encodeURIComponent(sessionId)}/replan`, payload);
  return data;
}

export async function fetchSessionResources(sessionId, nodeId, { force = false } = {}) {
  const { data } = await apiClient.get(`/sessions/${encodeURIComponent(sessionId)}/resources/${encodeURIComponent(nodeId)}`, {
    params: { force },
  });
  return data;
}
export async function resetSession(userId) {
  const { data } = await apiClient.post("/reset", { user_id: userId });
  return data;
}

export async function fetchState(userId, courseId = "data_structures") {
  const { data } = await apiClient.get("/state", { params: { user_id: userId, course_id: courseId } });
  return data;
}

export async function fetchProbe(userId, courseId = "data_structures") {
  const { data } = await apiClient.get("/cold-start/probe", { params: { user_id: userId, course_id: courseId } });
  return data;
}

export async function submitProbeAnswer(userId, answer, courseId = "data_structures") {
  const { data } = await apiClient.post("/cold-start/answer", { user_id: userId, answer, course_id: courseId });
  return data;
}

export async function initLearningPath(userId, courseId = "data_structures") {
  const { data } = await apiClient.post("/init-path", { user_id: userId, course_id: courseId });
  return data;
}

export async function runPipelineStep(payload) {
  const { data } = await apiClient.post("/pipeline/step", payload);
  return data;
}

export async function askTutor(payload) {
  const { data } = await apiClient.post("/tutor/ask", payload);
  return data;
}

/**
 * 显式生成或重新生成某节点的学习资源。
 * 仅在用户主动点击"生成"/"重新生成"时调用，不在页面加载时自动触发。
 *
 * @param {{ user_id: string, course_id: string, node_id: string, force?: boolean }} payload
 * @returns {Promise<{ status: string, node_id: string, cards: Array }>}
 */
export async function generateNodeResources(payload) {
  const { data } = await apiClient.post("/resources/generate-node", payload);
  return data;
}

/**
 * 流式辅导问答 — SSE over fetch（后端为 POST，EventSource 不支持 POST，故用 ReadableStream 手动解析）。
 *
 * @param {Object} payload           - { user_id, course_id, question }
 * @param {Object} handlers          - 回调集合
 * @param {(token: string) => void}  handlers.onToken - 每个 token 到达时触发
 * @param {(meta: Object) => void}   [handlers.onDone] - 流结束（done 事件）时触发
 * @param {(err: Error) => void}     [handlers.onError] - 出错时触发
 * @param {AbortSignal}              [handlers.signal] - 可选，用于中断
 * @returns {Promise<void>}
 */
export async function streamTutorAsk(payload, { onToken, onDone, onError, signal } = {}) {
  const token = tokenStore.getAccessToken();
  let response;
  try {
    response = await fetch("/api/tutor/ask-stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
      credentials: "include",
      signal,
    });
  } catch (err) {
    onError?.(err);
    return;
  }

  if (!response.ok || !response.body) {
    onError?.(new Error(`SSE 请求失败：HTTP ${response.status}`));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const dispatch = (rawEvent) => {
    // 单个 SSE 事件块可能包含多行 event:/data:
    let eventName = "message";
    const dataLines = [];
    for (const line of rawEvent.split("\n")) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (!dataLines.length) return;
    const dataStr = dataLines.join("\n");
    let parsed;
    try {
      parsed = JSON.parse(dataStr);
    } catch {
      return;
    }
    if (eventName === "token") {
      if (parsed.token) onToken?.(parsed.token);
    } else if (eventName === "done") {
      onDone?.(parsed);
    } else if (eventName === "error") {
      onError?.(new Error(parsed.error || "流式辅导出错"));
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE 事件以空行（\n\n）分隔
      let sepIndex;
      while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        if (rawEvent.trim()) dispatch(rawEvent);
      }
    }
    // 冲刷残余
    if (buffer.trim()) dispatch(buffer);
  } catch (err) {
    if (err?.name !== "AbortError") onError?.(err);
  }
}

export async function fetchKnowledgeGraph(courseId = "data_structures") {
  const { data } = await apiClient.get("/knowledge-graph", { params: { course_id: courseId } });
  return data;
}

// ── 课程 ──
export async function fetchCourses(search) {
  const { data } = await apiClient.get("/courses", { params: search ? { search } : {} });
  return data;
}

export async function fetchCourseDetail(courseId) {
  const { data } = await apiClient.get(`/courses/${courseId}`);
  return data;
}

export async function fetchUserCourses(userId) {
  const { data } = await apiClient.get("/user/courses", { params: { user_id: userId } });
  return data;
}

export async function enrollCourse(userId, courseId) {
  const { data } = await apiClient.post("/user/courses/enroll", { user_id: userId, course_id: courseId });
  return data;
}

export async function switchCourse(userId, courseId) {
  const { data } = await apiClient.post("/user/courses/switch", { user_id: userId, course_id: courseId });
  return data;
}
