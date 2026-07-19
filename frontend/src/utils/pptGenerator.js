import {
  CODE_LANGUAGE,
  extractCCode,
  normalizeCodeLanguage,
  resolveStructuredPayload,
} from "./codeExample.js";

const MIME_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation";
const BULLET = "\u2022";

const COLORS = {
  ink: "17352D",
  inkMuted: "4F6B61",
  paper: "FAF7EF",
  panel: "FFFEF9",
  line: "CFE0D7",
  primary: "1E5E4D",
  teal: "2E8C8A",
  gold: "C8A858",
  blue: "3A8CBF",
  red: "C45A5A",
  code: "10231F",
  codeText: "E7F4EE",
  white: "FFFFFF",
};

const CARD_META = {
  concept_map: { label: "概念理解", accent: COLORS.primary },
  code_snippet: { label: "代码示例", accent: COLORS.teal },
  interactive_exercise: { label: "动手练习", accent: COLORS.gold },
  video_summary: { label: "视频回顾", accent: COLORS.blue },
  diagnostic_quiz: { label: "自我检查", accent: COLORS.red },
};

const DEFAULT_CARD_ORDER = [
  "concept_map",
  "code_snippet",
  "interactive_exercise",
  "video_summary",
  "diagnostic_quiz",
];

const SLIDE_WIDTH = 13.333;
const SLIDE_HEIGHT = 7.5;

export function buildNodePresentationModel({ nodeTitle = "", nodeId = "", cards = [] } = {}) {
  const title = firstText(nodeTitle, "当前学习节点");
  const normalizedCards = Array.isArray(cards)
    ? cards.filter((card) => card && typeof card === "object")
    : [];
  const slides = [
    {
      kind: "cover",
      title,
      subtitle: "节点学习课件",
      detail: normalizedCards.length
        ? `基于 ${normalizedCards.length} 份已生成学习资料整理`
        : "等待学习资料生成",
    },
    {
      kind: "agenda",
      title: "本节学习路线",
      items: normalizedCards.length
        ? orderedCards(normalizedCards).map((card) => cardLabel(card))
        : ["先生成当前节点的学习资料", "再按概念、示例、练习和检查逐步学习"],
    },
  ];

  for (const card of orderedCards(normalizedCards)) {
    slides.push(...slidesForCard(card));
  }

  const takeaways = buildTakeaways(normalizedCards);
  slides.push({
    kind: "summary",
    title: "带走这三件事",
    bullets: takeaways.length ? takeaways : ["能用自己的话解释核心概念", "能在新问题中判断适用条件", "能通过练习和自测验证掌握情况"],
    detail: "回到学习工作台，完成当前节点的练习与诊断后再进入下一节点。",
  });

  return {
    title,
    nodeId: String(nodeId || ""),
    filename: `EduAgent-${safeFilename(title)}.pptx`,
    slides,
  };
}

export async function generateNodePpt(input = {}) {
  const result = await createNodePptBlob(input);
  downloadBlob(result.blob, result.filename);
  return {
    filename: result.filename,
    slideCount: result.slideCount,
    nodeId: result.nodeId,
  };
}

export async function createNodePptBlob(input = {}) {
  const model = buildNodePresentationModel(input);
  if (!Array.isArray(input.cards) || input.cards.length === 0) {
    throw new Error("当前节点还没有可导出的学习资料");
  }

  const { default: PptxGenJS } = await import("pptxgenjs");
  const pptx = new PptxGenJS();
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "EduAgent";
  pptx.company = "EduAgent";
  pptx.subject = `${model.title} 节点学习课件`;
  pptx.title = model.title;
  pptx.theme = {
    headFontFace: "Aptos Display",
    bodyFontFace: "Aptos",
  };

  model.slides.forEach((descriptor, index) => {
    const slide = pptx.addSlide();
    renderSlide(slide, pptx, descriptor, index + 1, model.slides.length, model.title);
  });

  const output = await pptx.write({ outputType: "blob", compression: true });
  const blob = new Blob([output], { type: MIME_TYPE });
  return {
    blob,
    filename: model.filename,
    slideCount: model.slides.length,
    nodeId: model.nodeId,
  };
}

