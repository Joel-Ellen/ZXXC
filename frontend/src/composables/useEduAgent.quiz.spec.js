import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const apiMocks = vi.hoisted(() => ({
  fetchSessionResources: vi.fn(),
  getSession: vi.fn(),
  submitSessionLearningEvent: vi.fn(),
}));

vi.mock("../services/eduAgentApi", async (importOriginal) => ({
  ...(await importOriginal()),
  fetchSessionResources: apiMocks.fetchSessionResources,
  getSession: apiMocks.getSession,
  submitSessionLearningEvent: apiMocks.submitSessionLearningEvent,
}));

vi.mock("../stores/learningAssets", () => ({
  useLearningAssetsStore: () => ({
    tutorHistory: [],
    hydrate: vi.fn(async () => undefined),
    reset: vi.fn(),
  }),
}));

import { useEduAgent } from "./useEduAgent";

setActivePinia(createPinia());

describe("quiz result navigation", () => {
  beforeEach(() => {
    apiMocks.fetchSessionResources.mockReset();
    apiMocks.getSession.mockReset();
    apiMocks.submitSessionLearningEvent.mockReset();
  });

  it("keeps the evaluated node resources when the server advances to the next node", async () => {
    const quizCard = {
      resource_id: "node-a-quiz",
      resource_type: "diagnostic_quiz",
    };
    const cachedCards = [
      { resource_id: "node-a-concept", resource_type: "concept_map" },
      { resource_id: "node-a-code", resource_type: "code_snippet" },
      { resource_id: "node-a-practice", resource_type: "interactive_exercise" },
      { resource_id: "node-a-video", resource_type: "video_summary" },
      quizCard,
    ];
    const agent = useEduAgent();
    agent.currentUser.value = { user_id: "quiz-user" };
    agent.activeCourse.value = { course_id: "course-a" };
    agent.currentNode.value = "node-a";
    agent.mastery.value = { "node-a": 0.4, "node-b": 0 };
    agent.resources.value = { "node-a": [quizCard] };

    apiMocks.submitSessionLearningEvent.mockResolvedValue({
      event_id: "quiz-event",
      effective_correctness: 1,
      evaluated_node_id: "node-a",
      next_node_id: "node-b",
      advanced_to_next_node: true,
      mastery_before: 0.4,
      mastery_after: 0.8,
    });
    apiMocks.getSession.mockResolvedValue({
      session: { current_node_id: "node-b" },
      learning_path: {
        current_node_id: "node-b",
        nodes: [
          { id: "node-a", title: "Node A", mastery: 0.8 },
          { id: "node-b", title: "Node B", mastery: 0 },
        ],
      },
      dynamic_profile: { knowledge_mastery: { "node-a": 0.8, "node-b": 0 } },
      resources: { "node-b": [] },
    });
    apiMocks.fetchSessionResources.mockResolvedValue({ resources: cachedCards });

    await agent.submitQuiz({
      resourceId: quizCard.resource_id,
      answers: [{ questionId: "question-a", selectedOptionIndex: 0 }],
    });

    expect(agent.currentNode.value).toBe("node-a");
    expect(agent.currentCards.value).toEqual(cachedCards);
    expect(apiMocks.fetchSessionResources).toHaveBeenCalledWith("quiz-user:course-a", "node-a");
    expect(agent.lastDiagnostic.value).toMatchObject({
      evaluatedNodeId: "node-a",
      nextNodeId: "node-b",
    });
  });
});
