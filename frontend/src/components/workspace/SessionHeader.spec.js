import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import SessionHeader from "./SessionHeader.vue";

const CourseSwitcherStub = {
  name: "CourseSwitcher",
  template: '<button type="button" class="course-switcher-stub">当前课程</button>',
};

function mountHeader(overrides = {}) {
  return mount(SessionHeader, {
    props: {
      activeCourse: { course_id: "course-a", title_cn: "数据结构" },
      enrolledCourses: [],
      nodeTitle: "数组基础",
      currentNode: "arrays",
      pathNodes: [{ id: "arrays", title: "数组基础", order: 1 }],
      overallProgress: 42,
      masteredCount: 0,
      ...overrides,
    },
    global: {
      stubs: { CourseSwitcher: CourseSwitcherStub },
    },
  });
}

describe("SessionHeader actions", () => {
  it("keeps navigation out of the header and exposes one action per responsive mode", async () => {
    const wrapper = mountHeader();

    expect(wrapper.find("details").exists()).toBe(false);
    expect(wrapper.find("nav").exists()).toBe(false);
    expect(wrapper.get(".session-header__progress strong").text()).toBe("42%");

    await wrapper.get(".session-header__primary").trigger("click");
    expect(wrapper.emitted("toggle-tutor")).toHaveLength(1);

    await wrapper.get(".session-header__mobile-primary").trigger("click");
    expect(wrapper.emitted("navigate")).toEqual([["learn"]]);
  });
});