export function downloadBlob(blob, filename) {
  if (typeof document === "undefined" || typeof URL === "undefined") {
    throw new Error("当前环境不支持文件下载");
  }

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function orderedCards(cards) {
  const order = new Map(DEFAULT_CARD_ORDER.map((type, index) => [type, index]));
  return [...cards].sort((left, right) => (
    (order.get(resourceType(left)) ?? DEFAULT_CARD_ORDER.length)
      - (order.get(resourceType(right)) ?? DEFAULT_CARD_ORDER.length)
  ));
}

function slidesForCard(card) {
  const type = resourceType(card);
  const payload = cardPayload(card);
  const title = cardTitle(card, CARD_META[type]?.label || "学习资料");
  if (type === "concept_map") return conceptSlides(title, payload, card);
  if (type === "code_snippet") return codeSlides(title, payload, card);
  if (type === "interactive_exercise") return exerciseSlides(title, payload, card);
  if (type === "video_summary") return videoSlides(title, payload, card);
  if (type === "diagnostic_quiz") return quizSlides(title, payload);

  const fallback = cleanMarkdown(card.body_markdown || card.content);
  return fallback
    ? [{ kind: "content", kicker: "学习资料", title, lead: fallback, bullets: [] }]
    : [];
}

function conceptSlides(title, payload, card) {
  const slides = [];
  const summary = firstText(payload.summary);
  const definition = firstText(payload.definition, summary, cleanMarkdown(card.body_markdown));
  const objectives = uniqueStrings([
    ...listValue(payload, "learning_objectives", "objectives"),
    ...listValue(payload, "bullets"),
  ]);
  const prerequisites = listValue(payload, "prerequisites");
  const constraints = listValue(payload, "constraints");
  const mechanism = listValue(payload, "mechanism");
  const blueprint = objectValue(payload.learning_blueprint);
  const misconceptions = uniqueStrings([
    ...listValue(payload, "common_misconceptions"),
    ...listValue(blueprint, "misconceptions"),
  ]);
  const counterexamples = uniqueStrings([
    ...listValue(payload, "counterexamples"),
    ...listValue(blueprint, "boundaries"),
  ]);
  const conceptNotes = uniqueStrings([
    summary && summary !== definition ? summary : "",
    prerequisites.length ? `先备知识：${joinText(prerequisites, 3)}` : "",
  ]);

  slides.push({
    kind: "content",
    kicker: "概念理解",
    title,
    lead: definition,
    bullets: objectives.slice(0, 6),
    note: conceptNotes.join("；") || "先说清楚定义，再追踪它如何工作。",
  });

  if (constraints.length || mechanism.length) {
    slides.push({
      kind: "columns",
      kicker: "结构与机制",
      title: `${title}：什么时候成立？`,
      columns: [
        { heading: "成立条件", items: constraints.slice(0, 6) },
        { heading: "核心机制", items: mechanism.slice(0, 6) },
      ],
    });
  }

  if (misconceptions.length || counterexamples.length) {
    slides.push({
      kind: "columns",
      kicker: "边界辨析",
      title: `${title}：哪些理解需要修正？`,
      columns: [
        { heading: "常见误区", items: misconceptions.slice(0, 6) },
        { heading: "反例与边界", items: counterexamples.slice(0, 6) },
      ],
    });
  }

  const sections = Array.isArray(payload.sections) ? payload.sections : [];
  for (const section of sections.slice(0, 6)) {
    const heading = firstText(section?.heading, "关键要点");
    const body = cleanMarkdown(section?.body);
    if (body) {
      slides.push({ kind: "content", kicker: "关键要点", title: heading, lead: body, bullets: [] });
    }
  }

  const transfer = uniqueStrings([
    ...listValue(payload, "transfer_questions"),
    ...listValue(payload, "review_prompts"),
  ]);
  if (transfer.length) {
    slides.push({ kind: "content", kicker: "迁移练习", title: "换一个问题试试看", lead: "先预测结构，再检查它是否满足当前概念的条件。", bullets: transfer.slice(0, 6) });
  }
  return slides;
}

function codeSlides(title, payload, card) {
  const slides = [];
  const scenario = firstText(payload.scenario, payload.explanation, cleanMarkdown(card.body_markdown));
  const walkthrough = listValue(payload, "walkthrough_steps", "steps");
  const complexity = listValue(payload, "complexity_notes");
  const prerequisites = listValue(payload, "prerequisites");
  const boundaryTests = formatBoundaryTests(payload.boundary_tests);
  const codeNotes = uniqueStrings([
    prerequisites.length ? `先备知识：${joinText(prerequisites, 3)}` : "",
    complexity.length ? `复杂度：${joinText(complexity, 3)}` : "",
  ]);

  slides.push({
    kind: "content",
    kicker: "代码示例",
    title,
    lead: scenario,
    bullets: walkthrough.slice(0, 6),
    note: codeNotes.join("；") || "读代码时，逐步追踪状态变化和不变量。",
  });

  const explanation = firstText(payload.explanation);
  if (explanation && explanation !== scenario) {
    slides.push({
      kind: "content",
      kicker: "原理解释",
      title: `${title}：为什么可行？`,
      lead: explanation,
      bullets: walkthrough.slice(0, 6),
    });
  }

  const code = extractCCode(card);
  if (code) {
    const lines = code.split("\n");
    for (let index = 0; index < lines.length; index += 34) {
      slides.push({
        kind: "code",
        kicker: "可运行片段",
        title: lines.length > 34 ? `${title}：代码 ${Math.floor(index / 34) + 1}` : `${title}：代码`,
        code: lines.slice(index, index + 34).join("\n"),
        language: normalizeCodeLanguage(payload.language),
      });
    }
  }

  const pitfalls = uniqueStrings([
    ...listValue(payload, "pitfalls"),
    ...listValue(payload, "experiments"),
  ]);
  if (boundaryTests.length || pitfalls.length) {
    slides.push({
      kind: "columns",
      kicker: "验证与反思",
      title: "运行后检查这些地方",
      columns: [
        { heading: "边界测试", items: boundaryTests.slice(0, 6) },
        { heading: "常见错误与实验", items: pitfalls.slice(0, 6) },
      ],
    });
  }
  return slides;
}

function exerciseSlides(title, payload, card) {
  const goal = firstText(payload.goal);
  const prompt = firstText(payload.prompt, goal, cleanMarkdown(card.body_markdown));
  const hasSeparatePrompt = Boolean(goal && prompt && goal !== prompt);
  const steps = listValue(payload, "steps");
  const checkpoints = uniqueStrings([
    ...listValue(payload, "checkpoints"),
    ...formatExerciseCheckpoints(payload.structured_checkpoints),
  ]);
  const hints = listValue(payload, "hints");
  const rubric = formatExerciseRubric(payload.rubric);
  const errorSignature = firstText(payload.error_signature);
  const expectedOutcome = firstText(payload.expected_outcome, "完成后，用检查点解释你的判断依据。");
  const overviewNotes = uniqueStrings([
    errorSignature ? `本次练习重点修正：${errorSignature}` : "",
    hasSeparatePrompt ? "" : expectedOutcome,
  ]);
  const slides = [{
    kind: "content",
    kicker: "动手练习",
    title,
    lead: goal || prompt,
    bullets: hasSeparatePrompt ? [] : steps.slice(0, 6),
    note: overviewNotes.join("；"),
  }];
  if (hasSeparatePrompt) {
    slides.push({
      kind: "content",
      kicker: "任务说明",
      title: "开始完成任务",
      lead: prompt,
      bullets: steps.slice(0, 6),
      note: expectedOutcome,
    });
  }
  if (checkpoints.length || hints.length) {
    slides.push({
      kind: "columns",
      kicker: "练习提示",
      title: "做题时保持这条路径",
      columns: [
        { heading: "检查点", items: checkpoints.slice(0, 6) },
        { heading: "必要时再看提示", items: hints.slice(0, 5) },
      ],
    });
  }
  if (rubric.length) {
    slides.push({
      kind: "content",
      kicker: "评分标准",
      title: "完成后如何判断质量",
      lead: firstText(payload.expected_outcome, "按证据逐项检查练习结果。"),
      bullets: rubric.slice(0, 7),
    });
  }
  if (payload.solution_outline) {
    slides.push({ kind: "content", kicker: "复盘", title: "参考思路", lead: cleanMarkdown(payload.solution_outline), bullets: [] });
  }
  return slides;
}

function videoSlides(title, payload, card) {
  const summary = firstText(payload.summary, cleanMarkdown(card.body_markdown));
  const points = listValue(payload, "key_points");
  const watchFocus = uniqueStrings([
    ...listValue(payload, "watch_focus"),
    ...listValue(payload, "review_questions"),
  ]);
  const readingSequence = listValue(payload, "reading_sequence");
  const timeline = Array.isArray(payload.timeline)
    ? payload.timeline.map((item) => `${firstText(item?.label, "片段")}：${cleanMarkdown(item?.summary)}`).filter(Boolean)
    : [];
  const routeItems = uniqueStrings([...timeline, ...readingSequence]);
  const slides = [{ kind: "content", kicker: "视频回顾", title, lead: summary, bullets: points.slice(0, 7), note: payload.duration_minutes ? `建议用时：${payload.duration_minutes} 分钟` : "观看时先抓住主线，再回到关键细节。" }];
  if (routeItems.length || watchFocus.length) {
    slides.push({
      kind: "columns",
      kicker: timeline.length ? "观看路线" : "学习路线",
      title: timeline.length ? "带着问题观看" : "按顺序阅读与复习",
      columns: [
        { heading: timeline.length ? "时间线与阅读顺序" : "阅读顺序", items: routeItems.slice(0, 6) },
        { heading: "重点关注", items: watchFocus.slice(0, 6) },
      ],
    });
  }
  return slides;
}

function quizSlides(title, payload) {
  const questions = Array.isArray(payload.questions) ? payload.questions : [];
  const guidance = firstText(
    payload.after_quiz_guidance,
    payload.summary,
    "先独立作答，再回看错题对应的概念与边界。",
  );
  const slides = [{
    kind: "content",
    kicker: "自我检查",
    title,
    lead: guidance,
    bullets: questions.length ? [`共 ${Math.min(questions.length, 8)} 道题，请先独立作答。`] : [],
    note: "课件不包含答案；请回到学习工作台提交诊断，获得掌握度反馈。",
  }];

  questions.slice(0, 8).forEach((question, index) => {
    const prompt = firstText(question?.prompt, question?.question);
    if (!prompt) return;
    const options = Array.isArray(question?.options)
      ? question.options.map((option, optionIndex) => (
        `${String.fromCharCode(65 + optionIndex)}. ${cleanMarkdown(option)}`
      )).filter((option) => option.length > 3)
      : [];
    slides.push({
      kind: "content",
      kicker: "自我检查",
      title: `${title} · 第 ${index + 1} 题`,
      lead: prompt,
      bullets: options,
      note: "先记录你的选择和理由，再回到学习工作台提交答案。",
    });
  });
  return slides;
}

function buildTakeaways(cards) {
  const concept = cards.find((card) => resourceType(card) === "concept_map");
  const code = cards.find((card) => resourceType(card) === "code_snippet");
  const exercise = cards.find((card) => resourceType(card) === "interactive_exercise");
  const takeaways = [];
  if (concept) {
    const payload = cardPayload(concept);
    takeaways.push(firstText(payload.definition, payload.summary, "说清楚定义、机制和边界"));
  }
  if (code) takeaways.push("用一个可运行示例验证机制，并检查复杂度");
  if (exercise) takeaways.push(firstText(cardPayload(exercise).expected_outcome, "通过练习把理解迁移到新问题"));
  return uniqueStrings(takeaways).slice(0, 3);
}

function renderSlide(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle) {
  if (descriptor.kind === "cover") return renderCover(slide, pptx, descriptor, slideNumber, totalSlides);

  slide.background = { color: COLORS.paper };
  if (descriptor.kind === "agenda") {
    renderAgenda(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle);
    return;
  }
  if (descriptor.kind === "code") {
    renderCode(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle);
    return;
  }
  if (descriptor.kind === "columns") {
    renderColumns(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle);
    return;
  }
  if (descriptor.kind === "summary") {
    renderSummary(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle);
    return;
  }
  renderContent(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle);
}

function renderCover(slide, pptx, descriptor, slideNumber, totalSlides) {
  slide.background = { color: COLORS.ink };
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: 0.28, h: SLIDE_HEIGHT, fill: { color: COLORS.teal }, line: { color: COLORS.teal } });
  slide.addShape(pptx.ShapeType.rect, { x: 0.72, y: 1.15, w: 1.1, h: 0.12, fill: { color: COLORS.gold }, line: { color: COLORS.gold } });
  slide.addText("EDUAGENT  /  NODE STUDY", { x: 0.78, y: 0.62, w: 5.8, h: 0.28, fontFace: "Aptos", fontSize: 10, bold: true, charSpacing: 1.8, color: "B8D6A7", margin: 0 });
  slide.addText(descriptor.title, { x: 0.72, y: 1.62, w: 11.2, h: 1.35, fontFace: "Aptos Display", fontSize: 30, bold: true, color: COLORS.white, breakLine: false, fit: "shrink", margin: 0 });
  slide.addText(descriptor.subtitle, { x: 0.78, y: 3.35, w: 5.5, h: 0.45, fontSize: 19, bold: true, color: "D7E9E0", margin: 0 });
  slide.addText(descriptor.detail, { x: 0.8, y: 4.05, w: 7.2, h: 0.5, fontSize: 12, color: "A8C7B9", margin: 0, fit: "shrink" });
  addFooter(slide, slideNumber, totalSlides, descriptor.title, { dark: true });
}

