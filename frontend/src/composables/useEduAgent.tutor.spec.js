import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const serviceMocks = vi.hoisted(() => ({
  streamSessionTutor: vi.fn(),
  submitSessionLearningEvent: vi.fn(async () => ({})),
}));

vi.mock("../services/eduAgentApi", () => ({
  buildSessionId: (userId, courseId) => `${userId}:${courseId}`,
  createSession: vi.fn(),
  enrollCourse: vi.fn(),
  fetchCourses: vi.fn(),
  fetchKnowledgeGraph: vi.fn(),
  fetchMyProfile: vi.fn(),
  fetchSessionLearningEventHistory: vi.fn(),
  fetchSessionProfileProbe: vi.fn(),
  fetchSessionResources: vi.fn(),
  getSession: vi.fn(),
  fetchUserCourses: vi.fn(),
  getCaptcha: vi.fn(),
  initSessionPath: vi.fn(),
  login: vi.fn(),
  refreshToken: vi.fn(),
  register: vi.fn(),
  requestResourceGeneration: vi.fn(),
  streamResourceGeneration: vi.fn(),
  streamSessionTutor: serviceMocks.streamSessionTutor,
  submitSessionLearningEvent: serviceMocks.submitSessionLearningEvent,
  submitSessionProfileInput: vi.fn(),
  switchCourse: vi.fn(),
}));

vi.mock("../stores/learningAssets", () => ({
  useLearningAssetsStore: () => ({
    tutorHistory: [],
    hydrate: vi.fn(async () => undefined),
    read: vi.fn(() => null),
    write: vi.fn(),
    remove: vi.fn(),
  }),
}));

import { useEduAgent } from "./useEduAgent";

describe("Tutor stream transport hardening", () => {
  const agent = useEduAgent();

  beforeEach(() => {
    agent.messages.value = [];
    serviceMocks.streamSessionTutor.mockReset();
    serviceMocks.submitSessionLearningEvent.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("turns a directly rejected transport into a terminal assistant error", async () => {
    serviceMocks.streamSessionTutor.mockRejectedValueOnce(new Error("transport rejected"));

    await expect(agent.sendTutorMessage("解释二叉树")).rejects.toThrow("transport rejected");

    const assistant = agent.messages.value.at(-1);
    const handlers = serviceMocks.streamSessionTutor.mock.calls[0][2];
    expect(handlers.signal.aborted).toBe(true);
    expect(assistant).toMatchObject({
      role: "assistant",
      isStreaming: false,
      streamStatus: "error",
      streamError: "transport rejected",
    });
  });

  it("aborts a stalled stream and releases the caller after the idle timeout", async () => {
    vi.useFakeTimers();
    serviceMocks.streamSessionTutor.mockImplementationOnce((sessionId, payload, handlers) => (
      new Promise((resolve) => {
        handlers.signal.addEventListener("abort", resolve, { once: true });
      })
    ));

    const request = agent.sendTutorMessage("解释红黑树");
    const rejection = expect(request).rejects.toMatchObject({ name: "TimeoutError" });
    await vi.advanceTimersByTimeAsync(45_000);

    await rejection;
    const assistant = agent.messages.value.at(-1);
    expect(assistant.isStreaming).toBe(false);
    expect(assistant.streamStatus).toBe("error");
    expect(serviceMocks.streamSessionTutor.mock.calls[0][2].signal.aborted).toBe(true);
  });
});
