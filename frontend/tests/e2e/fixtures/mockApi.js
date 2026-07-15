import { expect } from "@playwright/test";

export const mockUser = Object.freeze({
  user_id: "e2e_user",
  username: "e2e_user",
  display_name: "E2E Learner",
  email: "learner@example.test",
});

export const mockCourses = Object.freeze([
  {
    course_id: "course-a",
    title: "Data Structures",
    title_cn: "数据结构入门",
    description: "Deterministic course fixture.",
    description_cn: "用可验证的练习掌握数组、栈与队列。",
    category: "计算机基础",
    difficulty: "beginner",
    estimated_hours: 6,
    node_count: 2,
    total_nodes: 2,
    progress: 0.25,
    completed_nodes: 0,
    last_node_id: "arrays",
    last_node_title: "数组基础",
    last_activity_at: "2026-07-13T08:00:00Z",
    icon: "DS",
    is_active: true,
  },
  {
    course_id: "course-b",
    title: "Python Basics",
    title_cn: "Python 基础",
    description: "A second deterministic course fixture.",
    description_cn: "从语法到函数的基础训练。",
    category: "编程语言",
    difficulty: "beginner",
    estimated_hours: 4,
    node_count: 2,
    total_nodes: 2,
    progress: 0,
    completed_nodes: 0,
    last_node_id: "syntax",
    last_node_title: "语法基础",
    last_activity_at: "2026-07-12T08:00:00Z",
    icon: "PY",
  },
]);

const mockQuizResource = Object.freeze({
  resource_id: "quiz-arrays-v1",
  node_id: "arrays",
  card_type: "diagnostic_quiz",
  resource_type: "diagnostic_quiz",
  body_markdown: "",
  structured_payload: {
    render_type: "diagnostic_quiz",
    title: "数组基础诊断",
    questions: [
      {
        id: "arrays-q1",
        prompt: "数组的第一个索引通常是什么？",
        options: ["0", "1", "-1"],
        explanation: "多数编程语言使用从 0 开始的数组索引。",
        skill_tag: "核心约束",
        difficulty: "medium",
      },
      {
        id: "arrays-q2",
        prompt: "访问数组元素前最需要检查什么？",
        options: ["边界范围", "变量名称", "注释长度"],
        explanation: "索引必须位于数组的有效边界内。",
        skill_tag: "边界条件",
        difficulty: "medium",
      },
    ],
    pass_threshold: 0.65,
  },
});

const mockRetestQuizResource = Object.freeze({
  ...mockQuizResource,
  resource_id: "quiz-arrays-retest-v2",
  structured_payload: {
    ...mockQuizResource.structured_payload,
    title: "数组基础复测",
  },
});

const mockCodeResource = Object.freeze({
  resource_id: "code-arrays-v1",
  node_id: "arrays",
  card_type: "code_snippet",
  resource_type: "code_snippet",
  body_markdown: "```python\ndef first_value(values):\n    return values[0]\n```",
  structured_payload: {
    render_type: "code_snippet",
    title: "读取数组首项",
    scenario: "实现一个返回数组首项的函数。",
    language: "python",
    code: "def first_value(values):\n    return values[0]",
    practice: {
      problem_id: "arrays-first-value",
      language: "python",
      starter_code: "def first_value(values):\n    pass\n",
    },
  },
});

const mockConceptResource = Object.freeze({
  resource_id: "concept-arrays-v1",
  node_id: "arrays",
  card_type: "concept_map",
  resource_type: "concept_map",
  body_markdown: "数组使用连续索引定位元素。",
  structured_payload: {
    render_type: "concept_map",
    title: "数组索引讲解",
    summary: "从零开始的索引把位置映射到数组元素。",
    objectives: ["识别有效索引范围"],
  },
});

const mockReviewPracticeResource = Object.freeze({
  resource_id: "practice-arrays-review-v1",
  node_id: "arrays",
  card_type: "interactive_exercise",
  resource_type: "interactive_exercise",
  body_markdown: "",
  structured_payload: {
    render_type: "interactive_exercise",
    title: "数组索引定向练习",
    goal: "修正数组起始索引的概念偏差。",
    prompt: "选择数组的第一个有效索引。",
    questions: [{
      id: "arrays-targeted-q1",
      prompt: "数组的第一个有效索引是什么？",
      options: ["0", "1", "-1"],
      explanation: "多数编程语言的数组索引从 0 开始。",
    }],
    hints: ["从最常见的零基索引规则开始判断。"],
  },
});

