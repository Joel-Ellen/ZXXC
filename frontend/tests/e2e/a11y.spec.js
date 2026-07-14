import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import {
  expectNoUnhandledApiRequests,
  installMockApi,
  seedAuthenticatedUser,
} from "./fixtures/mockApi";

const wcagTags = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];

const formalRoutes = [
  { path: "/app", heading: "继续 数据结构入门" },
  { path: "/courses", heading: "课程中心" },
  { path: "/courses/course-a", heading: "数据结构入门" },
  { path: "/learn/course-a/arrays", heading: "数组基础" },
  { path: "/review", heading: "没有到期复习" },
  { path: "/progress", heading: "数据结构入门" },
  { path: "/account", selector: "#account-display-name" },
  { path: "/settings", heading: "阅读与显示偏好" },
];

const interactiveSelector = [
  "a[href]",
  "button",
  "input:not([type='hidden'])",
  "select",
  "textarea",
  "summary",
  "[role='button']",
  "[role='tab']",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

async function expectRouteReady(page, route) {
  await page.goto(route.path);
  if (route.selector) {
    await expect(page.locator(route.selector)).toBeVisible();
  } else {
    await expect(page.getByRole("heading", { name: route.heading, exact: true }).first()).toBeVisible();
  }
  await expect(page.locator('[role="status"][aria-atomic="true"]')).toHaveCount(0);
}

async function expectNoWcagViolations(page, context) {
  const results = await new AxeBuilder({ page }).withTags(wcagTags).analyze();
  const blocking = results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    nodes: violation.nodes.map((node) => ({
      target: node.target.join(" "),
      html: node.html,
      failureSummary: node.failureSummary,
    })),
  }));
  expect(blocking, `${context} must have no WCAG A/AA violations`).toEqual([]);
}

async function expectNoRootOverflow(page, context = "page") {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    root: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(dimensions.root, `${context}: ${JSON.stringify(dimensions)}`).toBeLessThanOrEqual(dimensions.viewport + 1);
  expect(dimensions.body, `${context}: ${JSON.stringify(dimensions)}`).toBeLessThanOrEqual(dimensions.viewport + 1);
}

async function expectTouchTargets(page, context) {
  const undersized = await page.locator(interactiveSelector).evaluateAll((elements) => elements.flatMap((element) => {
    const style = window.getComputedStyle(element);
    const elementRect = element.getBoundingClientRect();
    const hidden = style.display === "none"
      || style.visibility === "hidden"
      || Number(style.opacity) === 0
      || elementRect.width === 0
      || elementRect.height === 0
      || element.closest("[hidden], [aria-hidden='true']");
    if (hidden) return [];

    const label = element.closest("label");
    const target = label || element;
    const rect = target.getBoundingClientRect();
    if (rect.width >= 43.5 && rect.height >= 43.5) return [];
    return [{
      tag: element.tagName.toLowerCase(),
      name: element.getAttribute("aria-label") || element.textContent?.trim().slice(0, 60) || element.id,
      target: label ? "label" : "self",
      width: Math.round(rect.width * 10) / 10,
      height: Math.round(rect.height * 10) / 10,
    }];
  }));
  expect(undersized, `${context} has touch targets smaller than 44px`).toEqual([]);
}

async function expectFocusIndicator(locator, context) {
  await locator.focus();
  const result = await locator.evaluate((element) => {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return {
      focused: document.activeElement === element,
      visible: rect.width > 0 && rect.height > 0,
      hasIndicator: (
        style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) > 0
      ) || style.boxShadow !== "none",
    };
  });
  expect(result, context).toEqual({ focused: true, visible: true, hasIndicator: true });
}

