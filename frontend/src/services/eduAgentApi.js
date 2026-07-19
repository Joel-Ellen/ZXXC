import apiClient, {
  createRequestId,
  forceLogout,
  refreshStoredTokens,
  tokenStore,
} from "./apiClient";
import { normalizeLearningEvent } from "../contracts/learning";
import { normalizeTutorRequest } from "../contracts/tutor";
import { createRefreshRecoveryReporter } from "./clientTelemetry";

const RESOURCE_READ_TIMEOUT_MS = 15_000;
const RESOURCE_GENERATION_REQUEST_TIMEOUT_MS = 15_000;
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

export async function deleteSessionReviewItem(sessionId, reviewItemId) {
  const { data } = await apiClient.delete(
    `/sessions/${sessionPath(sessionId)}/review/items/${encodeURIComponent(reviewItemId)}`,
  );
  return data;
}

export async function startSessionDirectReviewRetest(sessionId, reviewItemId) {
  const { data } = await apiClient.post(
    `/sessions/${sessionPath(sessionId)}/review/items/${encodeURIComponent(reviewItemId)}/direct-retest`,
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
  // Keep the request id and replay cursor on the caller-owned handler bag so
  // reconnects can resume the same server-side stream.
  if (!handlers.requestId) handlers.requestId = createRequestId();
  const callerOnEvent = handlers.onEvent;
  return streamSsePost(
    `/api/sessions/${sessionPath(sessionId)}/tutor`,
    normalizeTutorRequest({ ...payload, stream: true }),
    {
      ...handlers,
      onEvent(event) {
        if (event?.id) handlers.lastEventId = event.id;
        callerOnEvent?.(event);
      },
    },
  );
}

const TUTOR_STREAM_MAX_RECONNECTS = 2;
const TUTOR_STREAM_RECONNECT_DELAY_MS = 500;

function abortableDelay(delayMs, signal) {
  if (delayMs <= 0 || signal?.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timeoutId = setTimeout(finish, delayMs);
    function finish() {
      clearTimeout(timeoutId);
      signal?.removeEventListener("abort", finish);
      resolve();
    }
    signal?.addEventListener("abort", finish, { once: true });
  });
}

/**
 * Reconnect a POST-based Tutor SSE stream while preserving its stream ID and
 * replay cursor. Recoverable transport errors are only surfaced after the
 * bounded retry budget is exhausted.
 */
export async function streamSessionTutorWithReconnect(
  sessionId,
  payload,
  handlers = {},
  {
    maxReconnects = TUTOR_STREAM_MAX_RECONNECTS,
    reconnectDelayMs = TUTOR_STREAM_RECONNECT_DELAY_MS,
  } = {},
) {
  const callerOnEvent = handlers.onEvent;
  const callerOnDone = handlers.onDone;
  const callerOnError = handlers.onError;
  const signal = handlers.signal;
  let terminal = false;
  let latestError = null;
  let latestErrorEvent;
  let reconnectAttempts = 0;

  handlers.requestId ||= createRequestId();
  handlers.lastEventId = String(handlers.lastEventId || "");
  const managedHandlers = {
    ...handlers,
    onEvent(event) {
      if (event?.id) {
        managedHandlers.lastEventId = event.id;
        handlers.lastEventId = event.id;
      }
      callerOnEvent?.(event);
    },
    onDone(data) {
      terminal = true;
      callerOnDone?.(data);
    },
    onError(error, event) {
      latestError = error instanceof Error ? error : new Error("辅导连接失败，请重试。");
      latestErrorEvent = event;
      if (!latestError.retryable || latestError.sseTerminal) {
        terminal = true;
        callerOnError?.(latestError, event);
      }
    },
  };

  while (!terminal && !signal?.aborted) {
    latestError = null;
    latestErrorEvent = undefined;
    managedHandlers.requestId = handlers.requestId;
    managedHandlers.lastEventId = handlers.lastEventId;

    try {
      await streamSessionTutor(sessionId, payload, managedHandlers);
    } catch (error) {
      latestError = error instanceof Error ? error : new Error("辅导连接失败，请重试。");
    }
    handlers.lastEventId = managedHandlers.lastEventId;

    if (terminal || signal?.aborted) return;
    const error = latestError || Object.assign(
      new Error("辅导连接意外结束，输入已保留，请重试。"),
      { retryable: true },
    );
    if (!error.retryable || reconnectAttempts >= Math.max(0, Number(maxReconnects) || 0)) {
      callerOnError?.(error, latestErrorEvent);
      return;
    }

    reconnectAttempts += 1;
    const retryAfterMs = Number.isFinite(Number(error.retryAfterMs))
      ? Math.max(0, Number(error.retryAfterMs))
      : 0;
    const delayMs = Math.max(
      Math.max(0, Number(reconnectDelayMs) || 0) * reconnectAttempts,
      retryAfterMs,
    );
    handlers.onReconnect?.({ attempt: reconnectAttempts, delayMs, error });
    await abortableDelay(delayMs, signal);
  }
}