function renderAgenda(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle) {
  addHeader(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle);
  const items = descriptor.items.slice(0, 8);
  items.forEach((item, index) => {
    const y = 1.75 + index * 0.54;
    slide.addShape(pptx.ShapeType.ellipse, { x: 0.86, y: y + 0.06, w: 0.24, h: 0.24, fill: { color: COLORS.primary }, line: { color: COLORS.primary } });
    slide.addText(String(index + 1).padStart(2, "0"), { x: 1.28, y, w: 0.5, h: 0.3, fontFace: "Aptos", fontSize: 11, bold: true, color: COLORS.primary, margin: 0 });
    slide.addText(item, { x: 1.95, y: y - 0.02, w: 9.8, h: 0.34, fontSize: 17, color: COLORS.ink, margin: 0, fit: "shrink" });
    slide.addShape(pptx.ShapeType.line, { x: 1.95, y: y + 0.38, w: 9.8, h: 0, line: { color: COLORS.line, width: 0.8 } });
  });
}

function renderContent(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle) {
  addHeader(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle);
  let y = 1.55;
  if (descriptor.lead) {
    slide.addText(descriptor.lead, { x: 0.82, y, w: 11.65, h: 0.95, fontSize: 19, bold: true, color: COLORS.ink, margin: 0, fit: "shrink", breakLine: false });
    y += 1.22;
  }
  if (descriptor.bullets?.length) {
    const lines = descriptor.bullets.slice(0, 8).map((item) => `${BULLET} ${item}`).join("\n");
    slide.addShape(pptx.ShapeType.roundRect, { x: 0.82, y, w: 11.65, h: Math.min(3.95, Math.max(1.2, descriptor.bullets.length * 0.52 + 0.35)), fill: { color: COLORS.panel }, line: { color: COLORS.line, width: 0.8 }, rectRadius: 0.08 });
    slide.addText(lines, { x: 1.1, y: y + 0.28, w: 10.95, h: Math.min(3.45, Math.max(0.7, descriptor.bullets.length * 0.52)), fontSize: 15, color: COLORS.inkMuted, breakLine: false, fit: "shrink", margin: 0.02, paraSpaceAfter: 8, valign: "middle" });
  }
  if (descriptor.note) {
    slide.addText(descriptor.note, { x: 0.84, y: 6.05, w: 11.5, h: 0.46, fontSize: 11, color: COLORS.primary, italic: true, margin: 0, fit: "shrink" });
  }
}

