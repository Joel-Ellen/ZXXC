import { afterEach, describe, expect, it, vi } from "vitest";

const authMocks = vi.hoisted(() => ({
  accessToken: "expired-access-token",
  refreshStoredTokens: vi.fn(async () => "renewed-access-token"),
}));

vi.mock("./apiClient", () => ({
  default: {},
  createRequestId: () => "request-id",
  refreshStoredTokens: authMocks.refreshStoredTokens,
  tokenStore: {
    getAccessToken: () => authMocks.accessToken,
    getRefreshToken: () => "refresh-token",
  },
}));

import { streamResourceGeneration, streamSessionTutor } from "./eduAgentApi";

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
  vi.unstubAllGlobals();
  authMocks.accessToken = "expired-access-token";
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
});
