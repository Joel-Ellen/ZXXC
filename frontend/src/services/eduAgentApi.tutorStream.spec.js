import { afterEach, describe, expect, it, vi } from "vitest";

import { streamSessionTutor } from "./eduAgentApi";


afterEach(() => {
  vi.unstubAllGlobals();
});


describe("Tutor SSE UTF-8 transport", () => {
  it("preserves Chinese text split across byte boundaries", async () => {
    const source = [
      'event: token\ndata: {"token":"中文回答完整显示"}\n\n',
      'event: done\ndata: {"reference_count":0}\n\n',
    ].join("");
    const bytes = new TextEncoder().encode(source);
    const chunks = Array.from(bytes, (byte) => new Uint8Array([byte]));
    let index = 0;
    const stream = new ReadableStream({
      pull(controller) {
        if (index >= chunks.length) {
          controller.close();
          return;
        }
        controller.enqueue(chunks[index]);
        index += 1;
      },
    });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    })));

    let received = "";
    let completed = false;
    await streamSessionTutor("u1:course1", { question: "请解释二叉树" }, {
      onToken(token) {
        received += token;
      },
      onDone() {
        completed = true;
      },
    });

    expect(received).toBe("中文回答完整显示");
    expect(completed).toBe(true);
  });
});