function renderColumns(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle) {
  addHeader(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle);
  const columns = descriptor.columns || [];
  const width = columns.length > 1 ? 5.6 : 11.65;
  columns.slice(0, 2).forEach((column, index) => {
    const x = 0.82 + index * 5.98;
    const height = Math.min(4.75, Math.max(1.65, (column.items || []).length * 0.55 + 0.9));
    slide.addShape(pptx.ShapeType.roundRect, { x, y: 1.58, w: width, h: height, fill: { color: COLORS.panel }, line: { color: COLORS.line, width: 0.8 }, rectRadius: 0.08 });
    slide.addShape(pptx.ShapeType.rect, { x, y: 1.58, w: width, h: 0.1, fill: { color: index === 0 ? COLORS.primary : COLORS.teal }, line: { color: index === 0 ? COLORS.primary : COLORS.teal } });
    slide.addText(firstText(column.heading, "要点"), { x: x + 0.3, y: 1.93, w: width - 0.6, h: 0.35, fontSize: 14, bold: true, color: COLORS.ink, margin: 0, fit: "shrink" });
    const text = (column.items || []).slice(0, 7).map((item) => `${BULLET} ${item}`).join("\n") || "暂无内容";
    slide.addText(text, { x: x + 0.3, y: 2.4, w: width - 0.6, h: height - 1.0, fontSize: 13, color: COLORS.inkMuted, margin: 0.02, fit: "shrink", paraSpaceAfter: 7, valign: "middle" });
  });
}

