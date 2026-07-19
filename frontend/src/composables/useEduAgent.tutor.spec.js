import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const serviceMocks = vi.hoisted(() => ({
  streamSessionTutor: vi.fn(),
  submitSessionLearningEvent: vi.fn(async () => ({})),
}));
const assetMocks = vi.hoisted(() => ({
  tutorHistory: [],
  hydrate: vi.fn(async () => undefined),
  read: vi.fn(() => null),
  write: vi.fn(),
  remove: vi.fn(),
  reset: vi.fn(),
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
  useLearningAssetsStore: () => assetMocks,
}));

import { useEduAgent } from "./useEduAgent";
import { createPinia, setActivePinia } from "pinia";

// useEduAgent() is called at describe scope below; the auth store needs an
// active Pinia before that runs.
setActivePinia(createPinia());

describe("Tutor stream transport hardening", () => {
  const agent = useEduAgent();

  beforeEach(() => {
    agent.messages.value = [];
    agent.agentFeedback.value = [];
    serviceMocks.streamSessionTutor.mockReset();
    serviceMocks.submitSessionLearningEvent.mockClear();
    assetMocks.tutorHistory = [];
    assetMocks.hydrate.mockReset().mockResolvedValue(undefined);
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
      content: "发送失败，输入内容已保留，请稍后重试。",
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

  it("restores persisted tutor history and exposes the latest answer in agent collaboration", async () => {
    serviceMocks.streamSessionTutor.mockImplementationOnce(async (sessionId, payload, handlers) => {
      handlers.onToken("二叉树由节点和边组成。");
      assetMocks.tutorHistory = [
        {
          key: "tutor-1-user",
          exchange_id: "tutor-1",
          sequence: 0,
          role: "user",
          content: "解释二叉树",
          context_type: "concept",
        },
        {
          key: "tutor-1-assistant",
          exchange_id: "tutor-1",
          sequence: 1,
          role: "assistant",
          content: "二叉树由节点和边组成。",
          context_type: "concept",
        },
      ];
      handlers.onDone({ reference_count: 0 });
    });

    await expect(agent.sendTutorMessage("解释二叉树", "concept")).resolves.toEqual({ status: "ok" });

    expect(assetMocks.hydrate).toHaveBeenCalledWith("demo_user:data_structures");
    expect(agent.messages.value).toEqual([
      expect.objectContaining({ role: "user", content: "解释二叉树", isStreaming: false }),
      expect.objectContaining({ role: "assistant", content: "二叉树由节点和边组成。", isStreaming: false }),
    ]);
    expect(agent.agentFeedback.value[0]).toMatchObject({
      agent: "Tutor",
      stage: "AI 问答智能体",
      status: "success",
      details_md: "二叉树由节点和边组成。",
    });
    expect(serviceMocks.streamSessionTutor).toHaveBeenCalledWith(
      "demo_user:data_structures",
      expect.objectContaining({ question: "解释二叉树", context_type: "concept" }),
      expect.any(Object),
    );
  });
});
