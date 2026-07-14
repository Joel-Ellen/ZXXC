import apiClient, { createRequestId, tokenStore } from "./apiClient";
import { normalizeLearningEvent } from "../contracts/learning";
import { normalizeTutorRequest } from "../contracts/tutor";
import { createRefreshRecoveryReporter } from "./clientTelemetry";

// Generating a complete node can require several model calls. Keep the normal
// API timeout short, but give this explicit learner-requested operation enough
// time to return its real server result rather than reporting a false failure.
const RESOURCE_GENERATION_TIMEOUT_MS = 120_000;
const refreshRecoveryReporter = createRefreshRecoveryReporter();

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
  const normalizedUserId = String(userId || "").trim();
  const normalizedCourseId = String(courseId || "data_structures").trim();
  return normalizedUserId && normalizedUserId !== "demo_user" && normalizedCourseId
    ? `${normalizedUserId}:${normalizedCourseId}`
    : "";
}

export async function createSession({ course_id = "data_structures" } = {}) {
  const { data } = await apiClient.post("/sessions", { course_id });
  return data;
}

export async function getSession(sessionId) {
  try {
    const { data } = await apiClient.get(`/sessions/${encodeURIComponent(sessionId)}`);
    refreshRecoveryReporter.success();
    return data;
  } catch (error) {
    refreshRecoveryReporter.failure();
    throw error;
  }
}

export async function submitSessionProfileInput(sessionId, answer) {
  const { data } = await apiClient.post(`/sessions/${encodeURIComponent(sessionId)}/profile-input`, { answer });
  return data;
}

export async function fetchSessionProfileProbe(sessionId) {
  const { data } = await apiClient.get(`/sessions/${encodeURIComponent(sessionId)}/profile-probe`);
  return data;
}

