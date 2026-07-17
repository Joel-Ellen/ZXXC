import { expect, test } from "@playwright/test";
import {
  expectNoUnhandledApiRequests,
  installMockApi,
  seedAuthenticatedUser,
} from "./fixtures/mockApi";

test.describe("authenticated routing and truthful requests", () => {
  test("unauthenticated deep links are guarded without losing route state", async ({ page }) => {
    const api = await installMockApi(page);

    await page.goto("/learn/course-a/arrays?view=coach");

    await expect(page).toHaveURL(/\/login\?/);
    const currentUrl = new URL(page.url());
    expect(currentUrl.searchParams.get("redirect")).toBe("/learn/course-a/arrays?view=coach");
    await expect(page.locator("#auth-user-id")).toBeVisible();
    await expectNoUnhandledApiRequests(api);
  });

  test("login failures stay in the form and a later success restores the deep link", async ({ page }) => {
    const api = await installMockApi(page, { failLoginAttempts: 1 });
    await page.goto("/login?redirect=%2Flearn%2Fcourse-a%2Farrays%3Fview%3Dcoach");

    await page.locator("#auth-user-id").fill("e2e_user");
    await page.locator("#auth-password").fill("correct-password");
    await page.locator("#auth-captcha").fill("8");
    await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();

    await expect(page.getByRole("alert")).toContainText("凭据错误");
    await expect(page).toHaveURL(/\/login\?/);
    await expect(page.locator("#auth-user-id")).toHaveValue("e2e_user");

    await page.locator("#auth-captcha").fill("8");
    await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();

    await expect(page).toHaveURL(/\/learn\/course-a\/arrays\?view=coach$/);
    await expect(page.getByRole("heading", { name: "数组基础", exact: true })).toBeVisible();
    expect(api.loginRequests).toHaveLength(2);
    await expectNoUnhandledApiRequests(api);
  });

  test("unsafe post-login redirects cannot leave the application origin", async ({ page }) => {
    const api = await installMockApi(page);
    await page.goto("/login?redirect=%2F%2Fevil.example%2Fsteal");

    await page.locator("#auth-user-id").fill("e2e_user");
    await page.locator("#auth-password").fill("correct-password");
    await page.locator("#auth-captcha").fill("8");
    await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();

    await expect(page).toHaveURL(/\/app$/);
    expect(new URL(page.url()).origin).toBe(new URL(test.info().project.use.baseURL).origin);
    await expect(page.getByRole("heading", { name: "继续 数据结构入门" })).toBeVisible();
    await expectNoUnhandledApiRequests(api);
  });

  test("course center and browser history restore the selected learning node", async ({ page }) => {
    const api = await seedAuthenticatedUser(page);
    await page.goto("/app");

    await expect(page.getByRole("heading", { name: "继续 数据结构入门" })).toBeVisible();
    await page.getByRole("button", { name: "浏览课程", exact: true }).click();
    await expect(page).toHaveURL(/\/courses$/);
    await expect(page.getByRole("heading", { name: "课程中心", exact: true })).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL(/\/app$/);
    await page.getByRole("button", { name: "继续学习", exact: true }).first().click();
    await expect(page).toHaveURL(/\/learn\/course-a\/arrays$/);
    await expect(page.getByRole("heading", { name: "数组基础", exact: true })).toBeVisible();

    await page.locator(".course-path-panel__node", { hasText: "栈与队列" }).click();
    await expect(page).toHaveURL(/\/learn\/course-a\/stacks$/);
    await expect(page.getByRole("heading", { name: "栈与队列", exact: true })).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL(/\/learn\/course-a\/arrays$/);
    await expect(page.getByRole("heading", { name: "数组基础", exact: true })).toBeVisible();

    await page.goForward();
    await expect(page).toHaveURL(/\/learn\/course-a\/stacks$/);
    await expect(page.getByRole("heading", { name: "栈与队列", exact: true })).toBeVisible();

    await page.reload();
    await expect(page).toHaveURL(/\/learn\/course-a\/stacks$/);
    await expect(page.getByRole("heading", { name: "栈与队列", exact: true })).toBeVisible();
    await expect.poll(() => api.clientEvents).toContainEqual(expect.objectContaining({
      event: "refresh_recovery",
      surface: "learn",
      outcome: "success",
    }));
    await expectNoUnhandledApiRequests(api);
  });

  test("joining a catalog course changes server state before learning starts", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, { enrolledCourseIds: ["course-a"] });
    await page.goto("/courses");
    await expect(page.getByRole("heading", { name: "课程中心", exact: true })).toBeVisible();

    const pythonCourse = page.locator("article.course-card", { hasText: "Python 基础" });
    await expect(pythonCourse.getByRole("button", { name: "加入课程", exact: true })).toBeVisible();
    await pythonCourse.getByRole("button", { name: "加入课程", exact: true }).click();
    await expect(pythonCourse.getByRole("group", { name: "确认加入课程" })).toBeVisible();
    await pythonCourse.getByRole("button", { name: "确认", exact: true }).click();

    await expect.poll(() => api.courseActions).toContainEqual({
      type: "enroll",
      body: { course_id: "course-b" },
    });
    await expect(page).toHaveURL(/\/learn\/course-b\/syntax$/);
    await expect(page.locator(".session-header__node h1")).toHaveText("语法基础");
    await expectNoUnhandledApiRequests(api);
  });

  test("per-question answers produce a completion event and a review queue", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, { withQuiz: true });
    await page.goto("/learn/course-a/arrays");
    await expect(page.getByText("数组的第一个索引通常是什么？", { exact: true })).toBeVisible();

    const firstQuestion = page.getByText("数组的第一个索引通常是什么？", { exact: true }).locator("..");
    await firstQuestion.getByRole("button", { name: "1", exact: true }).click();
    await firstQuestion.getByRole("button", { name: "Submit answer", exact: true }).click();
    await expect(firstQuestion.getByText("Answer saved", { exact: true })).toBeVisible();

    const secondQuestion = page.getByText("访问数组元素前最需要检查什么？", { exact: true }).locator("..");
    await secondQuestion.getByRole("button", { name: "边界范围", exact: true }).click();
    await secondQuestion.getByRole("button", { name: "Submit answer", exact: true }).click();
    await expect(secondQuestion.getByText("Answer saved", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "提交诊断", exact: true }).click();
    await expect(page.getByRole("button", { name: "诊断已提交", exact: true })).toBeDisabled();

    await expect.poll(() => api.learningEvents.filter((event) => event.event_type === "answer_submitted").length).toBe(2);
    const completion = api.learningEvents.find((event) => event.event_type === "lesson_completed");
    expect(completion).toMatchObject({
      user_id: "e2e_user",
      course_id: "course-a",
      node_id: "arrays",
      resource_id: "quiz-arrays-v1",
      question_id: "",
      attempt_number: 1,
      used_hint: false,
      result: {
        evidence_type: "diagnostic_quiz",
        answers: [
          { question_id: "arrays-q1", answer_index: 1 },
          { question_id: "arrays-q2", answer_index: 0 },
        ],
      },
    });

    await page.goto("/review");
    await expect(page).toHaveURL(/\/review$/);
    await expect(page.getByRole("heading", { name: "1 项需要处理", exact: true })).toBeVisible();
    await expect(page.getByText("数组的第一个索引通常是什么？", { exact: true }).first()).toBeVisible();
    await expectNoUnhandledApiRequests(api);
  });

  test("Tutor sends the selected context, code, error, and auditable event", async ({ page }) => {
    const api = await seedAuthenticatedUser(page);
    await page.goto("/learn/course-a/arrays?view=coach");
    await expect(page.getByRole("heading", { name: "数组基础", exact: true })).toBeVisible();

    await page.getByRole("button", { name: "代码调试", exact: true }).click();
    await page.getByPlaceholder("粘贴需要调试的代码...").fill("print(1 / 0)");
    await page.getByPlaceholder("粘贴报错信息...").fill("ZeroDivisionError");
    await page.locator("#chat-input").fill("为什么会失败？");
    await page.locator("#chat-input").press("Enter");

    await expect.poll(() => api.tutorRequests.length).toBe(1);
    expect(api.tutorRequests[0]).toMatchObject({
      question: "为什么会失败？",
      context_type: "code_debug",
      code_snippet: "print(1 / 0)",
      error_message: "ZeroDivisionError",
      stream: true,
    });

    await expect.poll(() => api.learningEvents.some((event) => event.event_type === "tutor_question")).toBe(true);
    const tutorEvent = api.learningEvents.find((event) => event.event_type === "tutor_question");
    expect(tutorEvent).toMatchObject({
      user_id: "e2e_user",
      course_id: "course-a",
      node_id: "arrays",
      attempt_number: 1,
      used_hint: false,
      result: {
        context_type: "code_debug",
        has_code_snippet: true,
        has_error_message: true,
      },
    });
    await expect(page.getByText("已收到问题。", { exact: true })).toBeVisible();
    await expectNoUnhandledApiRequests(api);
  });
});
