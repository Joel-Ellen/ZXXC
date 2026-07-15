import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createRefreshRecoveryReporter,
  isLearningRouteReload,
  markLoginSuccess,
  reportClientSessionStarted,
  reportNextTaskReady,
  reportResourceCacheRead,
  reportResourceConceptReady,
  reportClientMetric,
} from "./clientTelemetry";

afterEach(() => {
  globalThis.localStorage?.removeItem("access_token");
  globalThis.sessionStorage?.removeItem("eduagent.client_session_reported");
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("client telemetry", () => {
  it("sends only allowlisted launch fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    await reportClientMetric("frontend_exception", {
      surface: "learn",
      kind: "vue",
      message: "private learner content",
      userId: "learner-1",
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    const [, request] = fetchMock.mock.calls[0];
    expect(JSON.parse(request.body)).toEqual({
      event: "frontend_exception",
      surface: "learn",
      kind: "vue",
    });
  });

  it("authenticates release metrics when a session token exists", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    globalThis.localStorage?.setItem("access_token", "session-token");

    await reportClientMetric("next_task_ready", { surface: "app", durationMs: 1200 });

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer session-token");
  });

  it("reports one authenticated frontend session", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    globalThis.localStorage?.setItem("access_token", "session-token");

    await expect(reportClientSessionStarted({ surface: "app" })).resolves.toBe(true);
    await expect(reportClientSessionStarted({ surface: "app" })).resolves.toBe(false);

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      event: "client_session_started",
      surface: "app",
    });
  });

  it("recognizes only reloads of a learning route", () => {
    const performanceApi = {
      getEntriesByType: () => [{ type: "reload" }],
    };

    expect(isLearningRouteReload({ performanceApi, pathname: "/learn/course/N01" })).toBe(true);
    expect(isLearningRouteReload({ performanceApi, pathname: "/courses" })).toBe(false);
    expect(isLearningRouteReload({
      performanceApi: { getEntriesByType: () => [{ type: "navigate" }] },
      pathname: "/learn/course/N01",
    })).toBe(false);
  });

  it("reports one refresh recovery result", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    const reporter = createRefreshRecoveryReporter({
      performanceApi: { getEntriesByType: () => [{ type: "reload" }] },
      pathname: "/learn/course/N01",
    });

    reporter.success();
    reporter.failure();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      event: "refresh_recovery",
      outcome: "success",
    });
  });

  it("measures login-to-task readiness without sending identity data", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    const values = new Map();
    const storage = {
      getItem: (key) => values.get(key) ?? null,
      removeItem: (key) => values.delete(key),
      setItem: (key, value) => values.set(key, value),
    };

    expect(markLoginSuccess({ now: 1000, storage })).toBe(true);
    await reportNextTaskReady({ now: 4200, storage, surface: "app" });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      event: "next_task_ready",
      surface: "app",
      duration_ms: 3200,
    });
    await expect(reportNextTaskReady({ now: 4300, storage, surface: "app" })).resolves.toBe(false);
  });

  it("reports resource read and concept readiness timings without node identity", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    await reportResourceCacheRead({ durationMs: 185, cacheHit: true });
    await reportResourceConceptReady({ durationMs: 940, cacheHit: false });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      event: "resource_cache_read",
      surface: "learn",
      duration_ms: 185,
      cache_hit: true,
      outcome: "success",
    });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      event: "resource_concept_ready",
      surface: "learn",
      duration_ms: 940,
      cache_hit: false,
      outcome: "success",
    });
  });
});
