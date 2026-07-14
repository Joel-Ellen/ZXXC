import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import {
  expectNoUnhandledApiRequests,
  installMockApi,
  seedAuthenticatedUser,
} from "./fixtures/mockApi";

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

async function expectNoSeriousOrCriticalViolations(page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const blocking = results.violations
    .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
    .map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      targets: violation.nodes.map((node) => node.target.join(" ")),
    }));
  expect(blocking).toEqual([]);
}

async function expectNoRootOverflow(page) {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    root: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(dimensions.root, JSON.stringify(dimensions)).toBeLessThanOrEqual(dimensions.viewport + 1);
  expect(dimensions.body, JSON.stringify(dimensions)).toBeLessThanOrEqual(dimensions.viewport + 1);
}

test.describe("automated accessibility quality gates", () => {
  test("login has no serious or critical axe violations", async ({ page }) => {
    const api = await installMockApi(page);
    await page.goto("/login");
    await expect(page.locator("#auth-user-id")).toBeVisible();
    await expectNoSeriousOrCriticalViolations(page);
    await expectNoUnhandledApiRequests(api);
  });

  test("learning workspace has no serious or critical axe violations", async ({ page }) => {
    const api = await seedAuthenticatedUser(page);
    await page.goto("/learn/course-a/arrays");
    await expect(page.getByRole("heading", { name: "数组基础", exact: true })).toBeVisible();
    await expectNoSeriousOrCriticalViolations(page);
    await expectNoUnhandledApiRequests(api);
  });

  test("visible mobile controls meet the 44px target and layouts do not overflow", async ({ page }) => {
    const api = await seedAuthenticatedUser(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/learn/course-a/arrays");
    await expect(page.getByRole("heading", { name: "数组基础", exact: true })).toBeVisible();

    const undersized = await page.locator(interactiveSelector).evaluateAll((elements) => elements.flatMap((element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      const hidden = style.display === "none"
        || style.visibility === "hidden"
        || Number(style.opacity) === 0
        || rect.width === 0
        || rect.height === 0
        || element.closest("[aria-hidden='true']");
      if (hidden) return [];
      if (rect.width >= 43.5 && rect.height >= 43.5) return [];
      return [{
        tag: element.tagName.toLowerCase(),
        name: element.getAttribute("aria-label") || element.textContent?.trim().slice(0, 60) || element.id,
        width: Math.round(rect.width * 10) / 10,
        height: Math.round(rect.height * 10) / 10,
      }];
    }));
    expect(undersized).toEqual([]);
    await expectNoRootOverflow(page);

    await page.setViewportSize({ width: 720, height: 450 });
    await expectNoRootOverflow(page);
    await expectNoUnhandledApiRequests(api);
  });

  test("keyboard navigation exposes a visible focus indicator", async ({ page }) => {
    const api = await seedAuthenticatedUser(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/courses");
    await expect(page.getByRole("heading", { name: "课程中心", exact: true })).toBeVisible();

    const focused = [];
    for (let index = 0; index < 6; index += 1) {
      await page.keyboard.press("Tab");
      focused.push(await page.evaluate(() => {
        const element = document.activeElement;
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        const hasIndicator = (
          style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) > 0
        ) || style.boxShadow !== "none";
        return {
          tag: element.tagName.toLowerCase(),
          label: element.getAttribute("aria-label") || element.textContent?.trim().slice(0, 60) || element.id,
          visible: rect.width > 0 && rect.height > 0,
          hasIndicator,
        };
      }));
    }

    expect(focused.filter((item) => item.visible).length).toBeGreaterThanOrEqual(4);
    expect(focused.filter((item) => item.visible && !item.hasIndicator)).toEqual([]);
    await expectNoUnhandledApiRequests(api);
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
