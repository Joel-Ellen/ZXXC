import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../services/courseLifecycleApi", () => ({
  courseLifecycleErrorMessage: (error, fallback) => error?.message || fallback,
  enrollInCourse: vi.fn(),
  fetchCourseCatalog: vi.fn(),
  fetchEnrollmentState: vi.fn(),
  fetchLearningSummary: vi.fn(),
  leaveCourse: vi.fn(),
  normalizeCourse: (course) => course,
  switchActiveCourse: vi.fn(),
}));

import { useCourseLifecycleStore } from "./courseLifecycle";

describe("courseLifecycle derived learning state", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("filters departed courses and falls back to the active course position", () => {
    const store = useCourseLifecycleStore();
    store.catalog = [
      { course_id: "course-a", title_cn: "算法", node_count: 8 },
      { course_id: "course-b", title_cn: "数据库", node_count: 6 },
    ];
    store.enrollment = {
      active_course: "course-a",
      courses: [{
        course_id: "course-a",
        title_cn: "算法",
        last_node_id: "node-3",
        last_activity_at: "2026-07-13T11:00:00Z",
      }],
    };
    store.learningSummary = {
      courses: [],
      recent_learning: [
        { course_id: "course-b", node_id: "node-9", occurred_at: "2026-07-13T12:00:00Z" },
        { course_id: "course-a", node_id: "node-2", occurred_at: "2026-07-13T10:00:00Z" },
      ],
      continue_learning: {
        course_id: "course-b",
        node_id: "node-9",
        occurred_at: "2026-07-13T12:00:00Z",
      },
    };

    expect(store.recentLearning).toEqual([expect.objectContaining({
      course_id: "course-a",
      node_id: "node-2",
      course_title: "算法",
    })]);
    expect(store.continueLearning).toEqual({
      course_id: "course-a",
      node_id: "node-3",
      occurred_at: "2026-07-13T11:00:00Z",
    });
  });
});
