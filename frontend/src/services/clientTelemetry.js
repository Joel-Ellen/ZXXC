const CLIENT_EVENT_ENDPOINT = "/api/ops/client-events";
const ACCESS_TOKEN_KEY = "access_token";
const LOGIN_READY_MARKER = "eduagent.login_ready_started_at";
const SESSION_REPORTED_MARKER = "eduagent.client_session_reported";
const ALLOWED_EVENTS = new Set([
  "client_session_started",
  "frontend_exception",
  "next_task_ready",
  "refresh_recovery",
  "resource_cache_read",
  "resource_concept_ready",
]);
const ALLOWED_SURFACES = new Set(["app", "auth", "learn", "other"]);
const ALLOWED_KINDS = new Set(["api", "bootstrap", "unhandled_rejection", "vue", "window"]);
const ALLOWED_OUTCOMES = new Set(["failure", "success"]);
const RESOURCE_TIMING_EVENTS = new Set(["resource_cache_read", "resource_concept_ready"]);

export function currentTelemetrySurface(pathname = globalThis.location?.pathname || "") {
  if (pathname.startsWith("/learn/")) return "learn";
  if (pathname === "/login" || pathname.includes("password") || pathname.includes("verify")) return "auth";
  if (pathname.startsWith("/app") || pathname.startsWith("/courses") || pathname.startsWith("/review")
    || pathname.startsWith("/progress") || pathname.startsWith("/account") || pathname.startsWith("/settings")) {
    return "app";
  }
  return "other";
}

export function isLearningRouteReload({
  performanceApi = globalThis.performance,
  pathname = globalThis.location?.pathname || "",
} = {}) {
  if (!pathname.startsWith("/learn/")) return false;
  const entries = typeof performanceApi?.getEntriesByType === "function"
    ? performanceApi.getEntriesByType("navigation")
    : [];
  return Array.from(entries || []).some((entry) => entry?.type === "reload");
}

function normalizedPayload(event, details = {}) {
  if (!ALLOWED_EVENTS.has(event)) return null;
  const surface = ALLOWED_SURFACES.has(details.surface)
    ? details.surface
    : currentTelemetrySurface();
  if (event === "client_session_started") return { event, surface };
  if (event === "frontend_exception") {
    return {
      event,
      surface,
      kind: ALLOWED_KINDS.has(details.kind) ? details.kind : "window",
    };
  }
  if (event === "next_task_ready") {
    const durationMs = Number(details.durationMs);
    if (!Number.isFinite(durationMs) || durationMs < 0 || durationMs > 600_000) return null;
    return { event, surface, duration_ms: Math.round(durationMs) };
  }
  if (RESOURCE_TIMING_EVENTS.has(event)) {
    const durationMs = Number(details.durationMs);
    if (!Number.isFinite(durationMs) || durationMs < 0 || durationMs > 600_000) return null;
    return {
      event,
      surface,
      duration_ms: Math.round(durationMs),
      cache_hit: Boolean(details.cacheHit),
      outcome: ALLOWED_OUTCOMES.has(details.outcome) ? details.outcome : "success",
    };
  }
  if (!ALLOWED_OUTCOMES.has(details.outcome)) return null;
  return { event, surface, outcome: details.outcome };
}

export function markLoginSuccess({ now = Date.now(), storage = globalThis.sessionStorage } = {}) {
  try {
    storage?.setItem(LOGIN_READY_MARKER, String(now));
    return true;
  } catch {
    return false;
  }
}

export function reportNextTaskReady({
  now = Date.now(),
  storage = globalThis.sessionStorage,
  surface = currentTelemetrySurface(),
} = {}) {
  let startedAt;
  try {
    startedAt = Number(storage?.getItem(LOGIN_READY_MARKER));
    storage?.removeItem(LOGIN_READY_MARKER);
  } catch {
    return Promise.resolve(false);
  }
  if (!Number.isFinite(startedAt) || startedAt <= 0 || now < startedAt) {
    return Promise.resolve(false);
  }
  return reportClientMetric("next_task_ready", { surface, durationMs: now - startedAt });
}

export function reportResourceCacheRead({
  durationMs,
  cacheHit = false,
  outcome = "success",
  surface = "learn",
} = {}) {
  return reportClientMetric("resource_cache_read", {
    durationMs,
    cacheHit,
    outcome,
    surface,
  });
}

export function reportResourceConceptReady({
  durationMs,
  cacheHit = false,
  outcome = "success",
  surface = "learn",
} = {}) {
  return reportClientMetric("resource_concept_ready", {
    durationMs,
    cacheHit,
    outcome,
    surface,
  });
}

export function reportClientMetric(event, details = {}) {
  const payload = normalizedPayload(event, details);
  if (!payload || typeof globalThis.fetch !== "function") return Promise.resolve(false);
  let accessToken = "";
  try {
    accessToken = globalThis.localStorage?.getItem(ACCESS_TOKEN_KEY) || "";
  } catch {
    accessToken = "";
  }
  return globalThis.fetch(CLIENT_EVENT_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify(payload),
    credentials: "same-origin",
    keepalive: true,
  }).then((response) => response.ok).catch(() => false);
}

export function reportClientSessionStarted({
  storage = globalThis.sessionStorage,
  surface = currentTelemetrySurface(),
} = {}) {
  try {
    if (!globalThis.localStorage?.getItem(ACCESS_TOKEN_KEY)) return Promise.resolve(false);
    if (storage?.getItem(SESSION_REPORTED_MARKER)) return Promise.resolve(false);
    storage?.setItem(SESSION_REPORTED_MARKER, "1");
  } catch {
    return Promise.resolve(false);
  }
  return reportClientMetric("client_session_started", { surface }).then((accepted) => {
    if (!accepted) {
      try {
        storage?.removeItem(SESSION_REPORTED_MARKER);
      } catch {
        // A storage failure should not affect the application session.
      }
    }
    return accepted;
  });
}

export function createRefreshRecoveryReporter(options = {}) {
  let pending = isLearningRouteReload(options);
  return {
    success() {
      if (!pending) return;
      pending = false;
      void reportClientMetric("refresh_recovery", { surface: "learn", outcome: "success" });
    },
    failure() {
      if (!pending) return;
      pending = false;
      void reportClientMetric("refresh_recovery", { surface: "learn", outcome: "failure" });
    },
  };
}
