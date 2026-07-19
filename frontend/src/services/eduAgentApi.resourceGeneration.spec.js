import { afterEach, describe, expect, it, vi } from "vitest";

const authMocks = vi.hoisted(() => ({
  accessToken: "expired-access-token",
  forceLogout: vi.fn(),
  refreshStoredTokens: vi.fn(async () => "renewed-access-token"),
}));

vi.mock("./apiClient", () => ({
  default: {},
  createRequestId: () => "request-id",
  forceLogout: authMocks.forceLogout,
  refreshStoredTokens: authMocks.refreshStoredTokens,
  tokenStore: {
    getAccessToken: () => authMocks.accessToken,
    getRefreshToken: () => "refresh-token",
  },
}));

import {
  streamResourceGeneration,
  streamSessionTutor,
  streamSessionTutorWithReconnect,
} from "./eduAgentApi";

function sseResponse(events) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(events));
      controller.close();
    },
  });
  return { ok: true, status: 200, body };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  authMocks.accessToken = "expired-access-token";
  authMocks.forceLogout.mockClear();
  authMocks.refreshStoredTokens.mockClear();
});

describe("resource generation SSE transport", () => {
  it("forwards the replay cursor and dispatches a resumed card_ready event", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([
      "id: 18",
      "event: card_ready",
      'data: {"card":{"resource_id":"code-v2","resource_type":"code_snippet"}}',
      "",
      "id: 19",
      "event: completed",
      'data: {"job_id":"job-1"}',
      "",
    ].join("\n")));
    vi.stubGlobal("fetch", fetchMock);
    const ready = vi.fn();

    await streamResourceGeneration("job-1", {
      lastEventId: "17",
      onCardReady: ready,
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/resource-generation-jobs/job-1/events");
    expect(fetchMock.mock.calls[0][1].headers["Last-Event-ID"]).toBe("17");
    expect(ready).toHaveBeenCalledWith(
      expect.objectContaining({
        card: expect.objectContaining({ resource_id: "code-v2", resource_type: "code_snippet" }),
      }),
      expect.objectContaining({ event: "card_ready", id: "18" }),
    );
  });

  it("refreshes an expired access token and retries the GET stream once", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, body: null })
      .mockResolvedValueOnce(sseResponse([
        "id: 20",
        "event: completed",
        'data: {"job_id":"job-1"}',
        "",
      ].join("\n")));
    vi.stubGlobal("fetch", fetchMock);
    const completed = vi.fn();

    await streamResourceGeneration("job-1", { onCompleted: completed });

    expect(authMocks.refreshStoredTokens).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer expired-access-token");
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer renewed-access-token");
    expect(fetchMock.mock.calls[1][1].headers["X-Request-ID"])
      .toBe(fetchMock.mock.calls[0][1].headers["X-Request-ID"]);
    expect(completed).toHaveBeenCalledOnce();
  });

  it("forces logout when the GET stream token refresh fails", async () => {
    authMocks.refreshStoredTokens.mockRejectedValueOnce(new Error("refresh rejected"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401, body: null }));
    const streamError = vi.fn();

    await streamResourceGeneration("job-1", { onError: streamError });

    expect(authMocks.forceLogout).toHaveBeenCalledOnce();
    expect(streamError).toHaveBeenCalledWith(expect.objectContaining({ status: 401, retryable: false }));
  });

  it("treats cancelled as a terminal resource event", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([
      "id: 21",
      "event: cancelled",
      'data: {"job_id":"job-1","status":"cancelled"}',
      "",
    ].join("\n")));
    vi.stubGlobal("fetch", fetchMock);
    const cancelled = vi.fn();
    const streamError = vi.fn();

    await streamResourceGeneration("job-1", {
      onCancelled: cancelled,
      onError: streamError,
    });

    expect(cancelled).toHaveBeenCalledWith(
      expect.objectContaining({ job_id: "job-1", status: "cancelled" }),
      expect.objectContaining({ event: "cancelled", id: "21" }),
    );
    expect(streamError).not.toHaveBeenCalled();
  });
});

describe("Tutor SSE authentication", () => {
  it("refreshes an expired access token and retries the stream once", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, body: null })
      .mockResolvedValueOnce(sseResponse([
        "event: token",
        'data: {"token":"已恢复。"}',
        "",
        "event: done",
        'data: {"status":"ok"}',
        "",
      ].join("\n")));
    vi.stubGlobal("fetch", fetchMock);
    const tokenHandler = vi.fn();
    const doneHandler = vi.fn();

    await streamSessionTutor("admin:data_structures", { question: "111" }, {
      onToken: tokenHandler,
      onDone: doneHandler,
    });

    expect(authMocks.refreshStoredTokens).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer expired-access-token");
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer renewed-access-token");
    expect(tokenHandler).toHaveBeenCalledWith("已恢复。");
    expect(doneHandler).toHaveBeenCalledWith({ status: "ok" });
  });

  it("reuses the request id and advances Last-Event-ID across resumptions", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(sseResponse([
        "id: 1",
        "event: token",
        'data: {"token":"A"}',
        "",
      ].join("\n")))
      .mockResolvedValueOnce(sseResponse([
        "id: 2",
        "event: token",
        'data: {"token":"B"}',
        "",
        "id: 3",
        "event: done",
        'data: {"status":"ok"}',
        "",
      ].join("\n")));
    vi.stubGlobal("fetch", fetchMock);
    let received = "";
    const handlers = {
      onToken(token) {
        received += token;
      },
      onError: vi.fn(),
    };

    await streamSessionTutor("admin:data_structures", { question: "resume" }, handlers);
    await streamSessionTutor("admin:data_structures", { question: "resume" }, handlers);

    expect(received).toBe("AB");
    expect(handlers.lastEventId).toBe("3");
    expect(fetchMock.mock.calls[1][1].headers["X-EduAgent-Stream-ID"])
      .toBe(fetchMock.mock.calls[0][1].headers["X-EduAgent-Stream-ID"]);
    expect(fetchMock.mock.calls[1][1].headers["Last-Event-ID"]).toBe("1");
  });

  it("retries capacity errors after retry_after without advancing the cursor", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(sseResponse([
        "event: error",
        'data: {"detail":"TUTOR_STREAM_CAPACITY_EXCEEDED","retry_after":2}',
        "",
      ].join("\n")))
      .mockResolvedValueOnce(sseResponse([
        "id: 1",
        "event: token",
        'data: {"token":"已恢复。"}',
        "",
        "id: 2",
        "event: done",
        'data: {"status":"ok"}',
        "",
      ].join("\n")));
    vi.stubGlobal("fetch", fetchMock);
    const reconnect = vi.fn();

    const request = streamSessionTutorWithReconnect(
      "admin:data_structures",
      { question: "capacity" },
      { onReconnect: reconnect },
    );
    await vi.waitFor(() => expect(reconnect).toHaveBeenCalledOnce());
    expect(reconnect).toHaveBeenCalledWith(expect.objectContaining({ delayMs: 2000 }));
    expect(fetchMock).toHaveBeenCalledOnce();

    await vi.advanceTimersByTimeAsync(2000);
    await request;

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][1].headers["Last-Event-ID"]).toBeUndefined();
  });
});