const mockReviewItem = Object.freeze({
  review_item_id: "review-arrays-q1",
  source_event_id: "lesson-failure-e2e",
  source_resource_id: "quiz-arrays-v1",
  review_kind: "diagnostic_quiz",
  node_id: "arrays",
  node_title: "数组基础",
  question_id: "arrays-q1",
  question_prompt: "数组的第一个索引通常是什么？",
  error_type: "concept_understanding",
  original_answer: "1",
  original_answer_index: 1,
  correct_answer: "0",
  correct_answer_index: 0,
  explanation: "多数编程语言使用从 0 开始的数组索引。",
  status: "due",
  phase: "material_review",
  attempt_count: 1,
  next_review_at: "2026-07-13T09:00:00Z",
  updated_at: "2026-07-13T08:30:00Z",
  recommended_materials: [],
});

const mockPracticeProblem = Object.freeze({
  status: "ok",
  problem_id: "arrays-first-value",
  version: "1",
  title: "读取数组首项",
  prompt: "实现 first_value(values)，返回数组中的第一项。",
  constraints: "输入数组至少包含一个元素。",
  language: "python",
  starter_code: "def first_value(values):\n    pass\n",
  public_test_count: 1,
  hidden_test_count: 1,
  public_tests: [{
    id: "public-1",
    name: "公开测试 1",
    input: [[3, 5, 8]],
    expected: 3,
    visibility: "public",
  }],
});

const emptyAssets = () => ({
  tutor_history: {},
  drafts: {},
  code_drafts: {},
  quiz_progress: {},
  annotations: {},
  bookmarks: {},
  recent_learning: {},
  scroll_positions: {},
  card_state: {},
  latest_diagnostic: {},
});

function sessionState(courseId = "course-a", resourcesByNode = {}) {
  const python = courseId === "course-b";
  const nodes = python
    ? [
        { id: "syntax", title: "语法基础" },
        { id: "functions", title: "函数" },
      ]
    : [
        { id: "arrays", title: "数组基础" },
        { id: "stacks", title: "栈与队列" },
      ];

  return {
    session: { current_node_id: nodes[0].id },
    learning_path: {
      current_node_id: nodes[0].id,
      nodes,
    },
    dynamic_profile: {
      knowledge_mastery: Object.fromEntries(nodes.map((node, index) => [node.id, index ? 0 : 0.25])),
      capability_radar: [0.4, 0.5, 0.45, 0.55, 0.5],
      diagnostic_report_md: "",
    },
    resources: Object.fromEntries(nodes.map((node) => [node.id, resourcesByNode[node.id] || []])),
    agent_feedback: [],
    pipeline_log: [],
  };
}

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function sse(route, events) {
  const body = events.map(({ event, data, id }) => {
    const lines = [];
    if (id) lines.push(`id: ${id}`);
    lines.push(`event: ${event}`, `data: ${JSON.stringify(data)}`);
    return `${lines.join("\n")}\n\n`;
  }).join("");
  return route.fulfill({ status: 200, contentType: "text/event-stream", body });
}

function requestBody(request) {
  try {
    return request.postDataJSON() || {};
  } catch {
    return {};
  }
}

function courseIdFromSessionPath(pathname) {
  const match = pathname.match(/^\/api\/sessions\/([^/]+)/);
  if (!match) return "course-a";
  const sessionId = decodeURIComponent(match[1]);
  return sessionId.split(":").slice(1).join(":") || "course-a";
}