export async function replanSession(sessionId, payload = {}) {
  const { data } = await apiClient.post(`/sessions/${sessionPath(sessionId)}/replan`, payload);
  return data;
}

export async function fetchSessionResources(sessionId, nodeId) {
  const { data } = await apiClient.get(`/sessions/${sessionPath(sessionId)}/resources/${encodeURIComponent(nodeId)}`, {
    timeout: RESOURCE_READ_TIMEOUT_MS,
  });
  return data;
}

export async function requestResourceGeneration(
  sessionId,
  nodeId,
  { cardTypes = [], force = false, priority = "" } = {},
) {
  const normalizedCardTypes = [...new Set(
    (Array.isArray(cardTypes) ? cardTypes : [cardTypes])
      .map((cardType) => String(cardType || "").trim())
      .filter(Boolean),
  )];
  const payload = {
    card_types: normalizedCardTypes,
    force: Boolean(force),
  };
  if (priority) payload.priority = priority;

  const { data } = await apiClient.post(
    `/sessions/${sessionPath(sessionId)}/resources/${encodeURIComponent(nodeId)}/generation`,
    payload,
    { timeout: RESOURCE_GENERATION_REQUEST_TIMEOUT_MS },
  );
  return data;
}

export async function streamResourceGeneration(jobId, handlers = {}) {
  return streamSseGet(
    `/api/resource-generation-jobs/${encodeURIComponent(jobId)}/events`,
    handlers,
  );
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
async function streamSsePost(url, payload, {
  onEvent,
  onToken,
  onDone,
  onReset,
  onWarning,
  onValidationError,
  onError,
  signal,
  lastEventId = "",
  requestId = "",
} = {}) {
  const streamRequestId = requestId || createRequestId();
  let cursor = String(lastEventId || "");
  const request = (token) => fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "X-Request-ID": createRequestId(),
        "X-EduAgent-Stream-ID": streamRequestId,
        ...(cursor ? { "Last-Event-ID": cursor } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
      credentials: "include",
      signal,
    });

  let response;
  try {
    response = await request(tokenStore.getAccessToken());
    if (response.status === 401 && !signal?.aborted) {
      const accessToken = await refreshStoredTokens().catch(() => null);
      if (!accessToken) {
        forceLogout();
        const authError = new Error("登录状态已失效，请重新登录。");
        authError.status = 401;
        authError.retryable = false;
        throw authError;
      }
      response = await request(accessToken);
    }
  } catch (err) {
    if (err?.name === "AbortError" || signal?.aborted) return;
    const error = err instanceof Error ? err : new Error("辅导连接失败，请重试。");
    if (/401|登录状态|refresh/i.test(error.message)) error.status = 401;
    error.retryable = !error.status;
    onError?.(error);
    return;
  }

  if (!response.ok || !response.body) {
    if (response.status === 401) forceLogout();
    const error = new Error(response.status === 401
      ? "登录状态已失效，请重新登录。"
      : `SSE 请求失败：HTTP ${response.status}`);
    error.status = response.status;
    error.retryable = response.status >= 500 || response.status === 408 || response.status === 429;
    onError?.(error);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let receivedTerminalEvent = false;

  const dispatch = (rawEvent) => {
    // 单个 SSE 事件块可能包含多行 event:/data:
    let eventName = "message";
    let eventId = "";
    const dataLines = [];
    for (const line of rawEvent.split("\n")) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("id:")) {
        eventId = line.slice(3).trim();
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
    const event = { event: eventName, data: parsed, id: eventId };
    if (eventId) cursor = eventId;
    onEvent?.(event);
    if (eventName === "token") {
      if (parsed.token) onToken?.(parsed.token);
    } else if (eventName === "reset") {
      onReset?.(parsed);
    } else if (eventName === "warning") {
      onWarning?.(parsed);
    } else if (eventName === "validation_error") {
      onValidationError?.(parsed);
    } else if (eventName === "done") {
      receivedTerminalEvent = true;
      onDone?.(parsed);
    } else if (eventName === "error") {
      receivedTerminalEvent = true;
      const errorCode = parsed.error || parsed.detail || "";
      const capacityExceeded = errorCode === "TUTOR_STREAM_CAPACITY_EXCEEDED";
      const error = new Error(capacityExceeded ? "辅导请求较多，请稍后重试。" : errorCode || "流式辅导出错");
      error.code = errorCode;
      error.sseTerminal = !capacityExceeded;
      error.retryable = capacityExceeded;
      const retryAfterSeconds = Number(parsed.retry_after);
      if (capacityExceeded && Number.isFinite(retryAfterSeconds) && retryAfterSeconds >= 0) {
        error.retryAfterMs = retryAfterSeconds * 1000;
      }
      onError?.(error, event);
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
    buffer += decoder.decode();
    buffer = buffer.replace(/\r\n/g, "\n");
    // 冲刷残余
    if (buffer.trim()) dispatch(buffer);
    if (!receivedTerminalEvent && !signal?.aborted) {
      const error = new Error("辅导连接意外结束，输入已保留，请重试。");
      error.retryable = true;
      onError?.(error);
    }
  } catch (err) {
    if (err?.name !== "AbortError" && !signal?.aborted) {
      const error = err instanceof Error ? err : new Error("Tutor stream disconnected.");
      error.retryable = true;
      onError?.(error);
    }
  }
}

async function streamSseGet(url, {
  onEvent,
  onQueued,
  onCardReady,
  onCardFailed,
  onCompleted,
  onFailed,
  onCancelled,
  onError,
  signal,
  lastEventId = "",
  requestId = "",
} = {}) {
  const streamRequestId = requestId || createRequestId();
  const request = (token) => fetch(url, {
    method: "GET",
    headers: {
      Accept: "text/event-stream",
      "X-Request-ID": streamRequestId,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(lastEventId ? { "Last-Event-ID": String(lastEventId) } : {}),
    },
    credentials: "include",
    signal,
  });

  let response;
  try {
    response = await request(tokenStore.getAccessToken());
    if (response.status === 401 && !signal?.aborted) {
      const accessToken = await refreshStoredTokens().catch(() => null);
      if (!accessToken) {
        forceLogout();
        const authError = new Error("登录状态已失效，请重新登录。");
        authError.status = 401;
        authError.retryable = false;
        throw authError;
      }
      response = await request(accessToken);
    }
  } catch (error) {
    if (error?.name !== "AbortError" && !signal?.aborted) {
      const normalized = error instanceof Error ? error : new Error("SSE 请求失败。");
      if (normalized.status === undefined && /401/.test(String(normalized.message))) normalized.status = 401;
      normalized.retryable = !normalized.status;
      onError?.(normalized);
    }
    return;
  }

  if (!response.ok || !response.body) {
    if (response.status === 401) forceLogout();
    const error = new Error(response.status === 401
      ? "登录状态已失效，请重新登录。"
      : `SSE request failed: HTTP ${response.status}`);
    error.status = response.status;
    error.retryable = response.status >= 500 || response.status === 408 || response.status === 429;
    onError?.(error);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let receivedTerminalEvent = false;

  const dispatch = (rawEvent) => {
    let eventName = "message";
    let eventId = "";
    const dataLines = [];
    for (const line of rawEvent.split("\n")) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("id:")) {
        eventId = line.slice(3).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (!dataLines.length) return;

    let data;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch {
      return;
    }

    const event = { event: eventName, data, id: eventId };
    onEvent?.(event);
    if (eventName === "queued") onQueued?.(data, event);
    if (eventName === "card_ready") onCardReady?.(data, event);
    if (eventName === "card_failed") onCardFailed?.(data, event);
    if (eventName === "completed") {
      receivedTerminalEvent = true;
      onCompleted?.(data, event);
    }
    if (eventName === "failed") {
      receivedTerminalEvent = true;
      onFailed?.(data, event);
    }
    if (eventName === "cancelled") {
      receivedTerminalEvent = true;
      onCancelled?.(data, event);
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let separatorIndex;
      while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);
        if (rawEvent.trim()) dispatch(rawEvent);
      }
    }
    buffer += decoder.decode();
    buffer = buffer.replace(/\r\n/g, "\n");
    if (buffer.trim()) dispatch(buffer);
    if (!receivedTerminalEvent && !signal?.aborted) {
      const error = new Error("Resource generation stream ended before completion.");
      error.retryable = true;
      onError?.(error);
    }
  } catch (error) {
    if (error?.name !== "AbortError" && !signal?.aborted) {
      const normalized = error instanceof Error
        ? error
        : new Error("Resource generation stream disconnected.");
      normalized.retryable = true;
      onError?.(normalized);
    }
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