function renderCode(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle) {
  addHeader(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle);
  slide.addText(normalizeCodeLanguage(descriptor.language).toUpperCase() || CODE_LANGUAGE.toUpperCase(), { x: 0.84, y: 1.5, w: 2.2, h: 0.3, fontFace: "Aptos", fontSize: 10, bold: true, color: COLORS.teal, charSpacing: 1.2, margin: 0 });
  slide.addShape(pptx.ShapeType.roundRect, { x: 0.82, y: 1.88, w: 11.65, h: 4.65, fill: { color: COLORS.code }, line: { color: COLORS.code }, rectRadius: 0.08 });
  slide.addText(descriptor.code, { x: 1.08, y: 2.16, w: 11.1, h: 4.05, fontFace: "Consolas", fontSize: 11.5, color: COLORS.codeText, margin: 0.02, fit: "shrink", breakLine: false, valign: "top" });
}

function renderSummary(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle) {
  addHeader(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle);
  const items = descriptor.bullets.slice(0, 3);
  items.forEach((item, index) => {
    const y = 1.65 + index * 1.18;
    slide.addText(String(index + 1).padStart(2, "0"), { x: 0.86, y, w: 0.7, h: 0.42, fontFace: "Aptos Display", fontSize: 22, bold: true, color: index === 0 ? COLORS.primary : index === 1 ? COLORS.teal : COLORS.gold, margin: 0 });
    slide.addText(item, { x: 1.85, y: y + 0.02, w: 9.9, h: 0.62, fontSize: 19, color: COLORS.ink, bold: true, margin: 0, fit: "shrink" });
    slide.addShape(pptx.ShapeType.line, { x: 1.85, y: y + 0.76, w: 9.9, h: 0, line: { color: COLORS.line, width: 0.8 } });
  });
  slide.addText(descriptor.detail, { x: 0.86, y: 5.55, w: 11.1, h: 0.6, fontSize: 13, color: COLORS.primary, italic: true, margin: 0, fit: "shrink" });
}

