import { beforeEach, describe, expect, it, vi } from "vitest";

const serviceMocks = vi.hoisted(() => ({
  fetchCourses: vi.fn(),
  fetchSessionLearningEventHistory: vi.fn(),
  fetchSessionResources: vi.fn(),
  requestResourceGeneration: vi.fn(),
  streamResourceGeneration: vi.fn(),
  fetchUserCourses: vi.fn(),
  getSession: vi.fn(),
  switchCourse: vi.fn(),
}));
const telemetryMocks = vi.hoisted(() => ({
  reportResourceCacheRead: vi.fn(),
  reportResourceConceptReady: vi.fn(),
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
  requestResourceGeneration: serviceMocks.requestResourceGeneration,
  refreshToken: vi.fn(),
  register: vi.fn(),
  streamSessionTutor: vi.fn(),
  streamResourceGeneration: serviceMocks.streamResourceGeneration,
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

vi.mock("../services/clientTelemetry", () => telemetryMocks);

import { useEduAgent } from "./useEduAgent";
import { createPinia, setActivePinia } from "pinia";

// useEduAgent() is called at describe scope below; the auth store needs an
// active Pinia before that runs.
setActivePinia(createPinia());

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

function resourceCard(nodeId, cardType) {
  return {
    resource_id: `${nodeId}-${cardType}-v1`,
    resource_type: cardType,
    card_type: cardType,
    structured_payload: { title: `${cardType} ${nodeId}` },
  };
}

function completeResourceSet(nodeId) {
  return [
    "concept_map",
    "code_snippet",
    "interactive_exercise",
    "video_summary",
    "diagnostic_quiz",
  ].map((cardType) => resourceCard(nodeId, cardType));
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
    serviceMocks.fetchSessionResources.mockReset().mockResolvedValue({ resources: completeResourceSet("node-b") });
    serviceMocks.requestResourceGeneration.mockReset().mockResolvedValue({ status: "queued", job_id: "job-1" });
    serviceMocks.streamResourceGeneration.mockReset().mockResolvedValue(undefined);
    serviceMocks.fetchUserCourses.mockReset();
    serviceMocks.getSession.mockReset();
    serviceMocks.switchCourse.mockReset().mockResolvedValue({});
    telemetryMocks.reportResourceCacheRead.mockReset();
    telemetryMocks.reportResourceConceptReady.mockReset();
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
    );
  });

  it("renders the concept card before subscribing to the server-started supporting bundle", async () => {
    const courses = [{ course_id: "course-a", title_cn: "A" }];
    let conceptHandlers;
    serviceMocks.fetchUserCourses.mockResolvedValue({ active_course: "course-a", courses });
    serviceMocks.getSession.mockResolvedValue(sessionState("course-a", "node-a"));
    serviceMocks.fetchSessionResources.mockResolvedValue({ resources: [] });
    serviceMocks.requestResourceGeneration
      .mockResolvedValueOnce({ status: "queued", job_id: "concept-job" });
    serviceMocks.streamResourceGeneration
      .mockImplementationOnce((_jobId, handlers) => {
        conceptHandlers = handlers;
        return new Promise(() => {});
      })
      .mockImplementationOnce(() => new Promise(() => {}));

    await expect(agent.prepareLearningRoute("course-a", "node-a")).resolves.toMatchObject({
      status: "ready",
      nodeId: "node-a",
    });
    await vi.waitFor(() => expect(serviceMocks.requestResourceGeneration).toHaveBeenCalledWith(
      "route-user:course-a",
      "node-a",
      { cardTypes: ["concept_map"], force: false, priority: "concept_map" },
    ));
    await vi.waitFor(() => expect(conceptHandlers).toBeTruthy());
    expect(agent.isLoadingNode.value).toBe(true);

    conceptHandlers.onCardReady({ resource: resourceCard("node-a", "concept_map") });

    await vi.waitFor(() => expect(agent.isLoadingNode.value).toBe(false));
    expect(agent.currentCards.value.map((card) => card.resource_type)).toContain("concept_map");
    expect(serviceMocks.requestResourceGeneration).toHaveBeenCalledTimes(1);

    conceptHandlers.onCompleted({
      follow_up_job_id: "support-job",
      follow_up_card_types: ["code_snippet", "interactive_exercise", "video_summary", "diagnostic_quiz"],
    });

    await vi.waitFor(() => expect(serviceMocks.streamResourceGeneration).toHaveBeenCalledWith(
      "support-job",
      expect.any(Object),
    ));
    expect(agent.currentResourceCardStates.value.code_snippet.status).toBe("queued");
  });

  it("renders a cached concept map immediately and starts only the missing supporting cards", async () => {
    const courses = [{ course_id: "course-a", title_cn: "A" }];
    let supportHandlers;
    serviceMocks.fetchUserCourses.mockResolvedValue({ active_course: "course-a", courses });
    serviceMocks.getSession.mockResolvedValue(sessionState("course-a", "node-a"));
    serviceMocks.fetchSessionResources.mockResolvedValue({
      resources: [
        resourceCard("node-a", "concept_map"),
        resourceCard("node-a", "diagnostic_quiz"),
      ],
    });
    serviceMocks.requestResourceGeneration.mockResolvedValue({ status: "queued", job_id: "support-job" });
    serviceMocks.streamResourceGeneration.mockImplementationOnce((_jobId, handlers) => {
      supportHandlers = handlers;
      return new Promise(() => {});
    });

    await expect(agent.prepareLearningRoute("course-a", "node-a")).resolves.toMatchObject({
      status: "ready",
      nodeId: "node-a",
    });
    await vi.waitFor(() => expect(serviceMocks.requestResourceGeneration).toHaveBeenCalledWith(
      "route-user:course-a",
      "node-a",
      {
        cardTypes: ["code_snippet", "interactive_exercise", "video_summary"],
        force: false,
        priority: "supporting_bundle",
      },
    ));

    expect(agent.isLoadingNode.value).toBe(false);
    expect(agent.currentCards.value.map((card) => card.resource_type)).toEqual([
      "concept_map",
      "diagnostic_quiz",
    ]);
    expect(agent.currentResourceCardStates.value.code_snippet.status).toBe("queued");
    expect(telemetryMocks.reportResourceCacheRead).toHaveBeenCalledWith(expect.objectContaining({
      cacheHit: true,
      outcome: "success",
    }));
    expect(telemetryMocks.reportResourceConceptReady).toHaveBeenCalledWith(expect.objectContaining({
      cacheHit: true,
      outcome: "success",
    }));
    expect(supportHandlers).toBeTruthy();
  });

  it("merges an SSE supporting card without overwriting cached cards", async () => {
    const courses = [{ course_id: "course-a", title_cn: "A" }];
    let supportHandlers;
    serviceMocks.fetchUserCourses.mockResolvedValue({ active_course: "course-a", courses });
    serviceMocks.getSession.mockResolvedValue(sessionState("course-a", "node-a"));
    serviceMocks.fetchSessionResources.mockResolvedValue({
      resources: [
        resourceCard("node-a", "concept_map"),
        resourceCard("node-a", "diagnostic_quiz"),
      ],
    });
    serviceMocks.requestResourceGeneration.mockResolvedValue({ status: "queued", job_id: "support-job" });
    serviceMocks.streamResourceGeneration.mockImplementationOnce((_jobId, handlers) => {
      supportHandlers = handlers;
      return new Promise(() => {});
    });

    await agent.prepareLearningRoute("course-a", "node-a");
    await vi.waitFor(() => expect(supportHandlers).toBeTruthy());

    supportHandlers.onCardReady({
      resource: {
        ...resourceCard("node-a", "code_snippet"),
        resource_id: "node-a-code-snippet-v2",
      },
    });

    expect(agent.currentCards.value.map((card) => card.resource_type).sort()).toEqual([
      "code_snippet",
      "concept_map",
      "diagnostic_quiz",
    ]);
    expect(agent.currentCards.value.find((card) => card.resource_type === "concept_map")?.resource_id)
      .toBe("node-a-concept_map-v1");
    expect(agent.currentCards.value.find((card) => card.resource_type === "diagnostic_quiz")?.resource_id)
      .toBe("node-a-diagnostic_quiz-v1");
  });

  it("force-regenerates only the selected card type", async () => {
    const courses = [{ course_id: "course-a", title_cn: "A" }];
    let codeHandlers;
    serviceMocks.fetchUserCourses.mockResolvedValue({ active_course: "course-a", courses });
    serviceMocks.getSession.mockResolvedValue(sessionState("course-a", "node-a"));
    serviceMocks.fetchSessionResources.mockResolvedValue({ resources: completeResourceSet("node-a") });
    serviceMocks.streamResourceGeneration.mockImplementationOnce((_jobId, handlers) => {
      codeHandlers = handlers;
      return new Promise(() => {});
    });

    await agent.prepareLearningRoute("course-a", "node-a");
    await vi.waitFor(() => expect(serviceMocks.fetchSessionResources).toHaveBeenCalledWith(
      "route-user:course-a",
      "node-a",
    ));

    const outcome = await agent.refreshNodeResources("node-a", {
      force: true,
      cardType: "code_snippet",
    });

    expect(outcome.ok).toBe(true);
    expect(serviceMocks.requestResourceGeneration).toHaveBeenCalledWith(
      "route-user:course-a",
      "node-a",
      { cardTypes: ["code_snippet"], force: true, priority: "card" },
    );
    expect(serviceMocks.requestResourceGeneration).toHaveBeenCalledTimes(1);
    await vi.waitFor(() => expect(codeHandlers).toBeTruthy());

    codeHandlers.onCardReady({
      resource: {
        ...resourceCard("node-a", "code_snippet"),
        resource_id: "node-a-code-snippet-v2",
      },
    });

    expect(agent.currentCards.value.map((card) => card.resource_type).sort()).toEqual([
      "code_snippet",
      "concept_map",
      "diagnostic_quiz",
      "interactive_exercise",
      "video_summary",
    ]);
    expect(agent.currentCards.value.find((card) => card.resource_type === "code_snippet")?.resource_id)
      .toBe("node-a-code-snippet-v2");
  });
});