test.describe("automated accessibility quality gates", () => {
  test("login passes WCAG A/AA and mobile touch-target checks", async ({ page }) => {
    const api = await installMockApi(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/login");
    await expect(page.locator("#auth-user-id")).toBeVisible();
    await expectNoWcagViolations(page, "/login");
    await expectTouchTargets(page, "/login");
    await expectNoRootOverflow(page, "/login");
    await expectNoUnhandledApiRequests(api);
  });

  test("every authenticated route passes all WCAG A/AA rules", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, { withQuiz: true });
    await page.setViewportSize({ width: 1280, height: 900 });

    for (const route of formalRoutes) {
      await expectRouteReady(page, route);
      await expectNoWcagViolations(page, route.path);
    }

    await expectNoUnhandledApiRequests(api);
  });

  test("every authenticated route has 44px mobile targets and no horizontal overflow", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, { withQuiz: true });
    await page.setViewportSize({ width: 390, height: 844 });

    for (const route of formalRoutes) {
      await expectRouteReady(page, route);
      await expectTouchTargets(page, route.path);
      await expectNoRootOverflow(page, route.path);
    }

    await expectNoUnhandledApiRequests(api);
  });

  test("keyboard users can filter a course and submit a quiz answer", async ({ page }) => {
    const api = await seedAuthenticatedUser(page, { withQuiz: true });
    await page.goto("/courses");
    await expect(page.getByRole("heading", { name: "课程中心", exact: true })).toBeVisible();

    const search = page.getByRole("searchbox", { name: "搜索课程" });
    await expectFocusIndicator(search, "course search focus");
    await page.keyboard.type("Python");
    const pythonCourse = page.locator("article.course-card", { hasText: "Python 基础" });
    await expect(pythonCourse).toBeVisible();

    const detail = pythonCourse.getByRole("button", { name: "查看详情", exact: true });
    await expectFocusIndicator(detail, "course detail action focus");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/courses\/course-b$/);
    await expect(page.getByRole("heading", { name: "Python 基础", exact: true })).toBeVisible();

    await page.goto("/learn/course-a/arrays");
    const firstQuestion = page.getByText("数组的第一个索引通常是什么？", { exact: true }).locator("..");
    const answer = firstQuestion.getByRole("button", { name: "1", exact: true });
    await expectFocusIndicator(answer, "quiz answer focus");
    await page.keyboard.press("Enter");
    const submit = firstQuestion.getByRole("button", { name: "Submit answer", exact: true });
    await expectFocusIndicator(submit, "quiz submit focus");
    await page.keyboard.press("Enter");
    await expect(firstQuestion.getByText("Answer saved", { exact: true })).toBeVisible();
    await expectNoUnhandledApiRequests(api);
  });

  test("dense routes reflow on a 1280px display at 200% browser scale", async ({ browser }) => {
    const context = await browser.newContext({
      baseURL: test.info().project.use.baseURL,
      viewport: { width: 640, height: 900 },
      deviceScaleFactor: 2,
    });
    const page = await context.newPage();
    const api = await seedAuthenticatedUser(page, { withQuiz: true });
    const zoomRoutes = [
      { path: "/learn/course-a/arrays", heading: "数组基础", screenshot: "step9-zoom-200-learning.png" },
      { path: "/account", selector: "#account-display-name", screenshot: "step9-zoom-200-account.png" },
    ];

    try {
      const scale = await page.evaluate(() => ({
        cssViewportWidth: window.innerWidth,
        devicePixelRatio: window.devicePixelRatio,
      }));
      expect(scale).toEqual({ cssViewportWidth: 640, devicePixelRatio: 2 });

      for (const route of zoomRoutes) {
        await expectRouteReady(page, route);
        await expectNoRootOverflow(page, `${route.path} at 200%`);
        await page.screenshot({ path: `../output/playwright/${route.screenshot}`, fullPage: true });
      }

      await expectNoUnhandledApiRequests(api);
    } finally {
      await context.close();
    }
  });

  test("prefers-reduced-motion removes long and repeating motion", async ({ page }) => {
    const api = await seedAuthenticatedUser(page);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/learn/course-a/arrays");
    await expect(page.getByRole("heading", { name: "数组基础", exact: true })).toBeVisible();

    expect(await page.evaluate(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
    const motionOffenders = await page.locator("body *").evaluateAll((elements) => {
      const seconds = (list) => list.split(",").map((value) => {
        const normalized = value.trim();
        return normalized.endsWith("ms")
          ? Number.parseFloat(normalized) / 1000
          : Number.parseFloat(normalized) || 0;
      });

      return elements.flatMap((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        if (!rect.width || !rect.height || style.visibility === "hidden" || style.display === "none") return [];
        const longAnimation = Math.max(...seconds(style.animationDuration)) > 0.05;
        const repeatingAnimation = style.animationName !== "none"
          && style.animationIterationCount.split(",").some((value) => value.trim() === "infinite");
        const longTransition = Math.max(...seconds(style.transitionDuration)) > 0.05;
        if (!longAnimation && !repeatingAnimation && !longTransition) return [];
        return [{
          tag: element.tagName.toLowerCase(),
          className: String(element.className).slice(0, 100),
          animation: `${style.animationName} ${style.animationDuration} ${style.animationIterationCount}`,
          transition: style.transitionDuration,
        }];
      });
    });
    expect(motionOffenders).toEqual([]);
    await expectNoUnhandledApiRequests(api);
  });
});
