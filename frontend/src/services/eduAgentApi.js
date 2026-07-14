import apiClient, { createRequestId, tokenStore } from "./apiClient";
import { normalizeLearningEvent } from "../contracts/learning";
import { normalizeTutorRequest } from "../contracts/tutor";
import { createRefreshRecoveryReporter } from "./clientTelemetry";

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

function sessionPath(sessionId) {
  return String(sessionId || "")
    .split(":")
    .map((part) => encodeURIComponent(part))
    .join(":");
}

export async function createSession({ course_id = "data_structures" } = {}) {
  const { data } = await apiClient.post("/sessions", { course_id });
  return data;
}

export async function getSession(sessionId) {
  try {
    const { data } = await apiClient.get(`/sessions/${sessionPath(sessionId)}`);
    refreshRecoveryReporter.success();
    return data;
  } catch (error) {
    refreshRecoveryReporter.failure();
    throw error;
  }
}

export async function submitSessionProfileInput(sessionId, answer) {
  const { data } = await apiClient.post(`/sessions/${sessionPath(sessionId)}/profile-input`, { answer });
  return data;
}

export async function fetchSessionProfileProbe(sessionId) {
  const { data } = await apiClient.get(`/sessions/${sessionPath(sessionId)}/profile-probe`);
  return data;
}

export async function initSessionPath(sessionId) {
  const { data } = await apiClient.post(`/sessions/${sessionPath(sessionId)}/path/init`, {});
  return data;
}

export async function advanceSession(sessionId, payload = {}) {
  const { data } = await apiClient.post(`/sessions/${sessionPath(sessionId)}/advance`, payload);
  return data;
}

export async function submitSessionBehavior(sessionId, payload = {}) {
  const { data } = await apiClient.post(`/sessions/${sessionPath(sessionId)}/behavior`, payload);
  return data;
}

export async function submitSessionLearningEvent(sessionId, payload = {}) {
  const { data } = await apiClient.post(
    `/sessions/${sessionPath(sessionId)}/events`,
    normalizeLearningEvent(payload),
  );
  return data;
}

export async function fetchSessionLearningEventHistory(
  sessionId,
  { nodeId = "", eventId = "", limit = 100 } = {},
) {
  const params = { limit };
  if (nodeId) params.node_id = nodeId;
  if (eventId) params.event_id = eventId;
  const { data } = await apiClient.get(`/sessions/${sessionPath(sessionId)}/events`, { params });
  return data;
}

export async function fetchSessionLearningAssets(sessionId) {
  const { data } = await apiClient.get(`/sessions/${sessionPath(sessionId)}/assets`);
  return data;
}

export async function patchSessionLearningAssets(sessionId, payload = {}) {
  const { data } = await apiClient.patch(`/sessions/${sessionPath(sessionId)}/assets`, payload);
  return data;
}

export async function fetchSessionReviewDashboard(sessionId) {
  const { data } = await apiClient.get(`/sessions/${sessionPath(sessionId)}/review`);
  return data;
}

export async function startSessionReviewItem(sessionId, reviewItemId) {
  const { data } = await apiClient.post(
    `/sessions/${sessionPath(sessionId)}/review/items/${encodeURIComponent(reviewItemId)}/start`,
    {},
  );
  return data;
}

export async function prepareSessionReviewRetest(sessionId, reviewItemId, practiceEventId) {
  const { data } = await apiClient.post(
    `/sessions/${sessionPath(sessionId)}/review/items/${encodeURIComponent(reviewItemId)}/prepare-retest`,
    { practice_event_id: String(practiceEventId || "") },
  );
  return data;
}

export async function askSessionTutor(sessionId, payload = {}) {
  const { data } = await apiClient.post(
    `/sessions/${sessionPath(sessionId)}/tutor`,
    normalizeTutorRequest(payload),
  );
  return data;
}

export async function streamSessionTutor(sessionId, payload, handlers = {}) {
  return streamSsePost(
    `/api/sessions/${sessionPath(sessionId)}/tutor`,
    normalizeTutorRequest({ ...payload, stream: true }),
    handlers,
  );
}

export async function replanSession(sessionId, payload = {}) {
  const { data } = await apiClient.post(`/sessions/${sessionPath(sessionId)}/replan`, payload);
  return data;
}

export async function fetchSessionResources(sessionId, nodeId, { force = false, cardType = "" } = {}) {
  const params = { force };
  if (cardType) params.card_type = cardType;
  const { data } = await apiClient.get(`/sessions/${sessionPath(sessionId)}/resources/${encodeURIComponent(nodeId)}`, {
    params,
    timeout: RESOURCE_GENERATION_TIMEOUT_MS,
  });
  return data;
}

export async function fetchSessionPracticeProblem(sessionId, problemOrResourceId) {
  const { data } = await apiClient.get(
    `/sessions/${sessionPath(sessionId)}/practice/problems/${encodeURIComponent(problemOrResourceId)}`,
  );
  return data;
}

export async function runSessionPractice(sessionId, payload = {}) {
  const { data } = await apiClient.post(
    `/sessions/${sessionPath(sessionId)}/practice/run`,
    payload,
  );
  return data;
}

export async function submitSessionPractice(sessionId, payload = {}) {
  const { data } = await apiClient.post(
    `/sessions/${sessionPath(sessionId)}/practice/submit`,
    payload,
  );
  return data;
}
export async function resetSession(userId, courseId = "data_structures") {
  const { data } = await apiClient.post("/reset", { user_id: userId, course_id: courseId });
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
  let receivedTerminalEvent = false;

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
      receivedTerminalEvent = true;
      onDone?.(parsed);
    } else if (eventName === "error") {
      receivedTerminalEvent = true;
      onError?.(new Error(parsed.error || "流式辅导出错"));
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
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
    if (!receivedTerminalEvent) {
      onError?.(new Error("辅导连接意外结束，输入已保留，请重试。"));
    }
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
