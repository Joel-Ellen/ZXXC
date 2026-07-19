import { describe, expect, it } from "vitest";
import {
  MIME_TYPE,
  buildNodePresentationModel,
  createNodePptBlob,
} from "./pptGenerator.js";

const cards = [
  {
    resource_id: "concept-1",
    resource_type: "concept_map",
    title: "二叉树核心概念",
    structured_payload: {
      definition: "二叉树中每个节点最多有两个子节点。",
      summary: "二叉树的结构约束决定了遍历与递归分解方式。",
      learning_objectives: ["理解节点与边的关系", "区分满二叉树和完全二叉树"],
      bullets: ["每个节点的子节点数量不超过两个。"],
      constraints: ["根节点可以没有子节点。"],
      mechanism: ["从根节点向左右子树递归展开"],
      common_misconceptions: ["二叉树不要求每个节点都有两个子节点"],
      counterexamples: ["链式结构也是一种退化的二叉树。"],
      transfer_questions: ["如何用二叉树表示表达式？"],
      review_prompts: ["先说出节点的子树边界，再选择遍历方式。"],
    },
  },
  {
    resource_id: "code-1",
    resource_type: "code_snippet",
    title: "前序遍历",
    structured_payload: {
      language: "c",
      scenario: "用递归访问根、左子树和右子树。",
      code: "typedef struct Node {\n    int value;\n    struct Node *left;\n    struct Node *right;\n} Node;\n\nvoid preorder(const Node *node) {\n    if (node == NULL) return;\n    printf(\"%d \", node->value);\n    preorder(node->left);\n    preorder(node->right);\n}",
      walkthrough_steps: ["先处理空节点", "访问根节点", "递归访问左右子树"],
      complexity_notes: ["时间复杂度 O(n)"],
      explanation: "递归调用会把同一规则应用到左右子树。",
      boundary_tests: [{ name: "空树", input: "None", expected: "[]" }],
      pitfalls: ["忘记处理空节点。"],
      experiments: ["改为后序遍历并比较访问顺序。"],
    },
  },
  {
    resource_id: "exercise-1",
    resource_type: "interactive_exercise",
    title: "遍历练习",
    structured_payload: {
      goal: "能够根据访问顺序判断遍历类型。",
      error_signature: "把根节点访问时机和子树顺序混淆。",
      prompt: "给定一棵二叉树，写出它的前序遍历结果。",
      steps: ["标记根节点", "递归记录左子树", "递归记录右子树"],
      checkpoints: ["是否先访问根节点？"],
      hints: ["先画出访问轨迹。"],
      expected_outcome: "能解释每个输出值对应的访问时机。",
      solution_outline: "按根、左、右的顺序逐层展开。",
      rubric: [{ criterion: "访问顺序正确", points: 4, evidence: "输出与轨迹一致" }],
      structured_checkpoints: [{ id: "cp-1", prompt: "当前访问的是哪一层？", expected_signal: "能指出根或子树" }],
    },
  },
  {
    resource_id: "video-1",
    resource_type: "video_summary",
    title: "遍历视频回顾",
    structured_payload: {
      summary: "通过树形结构演示三种遍历。",
      key_points: ["前序遍历先访问根节点。"],
      timeline: [{ label: "00:30", summary: "画出根节点和左右子树。" }],
      watch_focus: ["观察递归返回时机。"],
      review_questions: ["为什么中序遍历适合搜索树？"],
      reading_sequence: ["先看定义，再对照代码。"],
      duration_minutes: 8,
    },
  },
  {
    resource_id: "quiz-1",
    resource_type: "diagnostic_quiz",
    title: "节点自测",
    body_markdown: "旧正文答案解析：根节点。",
    structured_payload: {
      questions: [
        {
          id: "q-1",
          level: "concept",
          prompt: "前序遍历首先访问哪个节点？",
          options: ["根节点", "最左叶子", "最右叶子", "最后入栈节点"],
          answer_index: 0,
          explanation: "正确答案是根节点。",
          skill_tag: "二叉树遍历",
        },
      ],
      after_quiz_guidance: "完成后回顾遍历顺序。",
    },
  },
];

