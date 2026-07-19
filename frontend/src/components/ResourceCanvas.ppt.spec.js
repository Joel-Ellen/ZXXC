import { flushPromises, shallowMount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pptMocks = vi.hoisted(() => ({
  buildNodePresentationModel: vi.fn(({ nodeTitle = "" } = {}) => ({
    title: nodeTitle,
    nodeId: "node-1",
    filename: "EduAgent-node.pptx",
    slides: [],
  })),
  createNodePptBlob: vi.fn(),
  downloadBlob: vi.fn(),
}));

vi.mock("../utils/pptGenerator.js", () => ({
  buildNodePresentationModel: pptMocks.buildNodePresentationModel,
  createNodePptBlob: pptMocks.createNodePptBlob,
  downloadBlob: pptMocks.downloadBlob,
}));

import ResourceCanvas from "./ResourceCanvas.vue";

const nodeOneCards = [{
  resource_id: "concept-node-1",
  resource_type: "concept_map",
  title: "节点一概念",
  structured_payload: { definition: "节点一内容" },
}];

const nodeTwoCards = [{
  resource_id: "concept-node-2",
  resource_type: "concept_map",
  title: "节点二概念",
  structured_payload: { definition: "节点二内容" },
}];

function mountCanvas(overrides = {}) {
  return shallowMount(ResourceCanvas, {
    props: {
      cards: nodeOneCards,
      currentNode: "node-1",
      nodeTitle: "节点一",
      pathNodes: [
        { id: "node-1", title: "节点一", mastery: 0 },
        { id: "node-2", title: "节点二", mastery: 0 },
      ],
      getCardLabel: (type) => type,
      getAgentLabel: () => "文档智能体",
      buildQuiz: () => [],
      ...overrides,
    },
  });
}

describe("ResourceCanvas PPT export", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    HTMLElement.prototype.scrollTo = vi.fn();
  });

  it("downloads the generated deck for the active node", async () => {
    const blob = new Blob(["pptx"]);
    pptMocks.createNodePptBlob.mockResolvedValue({
      blob,
      filename: "EduAgent-节点一.pptx",
      slideCount: 6,
      nodeId: "node-1",
    });
    const wrapper = mountCanvas();

    await wrapper.get('button[title="下载当前节点学习 PPT"]').trigger("click");
    await flushPromises();

    expect(pptMocks.createNodePptBlob).toHaveBeenCalledWith({
      nodeTitle: "节点一",
      nodeId: "node-1",
      cards: nodeOneCards,
    });
    expect(pptMocks.downloadBlob).toHaveBeenCalledWith(blob, "EduAgent-节点一.pptx");
    expect(wrapper.text()).toContain("已下载 6 页 PPT：EduAgent-节点一.pptx");
  });

  it("opens the in-workspace preview without downloading immediately", async () => {
    const wrapper = mountCanvas();

    await wrapper.get('button[title="在工作台预览当前节点学习 PPT"]').trigger("click");

    expect(wrapper.vm.showPptPreview).toBe(true);
    expect(pptMocks.createNodePptBlob).not.toHaveBeenCalled();
    expect(pptMocks.downloadBlob).not.toHaveBeenCalled();
  });

  it("does not download or report an obsolete deck after switching nodes", async () => {
    let resolveExport;
    pptMocks.createNodePptBlob.mockImplementation(() => new Promise((resolve) => {
      resolveExport = resolve;
    }));
    const wrapper = mountCanvas();

    await wrapper.get('button[title="下载当前节点学习 PPT"]').trigger("click");
    expect(wrapper.text()).toContain("正在整理当前节点的学习内容");

    await wrapper.setProps({
      currentNode: "node-2",
      nodeTitle: "节点二",
      cards: nodeTwoCards,
    });
    resolveExport({
      blob: new Blob(["old-pptx"]),
      filename: "EduAgent-节点一.pptx",
      slideCount: 6,
      nodeId: "node-1",
    });
    await flushPromises();

    expect(pptMocks.downloadBlob).not.toHaveBeenCalled();
    expect(wrapper.text()).not.toContain("EduAgent-节点一.pptx");
    expect(wrapper.text()).not.toContain("正在整理当前节点的学习内容");
  });

  it("renders legacy nested code payloads as C examples", () => {
    const wrapper = mountCanvas({
      filterType: "code",
      cards: [{
        resource_id: "code-node-1",
        resource_type: "code_snippet",
        metadata: {
          structured_payload: {
            language: "c",
            scenario: "遍历数组",
            code: "int total = 0;",
          },
        },
      }],
    });

    expect(wrapper.text()).toContain("C");
    expect(wrapper.text()).toContain("int total = 0;");
  });
});