export async function initSessionPath(sessionId) {
  const { data } = await apiClient.post(`/sessions/${encodeURIComponent(sessionId)}/path/init`, {});
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

/**
 * Record one real learner interaction. The server, not this client, derives
 * correctness and decides whether evidence may affect mastery.
 */
export async function submitSessionLearningEvent(sessionId, payload = {}) {
  const { data } = await apiClient.post(
    `/sessions/${encodeURIComponent(sessionId)}/events`,
    normalizeLearningEvent(payload),
  );
  return data;
}

export async function fetchSessionLearningEventHistory(sessionId, { nodeId = "", eventId = "", limit = 100 } = {}) {
  const params = { limit };
  if (nodeId) {
    params.node_id = nodeId;
  }
  if (eventId) {
    params.event_id = eventId;
  }

  const { data } = await apiClient.get(`/sessions/${encodeURIComponent(sessionId)}/events`, { params });
  return data;
}

/** Durable, per-session learner assets that must survive devices and routes. */
export async function fetchSessionLearningAssets(sessionId) {
  const { data } = await apiClient.get(`/sessions/${encodeURIComponent(sessionId)}/assets`);
  return data;
}

/** Apply one revision-aware asset patch without replacing unrelated assets. */
export async function patchSessionLearningAssets(sessionId, payload = {}) {
  const { data } = await apiClient.patch(`/sessions/${encodeURIComponent(sessionId)}/assets`, payload);
  return data;
}

/** Fetch the server-derived mistake book, due queue, weak nodes and trend. */
export async function fetchSessionReviewDashboard(sessionId) {
  const { data } = await apiClient.get(`/sessions/${encodeURIComponent(sessionId)}/review`);
  return data;
}

/** Begin the material-review phase for one queued review item. */
export async function startSessionReviewItem(sessionId, reviewItemId) {
  const { data } = await apiClient.post(
    `/sessions/${encodeURIComponent(sessionId)}/review/items/${encodeURIComponent(reviewItemId)}/start`,
    {},
  );
  return data;
}

/** Consume one verified practice event and obtain a fresh server-owned retest. */
export async function prepareSessionReviewRetest(sessionId, reviewItemId, practiceEventId) {
  const { data } = await apiClient.post(
    `/sessions/${encodeURIComponent(sessionId)}/review/items/${encodeURIComponent(reviewItemId)}/prepare-retest`,
    { practice_event_id: String(practiceEventId || "") },
  );
  return data;
}

export async function askSessionTutor(sessionId, payload = {}) {
  const { data } = await apiClient.post(
    `/sessions/${encodeURIComponent(sessionId)}/tutor`,
    normalizeTutorRequest(payload),
  );
  return data;
}

export async function streamSessionTutor(sessionId, payload, handlers = {}) {
  return streamSsePost(
    `/api/sessions/${encodeURIComponent(sessionId)}/tutor`,
    normalizeTutorRequest({ ...payload, stream: true }),
    handlers,
  );
}

export async function replanSession(sessionId, payload = {}) {
  const { data } = await apiClient.post(`/sessions/${encodeURIComponent(sessionId)}/replan`, payload);
  return data;
}

export async function fetchSessionResources(sessionId, nodeId, { force = false, cardType = "" } = {}) {
  const params = { force };
  if (cardType) {
    params.card_type = cardType;
  }

  const { data } = await apiClient.get(`/sessions/${encodeURIComponent(sessionId)}/resources/${encodeURIComponent(nodeId)}`, {
    params,
    timeout: RESOURCE_GENERATION_TIMEOUT_MS,
  });
  return data;
}

/**
 * Fetch the learner-safe problem specification. The API accepts either a
 * catalog problem id or a resource id so generated learning cards can opt in
 * without exposing private test data in the resource payload.
 */
export async function fetchSessionPracticeProblem(sessionId, problemOrResourceId) {
  const { data } = await apiClient.get(
    `/sessions/${encodeURIComponent(sessionId)}/practice/problems/${encodeURIComponent(problemOrResourceId)}`,
  );
  return data;
}

/**
 * Execute a draft against public tests only. Test definitions always remain
 * server-owned; callers may send source code and its declared language only.
 */
export async function runSessionPractice(sessionId, payload = {}) {
  const { data } = await apiClient.post(
    `/sessions/${encodeURIComponent(sessionId)}/practice/run`,
    payload,
  );
  return data;
}

/**
 * Submit a draft for the complete server-owned test suite.
 */
export async function submitSessionPractice(sessionId, payload = {}) {
  const { data } = await apiClient.post(
    `/sessions/${encodeURIComponent(sessionId)}/practice/submit`,
    payload,
  );
  return data;
}

/**
 * 流式辅导问答 — SSE over fetch（后端为 POST，EventSource 不支持 POST，故用 ReadableStream 手动解析）。
 *
 * @param {Object} payload           - { question, context_type, code_snippet, error_message }
 * @param {Object} handlers          - 回调集合
 * @param {(token: string) => void}  handlers.onToken - 每个 token 到达时触发
 * @param {(meta: Object) => void}   [handlers.onDone] - 流结束（done 事件）时触发
 * @param {(err: Error) => void}     [handlers.onError] - 出错时触发
 * @param {AbortSignal}              [handlers.signal] - 可选，用于中断
 * @returns {Promise<void>}
 */
// Shared transport for session tutor streaming.
async function streamSsePost(url, payload, { onToken, onDone, onReset, onError, signal } = {}) {
  const token = tokenStore.getAccessToken();
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "X-Request-ID": createRequestId(),
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
  let receivedDone = false;

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
    } else if (eventName === "reset") {
      onReset?.(parsed);
    } else if (eventName === "done") {
      receivedDone = true;
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
      // EventSourceResponse uses CRLF framing; normalize it before looking
      // for SSE's blank-line event boundary.
      buffer = buffer.replace(/\r\n/g, "\n");
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
    if (!receivedDone) onDone?.({});
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

export async function fetchUserCourses() {
  const { data } = await apiClient.get("/user/courses");
  return data;
}

export async function enrollCourse(courseId) {
  const { data } = await apiClient.post("/user/courses/enroll", { course_id: courseId });
  return data;
}

export async function switchCourse(courseId) {
  const { data } = await apiClient.post("/user/courses/switch", { course_id: courseId });
  return data;
}