export async function installMockApi(page, options = {}) {
  const arrayResources = [
    ...(options.withQuiz ? [mockQuizResource] : []),
    ...(options.withCodePractice ? [mockCodeResource] : []),
    ...(options.withReviewItem ? [mockReviewPracticeResource] : []),
  ];
  const state = {
    authenticated: options.authenticated ?? false,
    failLoginAttempts: options.failLoginAttempts ?? 0,
    failCourseCatalogAttempts: options.failCourseCatalogAttempts ?? 0,
    failTutorAttempts: options.failTutorAttempts ?? 0,
    disconnectTutorAttempts: options.disconnectTutorAttempts ?? 0,
    failResourceGenerationAttempts: options.failResourceGenerationAttempts ?? 0,
    failPracticeRunAttempts: options.failPracticeRunAttempts ?? 0,
    failPracticeSubmitAttempts: options.failPracticeSubmitAttempts ?? 0,
    failAnswerSubmitAttempts: options.failAnswerSubmitAttempts ?? 0,
    failReviewDashboardAttempts: options.failReviewDashboardAttempts ?? 0,
    failPrepareRetestAttempts: options.failPrepareRetestAttempts ?? 0,
    failRetestResourceAttempts: options.failRetestResourceAttempts ?? 0,
    activeCourseId: options.activeCourseId || "course-a",
    enrolledCourseIds: new Set(options.enrolledCourseIds || mockCourses.map((course) => course.course_id)),
    loginRequests: [],
    courseCatalogRequests: [],
    courseActions: [],
    tutorRequests: [],
    practiceRequests: { run: [], submit: [] },
    learningEventRequests: [],
    learningEvents: [],
    reviewDashboardRequests: [],
    reviewStartRequests: [],
    prepareRetestRequests: [],
    retestCreationCount: 0,
    retestResultsByPracticeEvent: new Map(),
    clientEvents: [],
    assetPatches: [],
    resourceRequests: [],
    resourceGenerationRequests: [],
    resourceGenerationJobs: new Map(),
    unhandledRequests: [],
    assets: emptyAssets(),
    assetRevision: 1,
    resourcesByNode: arrayResources.length ? { arrays: arrayResources } : {},
    reviewItems: options.withReviewItem ? [{ ...mockReviewItem }] : [],
  };

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const method = request.method();

    if (method === "GET" && pathname === "/api/auth/captcha-json") {
      return json(route, {
        captcha_token: `captcha-${state.loginRequests.length + 1}`,
        svg: '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40" role="img" aria-label="8"><text x="12" y="27">4 + 4</text></svg>',
      });
    }

    if (method === "POST" && pathname === "/api/auth/login") {
      const body = requestBody(request);
      state.loginRequests.push(body);
      if (state.failLoginAttempts > 0) {
        state.failLoginAttempts -= 1;
        return json(route, { detail: "凭据错误，请重试。" }, 401);
      }
      state.authenticated = true;
      return json(route, {
        access_token: "e2e-access-token",
        refresh_token: "e2e-refresh-token",
        token_type: "bearer",
        user: mockUser,
      });
    }

    if (method === "POST" && pathname === "/api/auth/refresh") {
      if (!state.authenticated) return json(route, { detail: "Session expired" }, 401);
      return json(route, {
        access_token: "e2e-access-token",
        refresh_token: "e2e-refresh-token",
        token_type: "bearer",
      });
    }

    if (method === "GET" && pathname === "/api/auth/me") {
      if (!state.authenticated) return json(route, { detail: "Not authenticated" }, 401);
      return json(route, mockUser);
    }

    if (method === "GET" && pathname === "/api/user/profile") {
      return json(route, {
        ...mockUser,
        university: "测试大学",
        major: "计算机科学",
        grade: "大二",
        weekly_study_hours: 6,
        learning_goal: "完成数据结构课程",
        preferred_resource_style: "textual",
        preferred_pace: "steady",
        preferred_practice_intensity: "balanced",
        email_verified: true,
        email_verified_at: "2026-07-13T08:00:00Z",
      });
    }

    if (method === "GET" && pathname === "/api/user/settings") {
      return json(route, {
        preferences: {
          theme: "light",
          high_contrast: false,
          reduce_motion: false,
          font_size: 16,
        },
        privacy: {
          analytics_enabled: false,
          personalization_enabled: true,
          profile_visibility: "private",
        },
        email_verified: true,
        email_verified_at: "2026-07-13T08:00:00Z",
      });
    }

    if (method === "GET" && pathname === "/api/auth/sessions") {
      return json(route, {
        current_session_id: "e2e-device",
        sessions: [{
          session_id: "e2e-device",
          current: true,
          device_name: "Chromium",
          created_at: "2026-07-13T08:00:00Z",
          last_seen_at: "2026-07-13T09:00:00Z",
        }],
      });
    }

    if (method === "POST" && pathname === "/api/ops/client-events") {
      state.clientEvents.push(requestBody(request));
      return json(route, { status: "accepted" }, 202);
    }

    if (method === "GET" && pathname === "/api/courses") {
      state.courseCatalogRequests.push({ search: url.searchParams.get("search") || "" });
      if (state.failCourseCatalogAttempts > 0) {
        state.failCourseCatalogAttempts -= 1;
        return json(route, { detail: "课程目录暂时不可用，请原位重试。" }, 503);
      }
      return json(route, { courses: mockCourses });
    }

    if (method === "GET" && pathname.startsWith("/api/courses/")) {
      const courseId = decodeURIComponent(pathname.slice("/api/courses/".length));
      const course = mockCourses.find((item) => item.course_id === courseId);
      return course ? json(route, course) : json(route, { detail: "Course not found" }, 404);
    }

    if (method === "GET" && pathname === "/api/user/courses") {
      return json(route, {
        active_course: state.activeCourseId,
        courses: mockCourses.filter((course) => state.enrolledCourseIds.has(course.course_id)),
      });
    }

    if (method === "GET" && pathname === "/api/user/learning-summary") {
      return json(route, {
        courses: mockCourses.map((course) => ({
          course_id: course.course_id,
          progress: course.progress,
          completed_nodes: course.completed_nodes,
          total_nodes: course.total_nodes,
          last_node_id: course.last_node_id,
          last_node_title: course.last_node_title,
          last_activity_at: course.last_activity_at,
          last_event_type: "content_viewed",
        })),
        recent_learning: [{
          course_id: "course-a",
          course_title: "数据结构入门",
          node_id: "arrays",
          node_title: "数组基础",
          event_type: "content_viewed",
          occurred_at: "2026-07-13T08:00:00Z",
          resource_id: "",
        }],
        continue_learning: {
          course_id: "course-a",
          node_id: "arrays",
          occurred_at: "2026-07-13T08:00:00Z",
        },
      });
    }

    if (method === "POST" && pathname === "/api/user/courses/switch") {
      const body = requestBody(request);
      state.courseActions.push({ type: "switch", body });
      state.activeCourseId = body.course_id || state.activeCourseId;
      return json(route, {
        active_course: state.activeCourseId,
        course: mockCourses.find((course) => course.course_id === state.activeCourseId),
      });
    }

    if (method === "POST" && pathname === "/api/user/courses/enroll") {
      const body = requestBody(request);
      state.courseActions.push({ type: "enroll", body });
      state.activeCourseId = body.course_id || state.activeCourseId;
      state.enrolledCourseIds.add(state.activeCourseId);
      return json(route, {
        active_course: state.activeCourseId,
        course: mockCourses.find((course) => course.course_id === state.activeCourseId),
      });
    }

    if (method === "GET" && /\/api\/sessions\/[^/]+\/assets$/.test(pathname)) {
      return json(route, { revision: state.assetRevision, assets: state.assets });
    }

    if (method === "PATCH" && /\/api\/sessions\/[^/]+\/assets$/.test(pathname)) {
      const body = requestBody(request);
      state.assetPatches.push(body);
      if (body.category && body.key && state.assets[body.category]) {
        if (body.delete) delete state.assets[body.category][body.key];
        else state.assets[body.category][body.key] = body.value;
      }
      state.assetRevision += 1;
      return json(route, { revision: state.assetRevision, assets: state.assets });
    }

    if (method === "GET" && /\/api\/sessions\/[^/]+\/events$/.test(pathname)) {
      return json(route, { events: state.learningEvents, mastery_attributions: [] });
    }

    if (method === "POST" && /\/api\/sessions\/[^/]+\/events$/.test(pathname)) {
      const body = requestBody(request);
      state.learningEventRequests.push(body);
      if (body.event_type === "answer_submitted" && state.failAnswerSubmitAttempts > 0) {
        state.failAnswerSubmitAttempts -= 1;
        return json(route, { detail: "答案暂时无法保存，请原位重试。" }, 503);
      }
      state.learningEvents.push(body);
      if (body.event_type === "answer_submitted" && body.result?.review_item_id) {
        const correct = body.result.answer_index === mockReviewItem.correct_answer_index;
        const practiceVerification = {
          verified: true,
          correct,
          reason: correct ? "verified_targeted_practice_correct" : "verified_targeted_practice_incorrect",
          review_item_id: body.result.review_item_id,
          resource_id: body.resource_id,
          question_id: body.question_id,
          selected_index: body.result.answer_index,
        };
        return json(route, {
          accepted: true,
          event_id: body.event_id,
          event: { ...body, practice_verification: practiceVerification },
          practice_verification: practiceVerification,
          knowledge_mastery: {},
        });
      }
      if (body.event_type === "lesson_completed" || body.event_type === "review_completed") {
        const answers = Array.isArray(body.result?.answers) ? body.result.answers : [];
        const questionResults = answers.map((answer, index) => ({
          question_id: answer.question_id,
          correct: index === 1,
          selected_option_index: answer.answer_index,
          correct_option_index: 0,
          explanation: index === 1
            ? "索引必须位于数组的有效边界内。"
            : "多数编程语言使用从 0 开始的数组索引。",
        }));
        const reviewItem = {
          review_item_id: "review-arrays-q1",
          source_event_id: body.event_id,
          source_resource_id: body.resource_id,
          review_kind: "diagnostic_quiz",
          node_id: "arrays",
          node_title: "数组基础",
          question_id: "arrays-q1",
          question_prompt: "数组的第一个索引通常是什么？",
          error_type: "concept_understanding",
          original_answer: "1",
          original_answer_index: 1,
          correct_answer: "0",
          correct_answer_index: 0,
          explanation: "多数编程语言使用从 0 开始的数组索引。",
          status: "due",
          phase: "material_review",
          attempt_count: 1,
          next_review_at: "2026-07-13T09:00:00Z",
          updated_at: "2026-07-13T08:30:00Z",
          recommended_materials: [],
        };
        state.reviewItems = [reviewItem];
        const verifiedEvidence = { question_results: questionResults };
        return json(route, {
          accepted: true,
          event_id: body.event_id,
          event: { ...body, verified_evidence: verifiedEvidence },
          verified_evidence: verifiedEvidence,
          effective_correctness: 0.5,
          evaluated_node_id: "arrays",
          mastery_before: 0.25,
          mastery_after: 0.35,
          mastery_threshold: 0.65,
          knowledge_mastery: { arrays: 0.35 },
          advanced_to_next_node: false,
          review: {
            requires_remediation: true,
            created_or_updated_items: [reviewItem],
            retested_items: [],
            remediation: { title: "复盘数组索引", steps: [] },
          },
        });
      }
      return json(route, {
        accepted: true,
        event_id: body.event_id,
        event: body,
        knowledge_mastery: {},
      });
    }

    if (method === "GET" && /\/api\/sessions\/[^/]+\/resources\/[^/]+$/.test(pathname)) {
      const nodeId = decodeURIComponent(pathname.split("/").at(-1));
      state.resourceRequests.push({
        nodeId,
        cardType: "",
        force: false,
      });
      return json(route, { status: "already_exists", resources: state.resourcesByNode[nodeId] || [] });
    }

    if (method === "POST" && /\/api\/sessions\/[^/]+\/resources\/[^/]+\/generation$/.test(pathname)) {
      const nodeId = decodeURIComponent(pathname.split("/").at(-2));
      const body = requestBody(request);
      const cardTypes = Array.isArray(body.card_types) ? body.card_types : [];
      const force = Boolean(body.force);
      state.resourceGenerationRequests.push({ nodeId, cardTypes, force, priority: body.priority || "" });
      cardTypes.forEach((cardType) => {
        state.resourceRequests.push({ nodeId, cardType, force });
      });
      if (cardTypes.length && state.failResourceGenerationAttempts > 0) {
        state.failResourceGenerationAttempts -= 1;
        return json(route, { detail: "资源服务暂时不可用，请原位重试。" }, 503);
      }
      if (cardTypes.includes("diagnostic_quiz") && state.failRetestResourceAttempts > 0) {
        state.failRetestResourceAttempts -= 1;
        return json(route, { detail: "复测题资源暂时不可用，请原位重试。" }, 503);
      }

      const existingResources = state.resourcesByNode[nodeId] || [];
      const generatedResources = [];
      if (options.generateResourceOnRequest && cardTypes.includes("concept_map")) {
        generatedResources.push(mockConceptResource);
      }
      if (options.withReviewItem && cardTypes.includes("diagnostic_quiz") && state.retestCreationCount > 0) {
        generatedResources.push(mockRetestQuizResource);
      }
      if (generatedResources.length) {
        const generatedTypes = new Set(generatedResources.map((resource) => resource.resource_type));
        state.resourcesByNode[nodeId] = [
          ...existingResources.filter((resource) => !generatedTypes.has(resource.resource_type)),
          ...generatedResources,
        ];
      }

      const jobId = `resource-job-${state.resourceGenerationRequests.length}`;
      state.resourceGenerationJobs.set(jobId, {
        nodeId,
        cardTypes,
        resources: generatedResources,
      });
      return json(route, {
        job_id: jobId,
        status: "queued",
        existing_resources: existingResources,
        missing_resources: cardTypes.filter((cardType) => !existingResources.some(
          (resource) => resource.resource_type === cardType,
        )),
      });
    }

    if (method === "GET" && /^\/api\/resource-generation-jobs\/[^/]+\/events$/.test(pathname)) {
      const jobId = decodeURIComponent(pathname.split("/").at(-2));
      const job = state.resourceGenerationJobs.get(jobId);
      if (!job) return json(route, { detail: "Generation job not found" }, 404);
      const events = [
        { id: `${jobId}-queued`, event: "queued", data: { job_id: jobId } },
        ...job.resources.map((resource, index) => ({
          id: `${jobId}-card-${index}`,
          event: "card_ready",
          data: {
            card_type: resource.resource_type,
            card: resource,
            progress: index + 1,
          },
        })),
        { id: `${jobId}-completed`, event: "completed", data: { job_id: jobId } },
      ];
      return sse(route, events);
    }

    if (method === "GET" && /\/api\/sessions\/[^/]+\/practice\/problems\/[^/]+$/.test(pathname)) {
      return json(route, { status: "ok", problem: mockPracticeProblem });
    }

    if (method === "POST" && /\/api\/sessions\/[^/]+\/practice\/(run|submit)$/.test(pathname)) {
      const mode = pathname.endsWith("/submit") ? "submit" : "run";
      const body = requestBody(request);
      state.practiceRequests[mode].push(body);
      const failureKey = mode === "submit" ? "failPracticeSubmitAttempts" : "failPracticeRunAttempts";
      if (state[failureKey] > 0) {
        state[failureKey] -= 1;
        return json(route, {
          status: "sandbox_unavailable",
          verdict: "sandbox_unavailable",
          mode,
          message: "隔离运行时暂时不可用，请原位重试。",
          resource_id: body.resource_id,
          problem_id: mockPracticeProblem.problem_id,
          problem_version: mockPracticeProblem.version,
        }, 503);
      }
      const hiddenTotal = mode === "submit" ? 1 : 0;
      return json(route, {
        status: "ok",
        mode,
        verdict: "accepted",
        submission_id: mode === "submit" ? "submission-e2e-1" : "",
        message: mode === "submit" ? "全部测试通过。" : "公开测试通过。",
        resource_id: body.resource_id,
        node_id: "arrays",
        problem_id: mockPracticeProblem.problem_id,
        problem_version: mockPracticeProblem.version,
        runtime_ms: 4.2,
        memory_kb: 768,
        summary: {
          passed: 1 + hiddenTotal,
          total: 1 + hiddenTotal,
          public_passed: 1,
          public_total: 1,
          hidden_passed: hiddenTotal,
          hidden_total: hiddenTotal,
        },
        tests: [{
          id: "public-1",
          name: "公开测试 1",
          passed: true,
          verdict: "accepted",
          visibility: "public",
          input: [[3, 5, 8]],
          expected: 3,
          actual: 3,
        }],
      });
    }

    if (method === "POST" && /\/api\/sessions\/[^/]+\/review\/items\/[^/]+\/start$/.test(pathname)) {
      const reviewItemId = decodeURIComponent(pathname.split("/").at(-2));
      state.reviewStartRequests.push({ reviewItemId });
      const reviewItem = state.reviewItems.find((item) => item.review_item_id === reviewItemId);
      if (!reviewItem) {
        return json(route, { status: "review_item_not_found", detail: "复习项目不存在。" }, 404);
      }
      Object.assign(reviewItem, { status: "in_progress", phase: "material_review" });
      return json(route, {
        status: "ok",
        review_item: reviewItem,
        learning_task: {
          node_id: reviewItem.node_id,
          phase: "material_review",
          focus_resource_type: "interactive_exercise",
        },
      });
    }

    if (method === "POST" && /\/api\/sessions\/[^/]+\/review\/items\/[^/]+\/prepare-retest$/.test(pathname)) {
      const reviewItemId = decodeURIComponent(pathname.split("/").at(-2));
      const body = requestBody(request);
      state.prepareRetestRequests.push({ reviewItemId, body });
      if (state.failPrepareRetestAttempts > 0) {
        state.failPrepareRetestAttempts -= 1;
        return json(route, { detail: "复测生成暂时不可用，请原位重试。" }, 503);
      }
      const practiceEventId = String(body.practice_event_id || "");
      if (!practiceEventId) {
        return json(route, { status: "targeted_practice_evidence_required", detail: "缺少定向练习凭据。" }, 409);
      }
      let result = state.retestResultsByPracticeEvent.get(practiceEventId);
      const idempotent = Boolean(result);
      if (!result) {
        state.retestCreationCount += 1;
        const reviewItem = state.reviewItems.find((item) => item.review_item_id === reviewItemId);
        if (reviewItem) Object.assign(reviewItem, { status: "in_progress", phase: "retest" });
        result = {
          status: "ok",
          review_item: reviewItem,
          learning_task: {
            node_id: reviewItem?.node_id || "arrays",
            phase: "retest",
            focus_resource_type: "diagnostic_quiz",
            retest_resource_id: mockRetestQuizResource.resource_id,
          },
        };
        state.retestResultsByPracticeEvent.set(practiceEventId, result);
      }
      return json(route, { ...result, idempotent });
    }

    if (method === "GET" && /\/api\/sessions\/[^/]+\/review$/.test(pathname)) {
      state.reviewDashboardRequests.push({ pathname });
      if (state.failReviewDashboardAttempts > 0) {
        state.failReviewDashboardAttempts -= 1;
        return json(route, { detail: "复习队列暂时不可用，请原位重试。" }, 503);
      }
      const hasReview = state.reviewItems.length > 0;
      return json(route, {
        status: "ok",
        today_queue: state.reviewItems,
        mistakes: state.reviewItems,
        weak_nodes: hasReview ? [{
          node_id: "arrays",
          node_title: "数组基础",
          mastery: 0.35,
          outstanding_count: 1,
          error_types: ["concept_understanding"],
        }] : [],
        mastery_trend: hasReview ? [{
          event_id: state.reviewItems[0].source_event_id,
          node_id: "arrays",
          node_title: "数组基础",
          mastery_before: 0.25,
          mastery_after: 0.35,
          mastery_delta: 0.1,
          recorded_at: "2026-07-13T08:30:00Z",
        }] : [],
        diagnostic_report: {
          latest: hasReview ? {
            node_id: "arrays",
            node_title: "数组基础",
            correctness: 0.5,
            correct_count: 1,
            question_count: 2,
            question_results: [],
          } : null,
          markdown: hasReview ? "一次真实诊断产生了 1 条复习任务。" : "",
        },
      });
    }

    if (method === "POST" && /\/api\/sessions\/[^/]+\/tutor$/.test(pathname)) {
      const body = requestBody(request);
      state.tutorRequests.push(body);
      if (state.disconnectTutorAttempts > 0) {
        state.disconnectTutorAttempts -= 1;
        return route.fulfill({
          status: 200,
          headers: {
            "content-type": "text/event-stream; charset=utf-8",
            "cache-control": "no-cache",
          },
          body: 'event: token\ndata: {"token":"回答尚未完成。"}\n\n',
        });
      }
      if (state.failTutorAttempts > 0) {
        state.failTutorAttempts -= 1;
        return json(route, { detail: "Tutor 暂时不可用，请原位重试。" }, 503);
      }
      return route.fulfill({
        status: 200,
        headers: {
          "content-type": "text/event-stream; charset=utf-8",
          "cache-control": "no-cache",
        },
        body: [
          'event: token\ndata: {"token":"已收到问题。"}',
          'event: done\ndata: {"status":"ok"}',
          "",
        ].join("\n\n"),
      });
    }

    if (method === "GET" && /\/api\/sessions\/[^/]+$/.test(pathname)) {
      return json(route, sessionState(courseIdFromSessionPath(pathname), state.resourcesByNode));
    }

    state.unhandledRequests.push({ method, pathname });
    return json(route, { detail: `Unhandled mock request: ${method} ${pathname}` }, 501);
  });

  return state;
}

export async function seedAuthenticatedUser(page, options = {}) {
  await page.addInitScript(() => {
    window.localStorage.setItem("access_token", "e2e-access-token");
    window.localStorage.setItem("refresh_token", "e2e-refresh-token");
  });
  return installMockApi(page, { ...options, authenticated: true });
}

export async function expectNoUnhandledApiRequests(state) {
  await expect.poll(() => state.unhandledRequests).toEqual([]);
}
