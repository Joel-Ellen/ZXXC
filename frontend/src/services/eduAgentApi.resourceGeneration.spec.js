import { afterEach, describe, expect, it, vi } from "vitest";
import { streamResourceGeneration } from "./eduAgentApi";

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