function addHeader(slide, pptx, descriptor, slideNumber, totalSlides, nodeTitle) {
  const accent = descriptor.kicker === "代码示例" || descriptor.kicker === "可运行片段"
    ? COLORS.teal
    : descriptor.kicker === "动手练习"
      ? COLORS.gold
      : descriptor.kicker === "自我检查"
        ? COLORS.red
        : COLORS.primary;
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: SLIDE_WIDTH, h: 0.16, fill: { color: accent }, line: { color: accent } });
  slide.addText(descriptor.kicker || "节点学习", { x: 0.84, y: 0.52, w: 3.6, h: 0.26, fontSize: 10, bold: true, charSpacing: 1.2, color: accent, margin: 0 });
  slide.addText(descriptor.title, { x: 0.82, y: 0.86, w: 11.6, h: 0.55, fontFace: "Aptos Display", fontSize: 24, bold: true, color: COLORS.ink, margin: 0, fit: "shrink" });
  slide.addShape(pptx.ShapeType.line, { x: 0.82, y: 1.46, w: 11.65, h: 0, line: { color: COLORS.line, width: 0.8 } });
  addFooter(slide, slideNumber, totalSlides, nodeTitle);
}

function addFooter(slide, slideNumber, totalSlides, nodeTitle, { dark = false } = {}) {
  slide.addText(`EduAgent  ·  ${nodeTitle}`, { x: 0.82, y: 7.08, w: 7.8, h: 0.18, fontSize: 8.5, color: dark ? "9EC1B1" : COLORS.inkMuted, margin: 0, fit: "shrink" });
  slide.addText(`${slideNumber} / ${totalSlides}`, { x: 11.35, y: 7.08, w: 1.1, h: 0.18, fontFace: "Aptos", fontSize: 8.5, color: dark ? "9EC1B1" : COLORS.inkMuted, align: "right", margin: 0 });
}

