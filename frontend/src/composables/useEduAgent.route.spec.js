import { beforeEach, describe, expect, it, vi } from "vitest";

const serviceMocks = vi.hoisted(() => ({
  fetchCourses: vi.fn(),
  fetchSessionLearningEventHistory: vi.fn(),
  fetchSessionResources: vi.fn(),
  fetchUserCourses: vi.fn(),
  getSession: vi.fn(),
  switchCourse: vi.fn(),
}));

vi.mock("../services/eduAgentApi", () => ({
  buildSessionId: (userId, courseId) => `${userId}:${courseId}`,
  createSession: vi.fn(),
  enrollCourse: vi.fn(),
  fetchCourses: serviceMocks.fetchCourses,
  fetchKnowledgeGraph: vi.fn(),
  fetchMyProfile: vi.fn(),
  fetchSessionLearningEventHistory: serviceMocks.fetchSessionLearningEventHistory,
  fetchSessionProfileProbe: vi.fn(),
  fetchSessionResources: serviceMocks.fetchSessionResources,
  fetchUserCourses: serviceMocks.fetchUserCourses,
  getCaptcha: vi.fn(),
  getSession: serviceMocks.getSession,
  initSessionPath: vi.fn(),
  login: vi.fn(),
  refreshToken: vi.fn(),
  register: vi.fn(),
  streamSessionTutor: vi.fn(),
  submitSessionLearningEvent: vi.fn(async () => ({})),
  submitSessionProfileInput: vi.fn(),
  switchCourse: serviceMocks.switchCourse,
}));

vi.mock("../stores/learningAssets", () => ({
  useLearningAssetsStore: () => ({
    tutorHistory: [],
    hydrate: vi.fn(async () => undefined),
    read: vi.fn(() => null),
    write: vi.fn(),
    remove: vi.fn(),
    reset: vi.fn(),
  }),
}));

import { useEduAgent } from "./useEduAgent";

function sessionState(courseId, nodeId) {
  return {
    course_id: courseId,
    session: { current_node_id: nodeId },
    learning_path: {
      current_node_id: nodeId,
      nodes: [{ id: nodeId, title: nodeId }],
    },
    dynamic_profile: { knowledge_mastery: { [nodeId]: 0 } },
    resources: { [nodeId]: [] },
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

describe("learning route synchronization", () => {
  const agent = useEduAgent();

  beforeEach(() => {
    agent.handleLogout();
    agent.currentUser.value = { user_id: "route-user" };
    agent.isLoggedIn.value = true;
    serviceMocks.fetchCourses.mockReset().mockResolvedValue([]);
    serviceMocks.fetchSessionLearningEventHistory.mockReset().mockResolvedValue({ events: [] });
    serviceMocks.fetchSessionResources.mockReset().mockResolvedValue({ resources: [] });
    serviceMocks.fetchUserCourses.mockReset();
    serviceMocks.getSession.mockReset();
    serviceMocks.switchCourse.mockReset().mockResolvedValue({});
  });

  it("lets the newest URL win when an older session request resolves late", async () => {
    const oldSession = deferred();
    const courses = [
      { course_id: "course-a", title_cn: "A" },
      { course_id: "course-b", title_cn: "B" },
    ];
    serviceMocks.fetchUserCourses
      .mockResolvedValueOnce({ active_course: "course-a", courses })
      .mockResolvedValueOnce({ active_course: "course-a", courses })
      .mockResolvedValueOnce({ active_course: "course-b", courses });
    serviceMocks.getSession
      .mockReturnValueOnce(oldSession.promise)
      .mockResolvedValueOnce(sessionState("course-b", "node-b"));

    const first = agent.prepareLearningRoute("course-a", "node-a");
    await vi.waitFor(() => expect(serviceMocks.getSession).toHaveBeenCalledTimes(1));

    const second = agent.prepareLearningRoute("course-b", "node-b");
    oldSession.resolve(sessionState("course-a", "node-a"));

    await expect(first).resolves.toMatchObject({ status: "stale" });
    await expect(second).resolves.toMatchObject({
      status: "ready",
      courseId: "course-b",
      nodeId: "node-b",
    });
    expect(agent.currentNode.value).toBe("node-b");
    expect(agent.activeCourse.value?.course_id).toBe("course-b");
    expect(serviceMocks.switchCourse).toHaveBeenCalledWith("course-b");

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(serviceMocks.fetchSessionResources).toHaveBeenCalledTimes(1);
    expect(serviceMocks.fetchSessionResources).toHaveBeenCalledWith(
      "route-user:course-b",
      "node-b",
      { force: false, cardType: "" },
    );
  });
});
