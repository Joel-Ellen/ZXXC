import { expect, test } from "@playwright/test";
import {
  expectNoUnhandledApiRequests,
  installMockApi,
  seedAuthenticatedUser,
} from "./fixtures/mockApi";

test.describe("in-place recovery for critical learning requests", () => {
  test("login keeps credentials and retries from the error without leaving the form", async ({ page }) => {
    const api = await installMockApi(page, { failLoginAttempts: 1 });
    await page.goto("/login?redirect=%2Fcourses");

    const userId = page.locator("#auth-user-id");
    const password = page.locator("#auth-password");
    const captcha = page.locator("#auth-captcha");
    await userId.fill("e2e_user");
    await password.fill("correct-password");
    await captcha.fill("8");
    await page.locator("form").getByRole("button", { name: "登录", exact: true }).click();

    const failure = page.getByRole("alert").filter({ hasText: "凭据错误" });
    await expect(failure).toBeVisible();
    await expect(page).toHaveURL(/\/login\?redirect=%2Fcourses$/);
    await expect(userId).toHaveValue("e2e_user");
    await expect(password).toHaveValue("correct-password");
    await expect(captcha).toHaveValue("");

    await captcha.fill("8");
    await failure.getByRole("button", { name: "重试", exact: true }).click();

    await expect(page).toHaveURL(/\/courses$/);
    await expect.poll(() => api.loginRequests.length).toBe(2);
    expect(api.loginRequests[1]).toMatchObject({
      user_id: api.loginRequests[0].user_id,
      password: api.loginRequests[0].password,
      captcha_answer: "8",
    });
    expect(api.loginRequests[1].captcha_token).not.toBe(api.loginRequests[0].captcha_token);
    await expectNoUnhandledApiRequests(api);
  });

  test("course catalog load failure stays on the page and reloads successfully", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, { failCourseCatalogAttempts: 1 });
    await page.goto("/courses");

    await expect(page.getByRole("heading", { name: "课程目录加载失败", exact: true })).toBeVisible();
    await expect(page.getByText("课程目录暂时不可用，请原位重试。", { exact: true })).toBeVisible();
    await expect(page).toHaveURL(/\/courses$/);
    const reload = page.getByRole("button", { name: "重新加载", exact: true });
    await expect(reload).toBeEnabled();

    await reload.click();

    await expect(page.getByRole("heading", { name: "数据结构入门", exact: true })).toBeVisible();
    await expect.poll(() => api.courseCatalogRequests.length).toBe(2);
    await expect(page).toHaveURL(/\/courses$/);
    await expectNoUnhandledApiRequests(api);
  });

  test("review queue load failure stays on /review and reloads the same dashboard", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, {
      withReviewItem: true,
      failReviewDashboardAttempts: 1,
    });
    await page.goto("/review");

    await expect(page.getByRole("heading", { name: "复习队列加载失败", exact: true })).toBeVisible();
    await expect(page.getByText("复习队列暂时不可用，请原位重试。", { exact: true })).toBeVisible();
    await expect(page).toHaveURL(/\/review$/);
    const reload = page.getByRole("button", { name: "重新加载", exact: true });
    await expect(reload).toBeEnabled();
    await expect.poll(() => api.reviewDashboardRequests.length).toBe(1);

    await reload.click();

    await expect(page.getByRole("heading", { name: "1 项需要处理", exact: true })).toBeVisible();
    await expect(page.getByText("数组的第一个索引通常是什么？", { exact: true }).first()).toBeVisible();
    await expect.poll(() => api.reviewDashboardRequests.length).toBe(2);
    await expect(page).toHaveURL(/\/review$/);
    await expectNoUnhandledApiRequests(api);
  });

  test("prepare-retest reuses verified practice evidence after a transient failure", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, {
      withReviewItem: true,
      failPrepareRetestAttempts: 1,
      failRetestResourceAttempts: 1,
    });
    await page.goto("/review");
    await expect(page.getByRole("heading", { name: "1 项需要处理", exact: true })).toBeVisible();

    await page.getByRole("button", { name: "开始补救", exact: true }).click();
    await expect(page).toHaveURL(/\/learn\/course-a\/arrays\?.*reviewItem=review-arrays-q1.*reviewPhase=material_review/);

    const practice = page.locator("fieldset").filter({ hasText: "定向练习题" });
    const correctAnswer = practice.getByRole("radio", { name: "0", exact: true });
    await expect(correctAnswer).toBeVisible();
    await correctAnswer.check();
    const submit = practice.getByRole("button", { name: "提交练习并生成复测", exact: true });
    await submit.click();

    const prepareFailure = page.getByRole("alert").filter({ hasText: "复测生成暂时不可用，请原位重试。" });
    await expect(prepareFailure).toHaveCount(1);
    await expect(correctAnswer).toBeChecked();
    await expect.poll(() => Object.values(api.assets.quiz_progress).some((progress) => (
      progress.review_item_id === "review-arrays-q1"
      && Boolean(progress.practice_event_id)
    ))).toBe(true);
    await expect.poll(() => api.prepareRetestRequests.length).toBe(1);
    const practiceEvents = () => api.learningEventRequests.filter((event) => (
      event.event_type === "answer_submitted"
      && event.result?.review_item_id === "review-arrays-q1"
    ));
    await expect.poll(() => practiceEvents().length).toBe(1);
    const practiceEventId = practiceEvents()[0].event_id;
    expect(api.prepareRetestRequests[0]).toMatchObject({
      reviewItemId: "review-arrays-q1",
      body: { practice_event_id: practiceEventId },
    });
    expect(api.retestCreationCount).toBe(0);

    await page.reload();

    await expect(page).toHaveURL(/\/learn\/course-a\/arrays\?.*reviewItem=review-arrays-q1.*reviewPhase=material_review/);
    await expect(prepareFailure).toHaveCount(1);
    await expect(correctAnswer).toBeChecked();
    const retry = practice.getByRole("button", { name: "重试生成复测", exact: true });
    await expect(retry).toBeEnabled();
    expect(practiceEvents()).toHaveLength(1);
    expect(api.prepareRetestRequests).toHaveLength(1);

    await retry.click();

    await expect(page).toHaveURL(/\/learn\/course-a\/arrays\?.*reviewItem=review-arrays-q1.*reviewPhase=retest/);
    const resourceFailure = page.getByRole("alert").filter({ hasText: "复测已创建，但复测题加载失败" });
    await expect(resourceFailure).toContainText("复测题资源暂时不可用，请原位重试。");
    await expect(resourceFailure.getByRole("button", { name: "重新加载复测", exact: true })).toBeEnabled();
    await expect.poll(() => api.prepareRetestRequests.length).toBe(2);
    expect(api.prepareRetestRequests[1]).toEqual(api.prepareRetestRequests[0]);
    expect(practiceEvents()).toHaveLength(1);
    expect(api.learningEvents.filter((event) => event.event_id === practiceEventId)).toHaveLength(1);
    expect(api.retestCreationCount).toBe(1);
    expect(api.retestResultsByPracticeEvent.size).toBe(1);
    await expect.poll(() => api.resourceRequests.filter((request) => request.cardType === "diagnostic_quiz").length).toBe(1);
    await expect(page).toHaveURL((url) => (
      url.searchParams.get("reviewItem") === "review-arrays-q1"
      && url.searchParams.get("reviewPhase") === "retest"
    ));

    await resourceFailure.getByRole("button", { name: "重新加载复测", exact: true }).click();

    await expect(page.locator('[data-resource-type="diagnostic_quiz"]')).toBeVisible();
    await expect(resourceFailure).toHaveCount(0);
    await expect.poll(() => api.resourceRequests.filter((request) => request.cardType === "diagnostic_quiz").length).toBe(2);
    expect(api.prepareRetestRequests).toHaveLength(2);
    expect(practiceEvents()).toHaveLength(1);
    await expect.poll(() => Object.values(api.assets.quiz_progress).some((progress) => (
      progress.review_item_id === "review-arrays-q1"
    ))).toBe(false);
    await expectNoUnhandledApiRequests(api);
  });

  test("resource generation keeps card_type and retries in the empty slot", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, {
      failResourceGenerationAttempts: 1,
      generateResourceOnRequest: true,
    });
    await page.goto("/learn/course-a/arrays");
    await expect(page.getByText("当前学习节点等待装配", { exact: true })).toBeVisible();
    await expect(page.locator(".session-header__notice")).toContainText("资源生成失败：资源服务暂时不可用，请原位重试。");
    await expect(page).toHaveURL(/\/learn\/course-a\/arrays$/);
    const generate = page.getByRole("button", { name: "重试生成", exact: true });
    await expect(generate).toBeEnabled();
    await expect.poll(() => api.resourceRequests.filter((request) => request.cardType === "concept_map").length).toBe(1);
    await generate.click();

    const conceptCard = page.locator('[data-resource-type="concept_map"]');
    await expect(conceptCard).toBeVisible();
    await expect(conceptCard.getByText("从零开始的索引把位置映射到数组元素。", { exact: true }).first()).toBeVisible();
    await expect.poll(() => api.resourceRequests.filter((request) => request.cardType === "concept_map").length).toBe(2);
    const generationRequests = api.resourceRequests.filter((request) => request.cardType === "concept_map");
    expect(generationRequests).toEqual([
      { nodeId: "arrays", cardType: "concept_map", force: false },
      { nodeId: "arrays", cardType: "concept_map", force: false },
    ]);
    await expectNoUnhandledApiRequests(api);
  });

  test("Tutor keeps the complete draft and retries the same request after an interrupted stream", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, { disconnectTutorAttempts: 1 });
    await page.goto("/learn/course-a/arrays?view=coach");
    await expect(page.getByRole("heading", { name: "数组基础", exact: true })).toBeVisible();

    await page.getByRole("button", { name: "代码调试", exact: true }).click();
    const codeInput = page.getByPlaceholder("粘贴需要调试的代码...");
    const errorInput = page.getByPlaceholder("粘贴报错信息...");
    const questionInput = page.locator("#chat-input");
    await codeInput.fill("print(1 / 0)");
    await errorInput.fill("ZeroDivisionError");
    await questionInput.fill("为什么会失败？");
    await questionInput.press("Enter");

    await expect(page.getByText("回答尚未完成。", { exact: true })).toBeVisible();
    const failure = page.getByRole("alert").filter({ hasText: "辅导连接意外结束" });
    await expect(failure).toBeVisible();
    await expect(codeInput).toHaveValue("print(1 / 0)");
    await expect(errorInput).toHaveValue("ZeroDivisionError");
    await expect(questionInput).toHaveValue("为什么会失败？");
    const retry = failure.getByRole("button", { name: "重新发送", exact: true });
    await expect(retry).toBeEnabled();
    await expect.poll(() => api.tutorRequests.length).toBe(1);

    await retry.click();

    await expect(page.getByText("已收到问题。", { exact: true })).toBeVisible();
    await expect.poll(() => api.tutorRequests.length).toBe(2);
    expect(api.tutorRequests[1]).toEqual(api.tutorRequests[0]);
    expect(api.tutorRequests[1]).toMatchObject({
      question: "为什么会失败？",
      context_type: "code_debug",
      code_snippet: "print(1 / 0)",
      error_message: "ZeroDivisionError",
      stream: true,
    });
    await expectNoUnhandledApiRequests(api);
  });

  test("code runner preserves the CodeMirror draft and succeeds when run again", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, {
      withCodePractice: true,
      failPracticeRunAttempts: 1,
    });
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "数组基础", exact: true })).toBeVisible();
    await page.locator(".resource-canvas__filter").filter({ hasText: "代码" }).click();

    const panel = page.getByRole("region", { name: "代码练习" });
    await expect(panel.getByText("读取数组首项", { exact: true })).toBeVisible();
    const editor = panel.locator(".cm-content");
    const code = "int first_value(const int *values, size_t count) {\n    return count > 0 ? values[0] : 0;\n}";
    await expect(editor).toBeVisible();
    await editor.fill(code);

    const run = panel.getByRole("button", { name: "运行公开测试", exact: true });
    await run.click();

    await expect(panel.getByText("隔离运行时不可用", { exact: true })).toBeVisible();
    await expect(panel.getByText("隔离运行时暂时不可用，请原位重试。", { exact: true })).toBeVisible();
    await expect(editor).toContainText("return count > 0 ? values[0] : 0;");
    await expect(run).toBeEnabled();
    await expect.poll(() => api.practiceRequests.run.length).toBe(1);
    expect(api.practiceRequests.run[0]).toMatchObject({
      resource_id: "code-arrays-v1",
      language: "c",
      code,
    });

    await run.click();

    await expect(panel.locator(".code-practice-panel__verdict")).toHaveText("通过");
    await expect(panel.getByText("公开测试通过。", { exact: true })).toBeVisible();
    await expect.poll(() => api.practiceRequests.run.length).toBe(2);
    expect(api.practiceRequests.run[1]).toEqual(api.practiceRequests.run[0]);
    await expect(editor).toContainText("return count > 0 ? values[0] : 0;");
    await expectNoUnhandledApiRequests(api);
  });

  test("per-question submission keeps the selected answer and retries idempotently", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, {
      withQuiz: true,
      // Learning events retry one transient 5xx before surfacing the error.
      failAnswerSubmitAttempts: 2,
    });
    await page.goto("/learn/course-a/arrays");

    const question = page
      .getByText("数组的第一个索引通常是什么？", { exact: true })
      .locator("..");
    await question.getByRole("button", { name: "1", exact: true }).click();
    const submit = question.getByRole("button", { name: "Submit answer", exact: true });
    await submit.click();

    await expect(question.getByRole("alert")).toContainText("答案暂时无法保存，请原位重试。");
    await expect(submit).toBeEnabled();
    await expect.poll(() => (
      api.learningEventRequests.filter((event) => event.event_type === "answer_submitted").length
    )).toBe(2);
    expect(api.learningEvents.filter((event) => event.event_type === "answer_submitted")).toHaveLength(0);

    await submit.click();

    await expect(question.getByText("Answer saved", { exact: true })).toBeVisible();
    await expect.poll(() => (
      api.learningEventRequests.filter((event) => event.event_type === "answer_submitted").length
    )).toBe(3);
    const attempts = api.learningEventRequests.filter((event) => event.event_type === "answer_submitted");
    expect(attempts[1]).toEqual(attempts[0]);
    expect(attempts[2]).toEqual(attempts[0]);
    expect(attempts[2]).toMatchObject({
      event_id: attempts[0].event_id,
      question_id: "arrays-q1",
      result: { answer_index: 1 },
    });
    expect(api.learningEvents.filter((event) => event.event_type === "answer_submitted")).toHaveLength(1);
    await expectNoUnhandledApiRequests(api);
  });
});