function resourceType(card) {
  return String(card?.resource_type || card?.card_type || card?.type || "").trim();
}

function cardPayload(card) {
  return resolveStructuredPayload(card);
}

function cardTitle(card, fallback) {
  return firstText(card?.title, cardPayload(card).title, fallback);
}

function cardLabel(card) {
  const type = resourceType(card);
  return `${CARD_META[type]?.label || "学习资料"}：${cardTitle(card, type || "学习资料")}`;
}

function listValue(payload, ...keys) {
  for (const key of keys) {
    const value = payload?.[key];
    if (Array.isArray(value)) {
      const items = uniqueStrings(value.map((item) => {
        if (typeof item === "string") return cleanMarkdown(item);
        if (item && typeof item === "object") return cleanMarkdown(item.text || item.summary || item.prompt || "");
        return "";
      }));
      if (items.length) return items;
    }
    if (typeof value === "string" && value.trim()) return [cleanMarkdown(value)];
  }
  return [];
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function formatBoundaryTests(value) {
  if (!Array.isArray(value)) return [];
  return uniqueStrings(value.map((test) => {
    if (typeof test === "string") return cleanMarkdown(test);
    if (!test || typeof test !== "object") return "";
    const name = firstText(test.name, "边界测试");
    const input = firstText(test.input);
    const expected = firstText(test.expected);
    const mapping = [input, expected].filter(Boolean).join(" → ");
    return mapping ? `${name}：${mapping}` : name;
  }));
}

function formatExerciseCheckpoints(value) {
  if (!Array.isArray(value)) return [];
  return uniqueStrings(value.map((checkpoint) => {
    if (typeof checkpoint === "string") return cleanMarkdown(checkpoint);
    if (!checkpoint || typeof checkpoint !== "object") return "";
    const prompt = firstText(checkpoint.prompt, checkpoint.text);
    const expectedSignal = firstText(checkpoint.expected_signal);
    return expectedSignal ? `${prompt}（观察信号：${expectedSignal}）` : prompt;
  }));
}

function formatExerciseRubric(value) {
  if (!Array.isArray(value)) return [];
  return uniqueStrings(value.map((item) => {
    if (typeof item === "string") return cleanMarkdown(item);
    if (!item || typeof item !== "object") return "";
    const criterion = firstText(item.criterion, item.text);
    const points = Number(item.points);
    const score = Number.isFinite(points) ? `${points} 分` : "";
    const evidence = firstText(item.evidence);
    const detail = [score, evidence].filter(Boolean).join(" · ");
    return detail ? `${criterion}：${detail}` : criterion;
  }));
}

function firstText(...values) {
  for (const value of values) {
    const text = cleanMarkdown(value);
    if (text) return text;
  }
  return "";
}

function joinText(items, limit) {
  return items.slice(0, limit).join("、");
}

function uniqueStrings(items) {
  const seen = new Set();
  return items
    .map((item) => String(item || "").trim())
    .filter((item) => item && !seen.has(item) && seen.add(item));
}

function cleanMarkdown(value) {
  return String(value ?? "")
    .replace(/```[\w-]*\s*/g, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s*/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

function safeFilename(value) {
  return String(value || "node")
    .split("")
    .filter((character) => character.charCodeAt(0) >= 32)
    .join("")
    .replace(/[<>:"/\\|?*]/g, "-")
    .replace(/\s+/g, "-")
    .slice(0, 80) || "node";
}

export { CARD_META, MIME_TYPE };