describe("node PPT generator", () => {
  it("builds a teaching sequence from the current node cards", () => {
    const model = buildNodePresentationModel({
      nodeTitle: "二叉树",
      nodeId: "binary-tree",
      cards,
    });

    expect(model.filename).toBe("EduAgent-二叉树.pptx");
    expect(model.slides[0]).toMatchObject({ kind: "cover", title: "二叉树" });
    expect(model.slides.some((slide) => slide.kind === "agenda")).toBe(true);
    expect(model.slides.some((slide) => slide.kind === "code")).toBe(true);
    expect(model.slides.find((slide) => slide.kind === "code")?.language).toBe("c");
    expect(model.slides.at(-1)?.kind).toBe("summary");

    const publicDeckText = JSON.stringify(model.slides);
    expect(publicDeckText).toContain("前序遍历首先访问哪个节点");
    expect(publicDeckText).toContain("A. 根节点");
    expect(publicDeckText).toContain("每个节点的子节点数量不超过两个");
    expect(publicDeckText).toContain("根节点可以没有子节点");
    expect(publicDeckText).toContain("链式结构也是一种退化的二叉树");
    expect(publicDeckText).toContain("先说出节点的子树边界");
    expect(publicDeckText).toContain("空树：None → []");
    expect(publicDeckText).toContain("改为后序遍历并比较访问顺序");
    expect(publicDeckText).toContain("把根节点访问时机和子树顺序混淆");
    expect(publicDeckText).toContain("访问顺序正确：4 分");
    expect(publicDeckText).toContain("为什么中序遍历适合搜索树");
    expect(publicDeckText).not.toContain("正确答案是根节点");
    expect(publicDeckText).not.toContain("旧正文答案解析");
    expect(publicDeckText).not.toContain("answer_index");
    expect(publicDeckText).not.toContain("explanation");
  });

  it("reads structured payloads nested in legacy metadata", () => {
    const model = buildNodePresentationModel({
      nodeTitle: "兼容节点",
      cards: [{
        resource_type: "concept_map",
        metadata: {
          structured_payload: {
            title: "嵌套概念",
            definition: "嵌套 payload 仍然可以导出。",
            bullets: ["兼容旧缓存结构。"],
          },
        },
      }],
    });

    const deckText = JSON.stringify(model.slides);
    expect(deckText).toContain("嵌套概念");
    expect(deckText).toContain("兼容旧缓存结构");
  });

  it("writes a real PPTX blob", async () => {
    const result = await createNodePptBlob({
      nodeTitle: "二叉树",
      nodeId: "binary-tree",
      cards,
    });

    expect(result.blob.type).toBe(MIME_TYPE);
    expect(result.blob.size).toBeGreaterThan(5_000);
    expect(result.slideCount).toBeGreaterThan(4);

    const bytes = new Uint8Array(await blobToArrayBuffer(result.blob));
    expect(String.fromCharCode(...bytes.slice(0, 2))).toBe("PK");
  });

  it("rejects export before node resources are ready", async () => {
    await expect(createNodePptBlob({ nodeTitle: "空节点", cards: [] }))
      .rejects
      .toThrow("当前节点还没有可导出的学习资料");
  });

  it("adds a diagram slide when the concept card carries mermaid source", () => {
    const mermaid = 'graph TD\nA["前置"] --> B["概念"]';
    const model = buildNodePresentationModel({
      nodeTitle: "二叉树",
      cards: [{
        resource_type: "concept_map",
        title: "二叉树核心概念",
        structured_payload: {
          definition: "二叉树中每个节点最多有两个子节点。",
          mermaid_source: mermaid,
          constraints: ["根节点可以没有子节点。"],
          mechanism: ["从根节点向左右子树递归展开"],
        },
      }],
    });

    const diagram = model.slides.find((slide) => slide.kind === "diagram");
    expect(diagram).toBeTruthy();
    expect(diagram.mermaid).toBe(mermaid);
    expect(diagram.fallback.bullets.length).toBeGreaterThan(0);
  });

  it("exports successfully even when mermaid rendering is unavailable", async () => {
    const result = await createNodePptBlob({
      nodeTitle: "二叉树",
      cards: [{
        resource_type: "concept_map",
        title: "二叉树核心概念",
        structured_payload: {
          definition: "二叉树中每个节点最多有两个子节点。",
          mermaid_source: "graph TD\nA --> B",
        },
      }],
    });

    expect(result.blob.type).toBe(MIME_TYPE);
    const bytes = new Uint8Array(await blobToArrayBuffer(result.blob));
    expect(String.fromCharCode(...bytes.slice(0, 2))).toBe("PK");
  });

  it("strips residual markdown emphasis markers from slide text", () => {
    const model = buildNodePresentationModel({
      nodeTitle: "排序",
      cards: [{
        resource_type: "concept_map",
        title: "快速排序",
        structured_payload: {
          definition: "**快速排序**基于*分治*策略。",
          learning_objectives: ["1. 理解 `partition` 的作用", "> 掌握基准选择"],
        },
      }],
    });

    const deckText = JSON.stringify(model.slides);
    expect(deckText).toContain("快速排序基于分治策略");
    expect(deckText).toContain("理解 partition 的作用");
    expect(deckText).toContain("掌握基准选择");
    expect(deckText).not.toContain("**");
    expect(deckText).not.toContain("> 掌握");
  });

  it("splits overlong bullet lists into continuation slides instead of shrinking", () => {
    const longBullets = Array.from({ length: 14 }, (_, index) => (
      `第 ${index + 1} 条：这是一条足够长的中文要点，用来验证内容会按估算行数拆分成续页而不是被压缩到不可读的字号。`
    ));
    const model = buildNodePresentationModel({
      nodeTitle: "分页",
      cards: [{
        resource_type: "concept_map",
        title: "长内容概念",
        structured_payload: {
          definition: "定义。",
          learning_objectives: longBullets,
        },
      }],
    });

    const pages = model.slides.filter((slide) => slide.title.startsWith("长内容概念") && slide.kind === "content");
    expect(pages.length).toBeGreaterThan(1);
    expect(pages.some((slide) => slide.title.endsWith("（续）"))).toBe(true);
    const allBullets = pages.flatMap((slide) => slide.bullets);
    // 分页不丢内容（原逻辑 slice(0, 6) 会截断）。
    expect(allBullets.filter((item) => item.startsWith("第")).length).toBe(14);
  });
});

function blobToArrayBuffer(blob) {
  if (typeof blob.arrayBuffer === "function") {
    return blob.arrayBuffer();
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}
