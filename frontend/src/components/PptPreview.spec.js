import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import PptPreview from "./PptPreview.vue";

const model = {
  title: "二叉树",
  slides: [
    {
      kind: "cover",
      title: "二叉树",
      subtitle: "节点学习课件",
      detail: "基于 5 份学习资料整理",
    },
    {
      kind: "content",
      kicker: "概念理解",
      title: "核心定义",
      lead: "每个节点最多有两个子节点。",
      bullets: ["理解节点与边的关系"],
    },
    {
      kind: "summary",
      title: "带走这三件事",
      bullets: ["说清定义", "检查边界"],
      detail: "回到工作台完成诊断。",
    },
  ],
};

let wrapper;

afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
});

describe("PptPreview", () => {
  it("shows the active slide and supports paging", async () => {
    wrapper = mount(PptPreview, {
      attachTo: document.body,
      props: { open: true, model },
    });

    expect(document.body.textContent).toContain("节点学习课件");
    expect(document.body.textContent).toContain("1 / 3");

    document.body.querySelector('button[aria-label="下一页"]').click();
    await wrapper.vm.$nextTick();

    expect(document.body.textContent).toContain("核心定义");
    expect(document.body.textContent).toContain("2 / 3");
  });

  it("emits download and close actions", async () => {
    wrapper = mount(PptPreview, {
      attachTo: document.body,
      props: { open: true, model },
    });

    document.body.querySelector('button[title="下载当前节点学习 PPT"]').click();
    document.body.querySelector('button[aria-label="关闭课件预览"]').click();
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted("download")).toHaveLength(1);
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("does not render the dialog when closed", () => {
    wrapper = mount(PptPreview, {
      attachTo: document.body,
      props: { open: false, model },
    });

    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  });
});
