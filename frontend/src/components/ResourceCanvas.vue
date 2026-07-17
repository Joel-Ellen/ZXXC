<template>
  <section
    ref="scrollViewport"
    class="resource-canvas aurora-scroll relative h-full min-h-0 overflow-y-auto px-4 py-4 sm:px-5 lg:px-6"
    @wheel="forwardWheelToContent"
  >
    <header class="resource-canvas__header">
      <div class="resource-canvas__heading-row">
        <div class="min-w-0">
          <p class="resource-canvas__eyebrow">当前学习节点</p>
          <div class="resource-canvas__title-line">
            <h1 class="resource-canvas__title">{{ nodeTitle || "等待装配" }}</h1>
            <span class="workspace-shell-chip workspace-shell-chip--accent shrink-0 px-3 py-1 text-[11px] font-semibold">
              {{ learningTone }}
            </span>
          </div>
        </div>

        <div class="resource-canvas__actions">
          <button
            type="button"
<<<<<<< HEAD
            class="workspace-shell-btn workspace-shell-btn--secondary focus-ring px-3 py-2 text-[11px] font-semibold"
=======
            class="workspace-shell-btn focus-ring min-h-11 px-3 py-2 text-[11px] font-semibold"
            @click="isExpanded = !isExpanded"
          >
            {{ isExpanded ? "紧凑视图" : "展开矩阵" }}
          </button>
          <button
            type="button"
            class="workspace-shell-btn workspace-shell-btn--secondary focus-ring min-h-11 px-3 py-2 text-[11px] font-semibold"
>>>>>>> origin/main
            @click="focusMode = !focusMode"
          >
            {{ focusMode ? "退出聚焦" : "聚焦模式" }}
          </button>
          <button
            v-if="activeCardType"
            type="button"
            class="workspace-shell-btn focus-ring min-h-11 px-3 py-2 text-[11px] font-semibold"
            :disabled="!currentNode || isCardPending(activeCardType)"
            @click="$emit('generate-card', { nodeId: currentNode, cardType: activeCardType, force: true })"
          >
            {{ isCardPending(activeCardType) ? "重新生成中..." : "重新生成当前卡" }}
          </button>
          <button
            type="button"
            class="workspace-shell-btn workspace-shell-btn--accent focus-ring min-h-11 px-3 py-2 text-[11px] font-semibold"
            :disabled="!currentNode || isAllCardsPending"
            @click="$emit('refresh')"
          >
            {{ isAllCardsPending ? "重新生成中..." : "重新生成全部" }}
          </button>
        </div>
      </div>

      <div class="resource-canvas__status" aria-label="当前节点学习状态">
        <div class="resource-canvas__metric">
          <span>掌握度</span>
          <strong>{{ currentMastery }}%</strong>
        </div>
        <div class="resource-canvas__metric">
          <span>学习资料</span>
          <strong>{{ props.cards.length }} 份</strong>
        </div>
        <div class="resource-canvas__metric resource-canvas__metric--progress">
          <span>课程进度</span>
          <strong>{{ masteredCount }}/{{ pathNodes.length }}</strong>
        </div>
        <p class="resource-canvas__guidance">
          {{ currentNodeMeta ? resourceGuidance : "选择课程节点后，资料会在这里自动装配。" }}
        </p>
      </div>

      <div class="resource-canvas__nodes">
        <span class="resource-canvas__nodes-label">课程节点</span>
        <div ref="nodeScroller" class="aurora-scroll flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1">
        <button
          v-for="node in pathNodes"
          :key="node.id"
          :ref="(element) => setNodeButtonRef(node.id, element)"
          type="button"
          class="course-path-panel__node workspace-shell-chip focus-ring min-h-11 shrink-0 px-3.5 py-1.5 text-[11px] font-medium tracking-[0.06em] transition-all duration-200 active:scale-95"
          :class="nodeChipClass(node)"
          :aria-current="selectedNodeId === node.id ? 'step' : undefined"
          @click="selectNode(node.id)"
        >
          {{ node.title }}
        </button>
        </div>
      </div>

<<<<<<< HEAD
      <div class="resource-canvas__filters" aria-label="资源类型">
        <span class="resource-canvas__filters-label">资源类型</span>
        <div class="resource-canvas__filter-scroll aurora-scroll" role="group" aria-label="筛选学习资源">
          <button
            v-for="item in resourceFilterItems"
            :key="item.key"
            type="button"
            class="resource-canvas__filter focus-ring"
            :class="{ 'resource-canvas__filter--active': filterType === item.key }"
            :aria-pressed="String(filterType === item.key)"
            @click="emit('filter-change', item.key)"
          >
            <span>{{ item.label }}</span>
            <span class="resource-canvas__filter-count" aria-hidden="true">{{ item.count }}</span>
          </button>
        </div>
=======
      <div class="flex min-w-0 gap-2 overflow-x-auto" role="tablist" aria-label="学习任务顺序">
        <button
          v-for="slot in cardTypeSlots"
          :key="slot.type"
          type="button"
          role="tab"
          class="workspace-shell-btn focus-ring min-h-11 shrink-0 px-3 py-2 text-[11px] font-semibold"
          :class="slot.card?.resource_id === activeCardId ? 'workspace-shell-btn--accent' : ''"
          :aria-selected="String(slot.card?.resource_id === activeCardId)"
          :disabled="!slot.card || isSlotPending(slot)"
          @click="slot.card && activateCard(slot.card.resource_id)"
        >
          {{ taskStageLabel(slot.type) }}
        </button>
>>>>>>> origin/main
      </div>
    </header>

    <div class="relative pb-4">
        <div v-if="!cards.length && !loading" class="flex h-full min-h-[420px] items-center justify-center">
        <div class="flex max-w-[44ch] flex-col items-center text-center animate-fadeIn">
          <div class="relative mb-6 flex h-24 w-24 items-center justify-center rounded-full">
            <div class="absolute inset-0 rounded-full bg-secondary/15 blur-2xl animate-halo" />
            <div class="absolute inset-0 rounded-full border border-secondary/20 animate-spin-slow" />
            <svg
              width="52"
              height="52"
              viewBox="0 0 48 48"
              fill="none"
              class="relative text-secondary"
              aria-hidden="true"
            >
              <circle cx="24" cy="24" r="6" stroke="currentColor" stroke-width="1.5" />
              <circle cx="24" cy="10" r="3.5" stroke="currentColor" stroke-width="1.25" opacity="0.65" />
              <circle cx="36" cy="30" r="3.5" stroke="currentColor" stroke-width="1.25" opacity="0.65" />
              <circle cx="12" cy="30" r="3.5" stroke="currentColor" stroke-width="1.25" opacity="0.65" />
              <path d="M24 17V20" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
              <path d="M29 27l4 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
              <path d="M19 27l-4 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </div>
          <p class="font-mono text-[12px] uppercase tracking-[0.22em] text-text-muted">
            当前学习节点等待装配
          </p>
          <p class="mt-2 font-mono text-[12px] leading-6 text-text-muted">
            请选择课程目录中的节点，或等待智能体完成资源生成。装配完成后会自动进入可学习状态。
          </p>
        </div>
      </div>

      <!-- 全部：原始卡片网格（保持动效、拖拽等原有样式） -->
      <div v-if="filterType === 'all'" class="resource-canvas__grid resource-canvas__grid--multiple">
        <template v-for="(slot, index) in cardTypeSlots" :key="slot.type">
          <div
<<<<<<< HEAD
            v-if="slot.card && !minimizedIds.includes(slot.card.resource_id)"
            :draggable="true"
            class="resource-canvas__slot animate-cardIn h-full card-depth transition-all duration-300"
            :style="{ animationDelay: `${index * 55}ms` }"
            @dragstart="onDragStart(slot.card.resource_id)"
            @dragover.prevent
            @drop="onDrop(slot.card.resource_id)"
=======
            v-if="slot.card"
            :data-resource-id="slot.card.resource_id"
            :data-resource-type="resourceType(slot.card)"
            class="animate-cardIn h-full card-depth transition-all duration-300"
            :style="{ animationDelay: `${index * 55}ms` }"
            :class="[getGridSpanClass(slot.type), slot.card.resource_id === activeCardId ? 'is-active md:-translate-y-1.5' : '']"
            @mouseup="captureSelectedText(slot.card)"
>>>>>>> origin/main
          >
            <template v-for="card of [slot.card]" :key="card.resource_id">
            <ResourceCard
              class="h-full"
              :agent-name="agentLabel(resourceType(card))"
              :title="cardLabel(resourceType(card))"
              :progress-text="slotProgressText(slot)"
              :progress="null"
              :is-ready="!isSlotPending(slot)"
              :is-active="card.resource_id === activeCardId"
<<<<<<< HEAD
              :is-expanded="isSingleCardView"
              :activatable="!loading"
              :color="cardColor(resourceType(card))"
              @activate="openCard(card)"
              @pin="pinCard(card.resource_id)"
              @minimize="minimizeCard(card.resource_id)"
=======
              :is-expanded="isCardHydrated(card.resource_id)"
              :is-bookmarked="isBookmarked(card)"
              :activatable="false"
              :show-pin="false"
              :show-minimize="false"
              :color="cardColor(resourceType(card))"
              @activate="activateCard(card.resource_id)"
              @bookmark="toggleBookmark(card)"
>>>>>>> origin/main
            >
              <template #content>
              <div class="space-y-4">
                <div class="workspace-shell-card-soft rounded-[20px] p-4">
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">{{ previewLabel(resourceType(card)) }}</p>
                  <pre v-if="resourceType(card) === 'code_snippet'" class="mt-3 overflow-x-auto rounded-[16px] border border-subtle/80 bg-[#08111f] px-4 py-3 text-xs leading-6 text-slate-100">{{ previewCode(card) }}</pre>
                  <p v-else class="mt-3 text-sm leading-7 text-text-secondary">{{ previewText(card) }}</p>
                </div>
<<<<<<< HEAD
                <button type="button" class="workspace-shell-btn workspace-shell-btn--accent focus-ring px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.10em]" @click.stop="openCard(card)">打开完整内容</button>
              </div>
            </template>
          </ResourceCard>
          </template>
          </div>
          <div v-else class="resource-canvas__slot animate-cardIn h-full transition-all duration-300" :style="{ animationDelay: `${index * 40}ms` }">
            <div class="slot-empty group h-full rounded-[22px] border border-dashed border-subtle/50 bg-space-elevated/40 flex flex-col items-center justify-center gap-4 p-6" :style="{ '--rail-accent': slot.color }">
              <span class="slot-empty-icon text-[2.25rem] opacity-40 group-hover:opacity-75 transition-opacity duration-300" :style="{ animationDelay: `${index * 0.4}s` }" aria-hidden="true">{{ slot.icon }}</span>
              <div class="text-center space-y-0.5"><p class="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-text-muted">{{ slot.label }}</p><p class="text-[11px] text-text-muted opacity-50">尚未生成</p></div>
              <button v-if="currentNode" type="button" class="btn-ripple workspace-shell-btn workspace-shell-btn--accent focus-ring px-4 py-2 text-[11px] font-semibold tracking-[0.06em] opacity-0 group-hover:opacity-100 translate-y-1 group-hover:translate-y-0 transition-all duration-200" @click="$emit('generate-card', { nodeId: currentNode, cardType: slot.type })">生成</button>
=======

                <button
                  type="button"
                    class="workspace-shell-btn workspace-shell-btn--accent focus-ring px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.10em]"
                    @click.stop="activateCard(card.resource_id)"
                  >
                  {{ card.resource_id === activeCardId ? "展开完整内容" : "设为当前并展开" }}
                </button>
              </div>

              <div v-else class="space-y-5">
                <div v-if="resourceType(card) === 'concept_map'" class="space-y-4">
                  <div class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-sm leading-7 text-text-secondary">{{ conceptSummary(card) }}</p>
                  </div>

                  <div v-if="conceptObjectives(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">学习目标</p>
                    <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(item, index) in conceptObjectives(card)" :key="`${card.resource_id}-objective-${index}`">{{ item }}</li>
                    </ul>
                  </div>

                  <div v-if="conceptSections(card).length" class="space-y-3">
                    <div
                      v-for="(section, index) in conceptSections(card)"
                      :key="`${card.resource_id}-section-${index}`"
                      class="workspace-shell-card rounded-[20px] p-4"
                    >
                      <p class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">{{ section.heading }}</p>
                      <p class="mt-3 text-sm leading-7 text-text-secondary">{{ section.body }}</p>
                    </div>
                  </div>

                  <div v-if="conceptBullets(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">关键要点</p>
                    <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(item, index) in conceptBullets(card)" :key="`${card.resource_id}-bullet-${index}`">{{ item }}</li>
                    </ul>
                  </div>

                  <div v-if="conceptMisconceptions(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">常见误区</p>
                    <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(item, index) in conceptMisconceptions(card)" :key="`${card.resource_id}-misconception-${index}`">{{ item }}</li>
                    </ul>
                  </div>

                  <div v-if="conceptReviewPrompts(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">复习提示</p>
                    <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(item, index) in conceptReviewPrompts(card)" :key="`${card.resource_id}-review-${index}`">{{ item }}</li>
                    </ul>
                  </div>

                  <MarkdownContent
                    :content="conceptMarkdown(card)"
                    :mermaid-source="conceptMermaidSource(card)"
                  />
                </div>

                <div v-else-if="resourceType(card) === 'code_snippet'" class="space-y-4">
                  <div class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">场景说明</p>
                    <p class="mt-3 text-sm leading-7 text-text-secondary">{{ codeScenario(card) }}</p>
                  </div>

                  <div v-if="codePrerequisites(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">前置知识</p>
                    <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(item, index) in codePrerequisites(card)" :key="`${card.resource_id}-prereq-${index}`">{{ item }}</li>
                    </ul>
                  </div>

                  <div class="workspace-shell-card-soft rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">
                      {{ codeLanguage(card).toUpperCase() }}
                    </p>
                    <pre class="mt-3 overflow-x-auto rounded-[16px] border border-subtle/80 bg-[#08111f] px-4 py-3 text-xs leading-6 text-slate-100">{{ fullCode(card) }}</pre>
                  </div>

                  <div v-if="codeWalkthrough(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">逐步讲解</p>
                    <ol class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(item, index) in codeWalkthrough(card)" :key="`${card.resource_id}-walkthrough-${index}`">
                        {{ index + 1 }}. {{ item }}
                      </li>
                    </ol>
                  </div>

                  <MarkdownContent
                    v-if="codeExplanation(card)"
                    :content="codeExplanation(card)"
                  />

                  <div v-if="codeComplexityNotes(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">复杂度提示</p>
                    <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(item, index) in codeComplexityNotes(card)" :key="`${card.resource_id}-complexity-${index}`">{{ item }}</li>
                    </ul>
                  </div>

                  <div v-if="codePitfalls(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">常见坑点</p>
                    <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(item, index) in codePitfalls(card)" :key="`${card.resource_id}-pitfall-${index}`">{{ item }}</li>
                    </ul>
                  </div>

                  <div v-if="codeExperiments(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">延伸实验</p>
                    <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(item, index) in codeExperiments(card)" :key="`${card.resource_id}-experiment-${index}`">{{ item }}</li>
                    </ul>
                  </div>

                  <CodePracticePanel
                    v-if="hasPracticeBinding(card)"
                    :session-id="sessionId"
                    :node-id="currentNode"
                    :resource-id="resourceId(card)"
                    :problem-id="practiceProblemId(card)"
                    :starter-code="practiceStarterCode(card)"
                    :language="codeLanguage(card)"
                    @code-run="emit('code-run', $event)"
                    @code-submitted="emit('code-submitted', $event)"
                  />
                </div>

                <div v-else-if="resourceType(card) === 'interactive_exercise'" class="space-y-4">
                  <div class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">任务目标</p>
                    <p class="mt-2 text-sm leading-7 text-text-secondary">{{ exerciseGoal(card) }}</p>
                    <p class="mt-4 text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">任务说明</p>
                    <p class="text-sm font-medium text-text-primary">{{ exercisePrompt(card) }}</p>
                    <div v-if="exerciseSteps(card).length" class="mt-4 space-y-3">
                      <div
                        v-for="(step, stepIndex) in exerciseSteps(card)"
                        :key="`${card.resource_id}-step-${stepIndex}`"
                         class="workspace-shell-card-soft rounded-[16px] px-4 py-3"
                      >
                        <p class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">步骤 {{ stepIndex + 1 }}</p>
                        <p class="mt-2 text-sm leading-6 text-text-secondary">{{ step }}</p>
                      </div>
                    </div>
                  </div>

                  <div v-if="exerciseCheckpoints(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">检查点</p>
                    <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(checkpoint, checkpointIndex) in exerciseCheckpoints(card)" :key="`${card.resource_id}-checkpoint-${checkpointIndex}`">
                        {{ checkpoint }}
                      </li>
                    </ul>
                  </div>

                  <fieldset
                    v-if="reviewPracticeQuestion(card)"
                    class="workspace-shell-card p-4"
                    :disabled="reviewPracticeSubmitting"
                  >
                    <legend class="px-1 text-sm font-bold text-text-primary">定向练习题</legend>
                    <p :id="reviewPracticePromptId(card)" class="mt-2 text-sm leading-7 text-text-secondary">
                      {{ reviewPracticeQuestion(card).prompt }}
                    </p>
                    <div class="mt-4 grid gap-2" role="radiogroup" :aria-labelledby="reviewPracticePromptId(card)">
                      <label
                        v-for="(option, optionIndex) in reviewPracticeQuestion(card).options"
                        :key="`${reviewPracticeQuestion(card).id}-${optionIndex}`"
                        :for="reviewPracticeOptionId(card, optionIndex)"
                        class="focus-within:ring-primary flex min-h-11 cursor-pointer items-center gap-3 border border-subtle px-3 py-2 text-sm leading-6 text-text-secondary focus-within:ring-2"
                        :class="reviewPracticeAnswerIndex === optionIndex ? 'border-primary/40 bg-primary-soft text-text-primary' : 'bg-transparent hover:border-primary/25 hover:bg-card-hover'"
                      >
                        <input
                          :id="reviewPracticeOptionId(card, optionIndex)"
                          :name="reviewPracticeInputName(card)"
                          type="radio"
                          :value="optionIndex"
                          :checked="reviewPracticeAnswerIndex === optionIndex"
                          @change="selectReviewPracticeAnswer(card, optionIndex)"
                        >
                        <span>{{ option }}</span>
                      </label>
                    </div>
                    <p v-if="reviewPracticeError" class="mt-3 text-sm leading-6 text-error" role="alert">
                      {{ reviewPracticeError }}
                    </p>
                    <button
                      type="button"
                      class="workspace-shell-btn workspace-shell-btn--accent focus-ring mt-4 min-h-11 px-4 py-2 text-sm font-semibold"
                      :disabled="reviewPracticeAnswerIndex === null || reviewPracticeSubmitting"
                      @click="submitReviewPractice(card)"
                    >
                      {{ reviewPracticeSubmitting ? '验证练习中...' : reviewPracticeEventId ? '重试生成复测' : '提交练习并生成复测' }}
                    </button>
                  </fieldset>

                  <div v-if="exerciseHints(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">提示</p>
                    <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(hint, index) in exerciseHints(card)" :key="`${card.resource_id}-hint-${index}`">{{ hint }}</li>
                    </ul>
                  </div>

                  <div v-if="exerciseExpectedOutcome(card) || exerciseSolutionOutline(card)" class="grid gap-4 lg:grid-cols-2">
                    <div v-if="exerciseExpectedOutcome(card)" class="workspace-shell-card rounded-[20px] p-4">
                      <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">预期结果</p>
                      <p class="mt-3 text-sm leading-7 text-text-secondary">{{ exerciseExpectedOutcome(card) }}</p>
                    </div>
                    <div v-if="exerciseSolutionOutline(card)" class="workspace-shell-card rounded-[20px] p-4">
                      <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">参考思路</p>
                      <p class="mt-3 text-sm leading-7 text-text-secondary">{{ exerciseSolutionOutline(card) }}</p>
                    </div>
                  </div>

                  <CodePracticePanel
                    v-if="hasPracticeBinding(card)"
                    :session-id="sessionId"
                    :node-id="currentNode"
                    :resource-id="resourceId(card)"
                    :problem-id="practiceProblemId(card)"
                    :starter-code="practiceStarterCode(card)"
                    :language="exerciseLanguage(card)"
                    @code-run="emit('code-run', $event)"
                    @code-submitted="emit('code-submitted', $event)"
                  />
                </div>

                <div v-else-if="resourceType(card) === 'video_summary'" class="space-y-4">
                  <div class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-sm leading-7 text-text-secondary">{{ videoSummary(card) }}</p>
                    <ul v-if="videoKeyPoints(card).length" class="mt-4 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(point, pointIndex) in videoKeyPoints(card)" :key="`${card.resource_id}-point-${pointIndex}`">
                        {{ point }}
                      </li>
                    </ul>
                  </div>

                  <div v-if="videoTimeline(card).length" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">分段提纲</p>
                    <div class="mt-3 space-y-3">
                      <div v-for="(item, index) in videoTimeline(card)" :key="`${card.resource_id}-timeline-${index}`" class="workspace-shell-card-soft rounded-[16px] px-4 py-3">
                        <p class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">{{ item.label }}</p>
                        <p class="mt-2 text-sm leading-6 text-text-secondary">{{ item.summary }}</p>
                      </div>
                    </div>
                  </div>

                  <div v-if="videoWatchFocus(card).length || videoReviewQuestions(card).length" class="grid gap-4 lg:grid-cols-2">
                    <div v-if="videoWatchFocus(card).length" class="workspace-shell-card rounded-[20px] p-4">
                      <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">观看关注点</p>
                      <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                        <li v-for="(item, index) in videoWatchFocus(card)" :key="`${card.resource_id}-watch-${index}`">{{ item }}</li>
                      </ul>
                    </div>
                    <div v-if="videoReviewQuestions(card).length" class="workspace-shell-card rounded-[20px] p-4">
                      <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">复习问题</p>
                      <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                        <li v-for="(item, index) in videoReviewQuestions(card)" :key="`${card.resource_id}-review-q-${index}`">{{ item }}</li>
                      </ul>
                    </div>
                  </div>

                  <a
                    v-if="videoUrl(card)"
                    :href="videoUrl(card)"
                    target="_blank"
                    rel="noreferrer"
                    class="workspace-shell-btn workspace-shell-btn--secondary px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.10em]"
                  >
                    打开视频链接
                  </a>
                </div>

                <div v-else-if="resourceType(card) === 'diagnostic_quiz'" class="space-y-4">
                  <div v-if="quizGuidance(card)" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">作答建议</p>
                    <p class="mt-3 text-sm leading-7 text-text-secondary">{{ quizGuidance(card) }}</p>
                  </div>

                  <div
                    v-for="question in quizQuestions"
                    :key="question.id"
                    class="workspace-shell-card rounded-[20px] p-4"
                  >
                    <p class="text-sm font-medium text-text-primary">{{ question.prompt }}</p>
                    <p v-if="question.skillTag || question.difficulty" class="mt-2 text-[11px] leading-5 text-text-muted">
                      {{ [question.skillTag, question.difficulty].filter(Boolean).join(" · ") }}
                    </p>
                    <div class="mt-3 space-y-2">
                      <button
                        v-for="(option, optionIndex) in question.options"
                        :key="`${question.id}-${optionIndex}`"
                        type="button"
                        class="focus-ring min-h-11 w-full rounded-[14px] border px-3 py-2.5 text-left text-sm font-light transition-all duration-200 active:scale-[0.99]"
                        :class="answerClass(question.id, optionIndex)"
                        :disabled="questionSubmitted(question.id) || questionSubmissionPending(question.id) || quizSubmitted || quizSubmitting"
                        @click="setAnswer(card, question.id, optionIndex)"
                      >
                        {{ option }}
                      </button>
                    </div>
                    <div class="mt-3 flex justify-end">
                      <p v-if="questionSubmitted(question.id)" class="mr-auto self-center text-[11px] font-medium text-success">Answer saved</p>
                      <p v-else-if="questionSubmissionPending(question.id)" class="mr-auto self-center text-[11px] font-medium text-text-muted">Saving answer</p>
                      <button
                        type="button"
                        class="workspace-shell-btn focus-ring min-h-11 px-3 py-2 text-[11px] font-semibold"
                        :disabled="!canSubmitQuestion(question)"
                        @click="submitQuestionAnswer(card, question)"
                      >
                        {{ questionSubmitted(question.id) ? 'Saved' : questionSubmissionPending(question.id) ? 'Saving...' : 'Submit answer' }}
                      </button>
                    </div>
                    <p v-if="questionSubmissionErrors[question.id]" class="mt-2 text-xs text-error" role="alert">
                      {{ questionSubmissionErrors[question.id] }}
                    </p>
                    <div v-if="quizSubmitted && question.explanation" class="mt-3 workspace-shell-card-soft rounded-[16px] px-4 py-3">
                      <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">题目解释</p>
                      <p class="mt-2 text-sm leading-6 text-text-secondary">{{ question.explanation }}</p>
                    </div>
                  </div>

                  <div class="workspace-shell-card flex flex-wrap items-center justify-between gap-3 rounded-[20px] p-4">
                    <div class="text-sm font-light text-text-muted">
                      {{ diagnosticStatusText }}
                    </div>
                    <button
                      type="button"
                      class="focus-ring btn-capsule min-h-11"
                      :disabled="!canSubmitQuiz"
                      @click="submitQuizAnswers"
                    >
                      {{ quizSubmitLabel }}
                    </button>
                  </div>

                  <p v-if="quizSubmissionError" class="text-sm text-error" role="alert">
                    {{ quizSubmissionError }}
                  </p>

                  <div v-if="quizAfterGuidance(card) && quizSubmitted && !quizSubmissionError" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">提交后建议</p>
                    <p class="mt-3 text-sm leading-7 text-text-secondary">{{ quizAfterGuidance(card) }}</p>
                  </div>
                </div>

                <MarkdownContent
                  v-else
                  :content="bodyMarkdown(card)"
                />

                <ResourceAnnotations
                  :annotations="annotationsFor(card)"
                  :can-highlight="Boolean(card.resource_id && currentNode)"
                  :selected-text="selectedTextFor(card)"
                  :is-bookmarked="isBookmarked(card)"
                  @save-note="saveNoteAnnotation(card, $event)"
                  @save-highlight="saveHighlightAnnotation(card, $event)"
                  @remove="removeAnnotation"
                />
              </div>
            </template>
          </ResourceCard>
          </template><!-- end alias -->
          </div><!-- end existing-card slot -->

          <!-- Case 2: empty slot — show placeholder with generate button -->
          <div
            v-else
            :data-resource-type="slot.type"
            class="animate-cardIn h-full min-h-[240px] transition-all duration-300"
            :style="{ animationDelay: `${index * 40}ms` }"
            :class="getGridSpanClass(slot.type)"
          >
            <div
              class="slot-empty group h-full rounded-[22px] border border-dashed border-subtle/50 bg-space-elevated/40 flex flex-col items-center justify-center gap-4 p-6"
              :style="{ '--rail-accent': slot.color }"
              :aria-busy="isSlotPending(slot) ? 'true' : undefined"
            >
              <template v-if="isSlotPending(slot)">
                <div class="w-full max-w-[16rem] space-y-3" role="status" aria-live="polite">
                  <div class="h-3 w-2/5 overflow-hidden rounded bg-card">
                    <div class="h-full w-1/2 animate-shimmer bg-gradient-to-r from-transparent via-[var(--text-muted)]/10 to-transparent" />
                  </div>
                  <div class="h-4 w-full overflow-hidden rounded bg-card">
                    <div class="h-full w-1/2 animate-shimmer bg-gradient-to-r from-transparent via-[var(--text-muted)]/10 to-transparent" />
                  </div>
                  <div class="h-4 w-4/5 overflow-hidden rounded bg-card">
                    <div class="h-full w-1/2 animate-shimmer bg-gradient-to-r from-transparent via-[var(--text-muted)]/10 to-transparent" />
                  </div>
                  <p class="pt-1 text-center text-[11px] text-text-muted">{{ slotProgressText(slot) }}</p>
                </div>
              </template>

              <template v-else>
                <span class="slot-empty-icon text-[2.25rem] opacity-40 group-hover:opacity-75 transition-opacity duration-300"
                      :style="{ animationDelay: `${index * 0.4}s` }"
                      aria-hidden="true">{{ slot.icon }}</span>
                <div class="text-center space-y-0.5">
                  <p class="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-text-muted">{{ slot.label }}</p>
                  <p class="text-[11px] text-text-muted opacity-50">{{ slotErrorText(slot) || "尚未生成" }}</p>
                </div>
                <button
                  v-if="currentNode"
                  type="button"
                  class="btn-ripple workspace-shell-btn workspace-shell-btn--accent focus-ring px-4 py-2 text-[11px] font-semibold tracking-[0.06em] opacity-0 group-hover:opacity-100 translate-y-1 group-hover:translate-y-0 transition-all duration-200"
                  @click="$emit('generate-card', { nodeId: currentNode, cardType: slot.type })"
                >
                  {{ isSlotFailed(slot) ? "重试生成" : "生成" }}
                </button>
              </template>
>>>>>>> origin/main
            </div>
          </div>
        </template>
      </div>

      <!-- 单类型：大页面式 -->
      <div v-else class="space-y-6">
        <template v-for="slot in cardTypeSlots" :key="slot.type">
          <div v-if="slot.card && !minimizedIds.includes(slot.card.resource_id)" class="rounded-xl border border-subtle bg-card p-6">
            <template v-for="card of [slot.card]" :key="slot.type">
              <div class="flex items-center gap-3 mb-5">
                <span class="text-xs font-semibold text-text-muted">{{ slot.label }}</span>
                <span class="h-px flex-1 bg-subtle" />
              </div>
              <article v-if="resourceType(card) === 'concept_map'" class="text-sm leading-7 text-text-secondary">
                <p class="text-text-primary">{{ conceptSummary(card) }}</p>
                <template v-if="conceptSections(card).length"><section v-for="(section, index) in conceptSections(card)" :key="'sec-'+index" class="mt-10"><h3 class="text-base font-semibold text-text-primary">{{ section.heading }}</h3><p class="mt-3">{{ section.body }}</p></section></template>
                <ul v-if="conceptObjectives(card).length" class="mt-10 space-y-2"><li v-for="(item, index) in conceptObjectives(card)" :key="'obj-'+index">{{ index + 1 }}. {{ item }}</li></ul>
                <ul v-if="conceptBullets(card).length" class="mt-10 space-y-2"><li v-for="item in conceptBullets(card)" :key="'b-'+item">{{ item }}</li></ul>
                <MarkdownContent v-if="conceptMermaidSource(card)" class="mt-10" :content="''" :mermaid-source="conceptMermaidSource(card)" />
                <ul v-if="conceptMisconceptions(card).length" class="mt-10 space-y-2"><li v-for="item in conceptMisconceptions(card)" :key="'mis-'+item" class="text-text-muted text-xs">* {{ item }}</li></ul>
                <ul v-if="conceptReviewPrompts(card).length" class="mt-10 space-y-2"><li v-for="(item, index) in conceptReviewPrompts(card)" :key="'rev-'+index">{{ index + 1 }}. {{ item }}</li></ul>
              </article>
              <article v-else-if="resourceType(card) === 'code_snippet'" class="text-sm leading-7 text-text-secondary">
                <p>{{ codeScenario(card) }}</p>
                <ul v-if="codePrerequisites(card).length" class="mt-10 space-y-2"><li v-for="item in codePrerequisites(card)" :key="'pre-'+item">{{ item }}</li></ul>
                <div class="mt-10 overflow-hidden rounded-lg border border-subtle bg-[#0d1117]"><div class="px-4 py-2 border-b border-white/5"><span class="text-xs text-slate-400">{{ codeLanguage(card) }}</span></div><pre class="overflow-x-auto p-4 text-[13px] leading-6 text-slate-100"><code>{{ fullCode(card) }}</code></pre></div>
                <MarkdownContent v-if="codeExplanation(card)" class="mt-10" :content="codeExplanation(card)" />
                <ol v-if="codeWalkthrough(card).length" class="mt-10 space-y-3"><li v-for="(item, index) in codeWalkthrough(card)" :key="'walk-'+index" :value="index + 1">{{ item }}</li></ol>
                <ul v-if="codeComplexityNotes(card).length" class="mt-10 space-y-2"><li v-for="item in codeComplexityNotes(card)" :key="'cx-'+item">{{ item }}</li></ul>
                <ul v-if="codePitfalls(card).length" class="mt-10 space-y-2"><li v-for="item in codePitfalls(card)" :key="'pit-'+item" class="text-text-muted text-xs">* {{ item }}</li></ul>
                <ul v-if="codeExperiments(card).length" class="mt-10 space-y-2"><li v-for="item in codeExperiments(card)" :key="'exp-'+item">{{ item }}</li></ul>
              </article>
              <article v-else-if="resourceType(card) === 'interactive_exercise'" class="text-sm leading-7 text-text-secondary">
                <p class="text-text-primary font-medium">{{ exerciseGoal(card) }}</p><p class="mt-4">{{ exercisePrompt(card) }}</p>
                <ol v-if="exerciseSteps(card).length" class="mt-10 space-y-4"><li v-for="(step, stepIndex) in exerciseSteps(card)" :key="'step-'+stepIndex" :value="stepIndex + 1"><p>{{ step }}</p></li></ol>
                <ul v-if="exerciseCheckpoints(card).length" class="mt-10 space-y-2"><li v-for="item in exerciseCheckpoints(card)" :key="'cp-'+item">{{ item }}</li></ul>
                <ul v-if="exerciseHints(card).length" class="mt-10 space-y-2"><li v-for="(hint, index) in exerciseHints(card)" :key="'hint-'+index" class="text-text-muted text-xs">{{ index + 1 }}. {{ hint }}</li></ul>
                <div v-if="exerciseExpectedOutcome(card) || exerciseSolutionOutline(card)" class="mt-10 grid gap-8 sm:grid-cols-2"><div v-if="exerciseExpectedOutcome(card)"><h4 class="text-xs font-semibold text-text-muted mb-2">预期结果</h4><p>{{ exerciseExpectedOutcome(card) }}</p></div><div v-if="exerciseSolutionOutline(card)"><h4 class="text-xs font-semibold text-text-muted mb-2">参考思路</h4><p>{{ exerciseSolutionOutline(card) }}</p></div></div>
              </article>
              <article v-else-if="resourceType(card) === 'video_summary'" class="text-sm leading-7 text-text-secondary">
                <p>{{ videoSummary(card) }}</p>
                <ul v-if="videoKeyPoints(card).length" class="mt-10 space-y-2"><li v-for="point in videoKeyPoints(card)" :key="'kp-'+point">{{ point }}</li></ul>
                <div v-if="videoTimeline(card).length" class="mt-10 space-y-4"><div v-for="item in videoTimeline(card)" :key="'tl-'+item.label"><span class="text-xs font-medium text-text-muted">{{ item.label }}</span><p class="mt-1">{{ item.summary }}</p></div></div>
                <div v-if="videoWatchFocus(card).length || videoReviewQuestions(card).length" class="mt-10 grid gap-8 sm:grid-cols-2"><ul v-if="videoWatchFocus(card).length" class="space-y-2"><li v-for="item in videoWatchFocus(card)" :key="'wf-'+item">{{ item }}</li></ul><ul v-if="videoReviewQuestions(card).length" class="space-y-2"><li v-for="(item, index) in videoReviewQuestions(card)" :key="'rq-'+index">{{ index + 1 }}. {{ item }}</li></ul></div>
                <a v-if="videoUrl(card)" :href="videoUrl(card)" target="_blank" rel="noreferrer" class="inline-block mt-10 text-xs font-medium text-primary hover:underline">打开视频链接 &rarr;</a>
              </article>
              <article v-else-if="resourceType(card) === 'diagnostic_quiz'" class="text-sm leading-7 text-text-secondary">
                <p v-if="quizGuidance(card)" class="text-text-muted">{{ quizGuidance(card) }}</p>
                <div v-for="question in quizQuestions" :key="question.id" class="mt-10"><p class="font-medium text-text-primary">{{ question.prompt }}</p><p v-if="question.skillTag || question.difficulty" class="mt-1 text-xs text-text-muted">{{ [question.skillTag, question.difficulty].filter(Boolean).join(" · ") }}</p><div class="mt-4 space-y-2"><button v-for="(option, optionIndex) in question.options" :key="`${question.id}-${optionIndex}`" type="button" class="focus-ring w-full rounded-lg border px-4 py-2.5 text-left text-sm transition-colors" :class="answerClass(question.id, optionIndex)" @click="setAnswer(question.id, optionIndex)">{{ option }}</button></div><div v-if="submittedScore !== null && question.explanation" class="mt-4 text-xs text-text-muted">{{ question.explanation }}</div></div>
                <div class="mt-10 flex flex-wrap items-center justify-between gap-3"><p class="text-xs text-text-muted">{{ diagnosticStatusText }}</p><button type="button" class="focus-ring btn-capsule" :disabled="!allAnswered || loading" @click="submitQuizScore">提交诊断</button></div>
                <p v-if="quizAfterGuidance(card) && submittedScore !== null" class="mt-8">{{ quizAfterGuidance(card) }}</p>
              </article>
              <MarkdownContent v-else :content="bodyMarkdown(card)" />
            </template>
          </div>
          <div v-else class="rounded-xl border border-dashed border-subtle/30 p-8 flex flex-col items-center justify-center gap-3">
            <span class="text-3xl opacity-30" aria-hidden="true">{{ slot.icon }}</span>
            <p class="text-xs text-text-muted">{{ slot.label }} · 尚未生成</p>
            <button v-if="currentNode" type="button" class="focus-ring rounded-lg border border-subtle px-4 py-2 text-xs text-text-muted hover:text-text-primary hover:border-primary/30 transition-colors" @click="$emit('generate-card', { nodeId: currentNode, cardType: slot.type })">生成</button>
          </div>
        </template>
      </div>

    </div>

  </section>
</template>

<script setup>
import { computed, defineAsyncComponent, nextTick, ref, watch } from "vue";
import MarkdownContent from "./MarkdownContent.vue";
import ResourceAnnotations from "./ResourceAnnotations.vue";
import ResourceCard from "./ResourceCard.vue";
import { useLearningAssetsStore } from "../stores/learningAssets";
import { extractCodePreview, extractTextPreview } from "../utils/markdownPreview.js";

const CodePracticePanel = defineAsyncComponent(() => import("./CodePracticePanel.vue"));

const props = defineProps({
  cards: { type: Array, default: () => [] },
  sessionId: { type: String, default: "" },
  currentNode: { type: String, default: "" },
  nodeTitle: { type: String, default: "" },
  pathNodes: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  cardStates: { type: Object, default: () => ({}) },
  overallProgress: { type: Number, default: 0 },
  masteredCount: { type: Number, default: 0 },
  lastDiagnostic: { type: Object, default: null },
  focusCardType: { type: String, default: "" },
  reviewItemId: { type: String, default: "" },
  reviewPhase: { type: String, default: "" },
  filterType: { type: String, default: "all" },
  getCardLabel: { type: Function, required: true },
  getAgentLabel: { type: Function, required: true },
  buildQuiz: { type: Function, required: true },
});

<<<<<<< HEAD
const emit = defineEmits(["submit-quiz", "select-node", "refresh", "generate-card", "filter-change"]);
=======
const emit = defineEmits([
  "submit-quiz",
  "select-node",
  "refresh",
  "generate-card",
  "answer-selected",
  "content-viewed",
  "hint-requested",
  "code-run",
  "code-submitted",
  "open-review",
  "prepare-review-retest",
]);
>>>>>>> origin/main

const orderedIds = ref([]);
const activeCardId = ref("");
const activeCardTypeHint = ref("");
const focusMode = ref(false);
const answers = ref({});
<<<<<<< HEAD
const submittedScore = ref(null);
const quizAttemptNumber = ref(1);
const quizStartedAt = ref(Date.now());
const quizEventId = ref("");
=======
const hydratedCardIds = ref([]);
>>>>>>> origin/main
const scrollViewport = ref(null);
const nodeScroller = ref(null);
const nodeButtonRefs = new Map();
const selectedNodeId = ref(props.currentNode);
const selectedTextByResource = ref({});
const learningAssets = useLearningAssetsStore();
const quizSubmitting = ref(false);
const quizSubmitted = ref(false);
const quizSubmissionError = ref("");
const quizStartedAt = ref(0);
const submittedQuestionIds = ref([]);
const submittingQuestionIds = ref([]);
const questionSubmissionErrors = ref({});
const quizAttemptsByResource = ref({});
const quizUsedHintByResource = ref({});
const reviewPracticeAnswerIndex = ref(null);
const reviewPracticeAttemptNumber = ref(1);
const reviewPracticeSubmitting = ref(false);
const reviewPracticeError = ref("");
const reviewPracticeEventId = ref("");
const reviewPracticeStartedAt = ref(0);

watch(
  [() => props.currentNode, () => props.loading, () => props.pathNodes.length],
  async ([nodeId, loading]) => {
    if (nodeId) {
      selectedNodeId.value = nodeId;
    }

    if (loading || !nodeId) {
      return;
    }

    await nextTick();
    alignNodeToLeft(nodeId);
  },
  { immediate: true, flush: "post" },
);

// ── 5-type slot system ─────────────────────────────────────────────────
const CARD_TYPES = [
  { type: "concept_map",          label: "概念导图", filterLabel: "概念", icon: "🗺", sidebarKey: "concept",  color: "var(--learning-concept)" },
  { type: "code_snippet",         label: "代码示例", filterLabel: "代码", icon: "💻", sidebarKey: "code",     color: "var(--learning-code)" },
  { type: "interactive_exercise", label: "互动练习", filterLabel: "练习", icon: "✏️", sidebarKey: "practice", color: "var(--learning-practice)" },
  { type: "video_summary",        label: "视频摘要", filterLabel: "视频", icon: "🎬", sidebarKey: "video",    color: "var(--learning-video)" },
  { type: "diagnostic_quiz",      label: "诊断测验", filterLabel: "测验", icon: "📋", sidebarKey: "quiz",     color: "var(--learning-quiz)" },
];

const resourceFilterItems = computed(() => [
  { key: "all", label: "全部", count: props.cards.length },
  ...CARD_TYPES.map((item) => ({
    key: item.sidebarKey,
    label: item.filterLabel,
    count: props.cards.filter((card) => resourceType(card) === item.type).length,
  })),
]);

/** Map card_type → latest card */
const cardsByType = computed(() => {
  const map = {};
  for (const card of props.cards) {
    const t = resourceType(card);
    if (t) map[t] = card;
  }
  return map;
});

/**
 * Visible slots after applying filterType.
 * "all" → all 5 types; otherwise only the matching type.
 */
const cardTypeSlots = computed(() => {
<<<<<<< HEAD
  let filtered = props.filterType && props.filterType !== "all"
    ? CARD_TYPES.filter((m) => m.sidebarKey === props.filterType)
    : CARD_TYPES;

  if (focusMode.value && activeCardId.value) {
    const activeType = resourceType(props.cards.find((card) => card.resource_id === activeCardId.value));
    filtered = filtered.filter((meta) => meta.type === activeType);
  }

  return filtered.map((meta) => ({
=======
  const filtered = props.filterType && props.filterType !== "all"
    ? CARD_TYPES.filter((meta) => meta.sidebarKey === props.filterType)
    : CARD_TYPES;
  const visibleTypes = filtered.length ? filtered : CARD_TYPES;
  return visibleTypes.map((meta) => ({
>>>>>>> origin/main
    ...meta,
    card: cardsByType.value[meta.type] ?? null,
    state: props.cardStates?.[meta.type] ?? { status: cardsByType.value[meta.type] ? "ready" : "idle" },
  }));
});

<<<<<<< HEAD
const singleCardId = computed(() => {
  if (cardTypeSlots.value.length !== 1) {
    return "";
  }

  const cardId = cardTypeSlots.value[0].card?.resource_id ?? "";
  return minimizedIds.value.includes(cardId) ? "" : cardId;
});

const isSingleCardView = computed(() => Boolean(singleCardId.value));

watch(
  () => props.filterType,
  () => {
    focusMode.value = false;
  },
);
=======
const canvasContextKey = computed(() => [
  props.sessionId,
  props.currentNode,
].join("|"));

const cardsIdentityKey = computed(() => props.cards
  .map((card) => card.resource_id || card.id || "")
  .filter(Boolean)
  .join("|"));

const cardsAndReviewKey = computed(() => [
  cardsIdentityKey.value,
  props.reviewItemId,
  props.reviewPhase,
].join("|"));

let lastQuizResourceId = "";
let lastReviewPracticeProgressKey = "";

function syncCardsWithoutReset() {
  const cards = props.cards;
  const nextIds = cards.map((card) => resourceId(card)).filter(Boolean);
  orderedIds.value = nextIds;

  if (!nextIds.includes(activeCardId.value)) {
    const savedCardId = restoreCanvasState(nextIds);
    const replacementCard = cards.find((card) => resourceType(card) === activeCardTypeHint.value);
    activeCardId.value = savedCardId || resourceId(replacementCard) || nextIds[0] || "";
    activeCardTypeHint.value = resourceType(cards.find((card) => resourceId(card) === activeCardId.value));
    hydrateCard(activeCardId.value);
  }

  const nextQuiz = cards.find((card) => resourceType(card) === "diagnostic_quiz");
  const nextQuizResourceId = resourceId(nextQuiz);
  if (nextQuizResourceId && nextQuizResourceId !== lastQuizResourceId) {
    lastQuizResourceId = nextQuizResourceId;
    restoreQuizProgress(nextQuizResourceId);
  }

  const reviewKey = reviewPracticeProgressKey();
  if (reviewKey && reviewKey !== lastReviewPracticeProgressKey) {
    lastReviewPracticeProgressKey = reviewKey;
    restoreReviewPracticeProgress();
  }
}
>>>>>>> origin/main

watch(
  canvasContextKey,
  () => {
    const cards = props.cards;
    const nextIds = cards.map((card) => resourceId(card)).filter(Boolean);
    orderedIds.value = nextIds;
<<<<<<< HEAD
    minimizedIds.value = [];
    activeCardId.value = nextIds[0] ?? "";
    focusMode.value = false;
  },
  { immediate: true },
);

watch(
  singleCardId,
  (cardId) => {
    if (cardId) {
      setActiveCard(cardId);
=======
    hydratedCardIds.value = [];
    focusMode.value = false;
    answers.value = {};
    submittedQuestionIds.value = [];
    submittingQuestionIds.value = [];
    questionSubmissionErrors.value = {};
    quizSubmitting.value = false;
    quizSubmitted.value = false;
    quizSubmissionError.value = "";
    quizStartedAt.value = 0;
    quizAttemptsByResource.value = {};
    quizUsedHintByResource.value = {};
    reviewPracticeAnswerIndex.value = null;
    reviewPracticeAttemptNumber.value = 1;
    reviewPracticeSubmitting.value = false;
    reviewPracticeError.value = "";
    reviewPracticeEventId.value = "";
    reviewPracticeStartedAt.value = 0;
    lastQuizResourceId = "";
    lastReviewPracticeProgressKey = "";

    const savedCardId = restoreCanvasState(nextIds);
    activeCardId.value = savedCardId || nextIds[0] || "";
    activeCardTypeHint.value = resourceType(cards.find((card) => resourceId(card) === activeCardId.value));
    hydrateCard(activeCardId.value);

    const nextQuiz = cards.find((card) => resourceType(card) === "diagnostic_quiz");
    lastQuizResourceId = resourceId(nextQuiz);
    if (lastQuizResourceId) restoreQuizProgress(lastQuizResourceId);
    const reviewKey = reviewPracticeProgressKey();
    if (reviewKey) {
      lastReviewPracticeProgressKey = reviewKey;
      restoreReviewPracticeProgress();
>>>>>>> origin/main
    }
  },
  { immediate: true },
);

watch(cardsAndReviewKey, syncCardsWithoutReset);

const sortedCards = computed(() => {
  const orderIndex = new Map(orderedIds.value.map((id, index) => [id, index]));
  const latestByType = new Map();
  const extras = [];

  [...props.cards]
    .sort(
      (left, right) =>
        (orderIndex.get(left.resource_id) ?? Number.MAX_SAFE_INTEGER) -
        (orderIndex.get(right.resource_id) ?? Number.MAX_SAFE_INTEGER),
    )
    .forEach((card) => {
      if (["concept_map", "code_snippet", "interactive_exercise", "video_summary", "diagnostic_quiz"].includes(resourceType(card))) {
        latestByType.set(resourceType(card), card);
      } else {
        extras.push(card);
      }
    });

  const ordered = ["concept_map", "code_snippet", "interactive_exercise", "video_summary", "diagnostic_quiz"]
    .map((cardType) => latestByType.get(cardType))
    .filter(Boolean);

  return [...ordered, ...extras];
});

const quizCard = computed(() =>
  sortedCards.value.find((card) => resourceType(card) === "diagnostic_quiz"),
);

watch(
  [() => props.currentNode, () => quizCard.value?.resource_id ?? quizCard.value?.id ?? ""],
  () => {
    answers.value = {};
    submittedScore.value = null;
    quizAttemptNumber.value = 1;
    quizStartedAt.value = Date.now();
    quizEventId.value = "";
  },
);

const quizQuestions = computed(() => {
  const structuredQuestions = structuredPayload(quizCard.value)?.questions;
  if (Array.isArray(structuredQuestions) && structuredQuestions.length) {
    return structuredQuestions.map((question) => ({
      id: question.id,
      prompt: question.prompt,
      options: question.options || [],
      answerIndex: question.answer_index ?? question.answerIndex ?? 0,
      explanation: question.explanation || "",
      skillTag: question.skill_tag || "",
      difficulty: question.difficulty || "",
    }));
  }

  return props.buildQuiz(bodyMarkdown(quizCard.value)).map((question) => ({
    id: question.id,
    prompt: question.prompt,
    options: question.options,
    answerIndex: question.answer ?? 0,
    explanation: "",
    skillTag: "",
    difficulty: "",
  }));
});
const allAnswered = computed(
  () => quizQuestions.value.length > 0 && quizQuestions.value.every((question) => answers.value[question.id] !== undefined),
);
const allQuestionsSubmitted = computed(
  () => quizQuestions.value.length > 0 && quizQuestions.value.every((question) => questionSubmitted(question.id)),
);
const canSubmitQuiz = computed(() => (
  allQuestionsSubmitted.value
  && !props.loading
  && !quizSubmitting.value
  && (!quizSubmitted.value || Boolean(quizSubmissionError.value))
));
const quizSubmitLabel = computed(() => {
  if (quizSubmitting.value) return "提交中...";
  if (quizSubmissionError.value) return "重新提交诊断";
  if (quizSubmitted.value) return "诊断已提交";
  if (allAnswered.value && !allQuestionsSubmitted.value) return "Submit each answer";
  return "提交诊断";
});

const currentNodeMeta = computed(() =>
  props.pathNodes.find((node) => node.id === props.currentNode),
);

const currentMastery = computed(() =>
  Math.round((currentNodeMeta.value?.mastery ?? 0) * 100),
);

<<<<<<< HEAD
const resourceGuidance = computed(() => ({
  concept: "概念导图帮助你建立当前知识点的整体结构。",
  code: "代码示例帮助你理解知识点如何落到实际实现。",
  practice: "互动练习帮助你通过应用与反思巩固理解。",
  video: "视频摘要帮助你快速回顾当前知识点的核心内容。",
  quiz: "诊断测验用于检验掌握程度并发现薄弱环节。",
  all: "多种学习资源共同支持理解、实践与诊断的完整过程。",
}[props.filterType] ?? "当前资源帮助你理解并掌握这个知识点。"));
=======
const activeCardType = computed(() => {
  const activeCard = sortedCards.value.find((card) => resourceId(card) === activeCardId.value);
  return resourceType(activeCard) || activeCardTypeHint.value;
});

const activeCardTitle = computed(() => {
  const activeCard = sortedCards.value.find((card) => card.resource_id === activeCardId.value) ?? sortedCards.value[0];
  return activeCard ? cardLabel(resourceType(activeCard)) : "当前内容";
});
>>>>>>> origin/main

const isAllCardsPending = computed(() => CARD_TYPES.every((meta) => isCardPending(meta.type)));

const nextPendingNode = computed(() =>
  props.pathNodes.find((node) => (node.mastery ?? 0) < 0.65 && node.id !== props.currentNode) ?? null,
);

const learningTone = computed(() => {
  if (props.loading) return "资源装配中";
  if (!props.cards.length) return "等待资源";
  if (currentMastery.value >= 65) return "节点达标";
  return "继续学习";
});

const diagnosticStatusText = computed(() => {
  if (props.lastDiagnostic) {
    const scorePercent = Math.round((props.lastDiagnostic.score ?? 0) * 100);
    const beforePercent = Math.round((props.lastDiagnostic.masteryBefore ?? 0) * 100);
    const afterPercent = Math.round((props.lastDiagnostic.masteryAfter ?? 0) * 100);
    if (props.lastDiagnostic.advancedToNextNode) {
      return `上次诊断得分 ${scorePercent}% · 掌握度 ${beforePercent}% -> ${afterPercent}% · 已推进到 ${props.lastDiagnostic.nextNodeTitle || "下一节点"}`;
    }
    return `上次诊断得分 ${scorePercent}% · 掌握度 ${beforePercent}% -> ${afterPercent}% · 继续停留当前节点`;
  }

  if (quizSubmitting.value) return "诊断结果正在等待服务端确认。";
  if (quizSubmissionError.value) return "诊断尚未确认，请使用原答案重试。";
  if (quizSubmitted.value) return "服务端已确认本次诊断。";

  return "请先回答所有题目，再提交诊断得分。";
});

function resourceType(card) {
  return card?.resource_type || card?.card_type || card?.type || "";
}

function resourceId(card) {
  return card?.resource_id || card?.id || "";
}

function cardState(cardType) {
  return props.cardStates?.[cardType] ?? { status: cardsByType.value[cardType] ? "ready" : "idle" };
}

function isCardPending(cardType) {
  return ["waiting", "queued"].includes(cardState(cardType).status);
}

function isSlotPending(slot) {
  return isCardPending(slot.type);
}

function isSlotFailed(slot) {
  return cardState(slot.type).status === "failed";
}

function slotErrorText(slot) {
  return isSlotFailed(slot) ? "生成失败，可重试" : "";
}

function slotProgressText(slot) {
  if (cardState(slot.type).status === "waiting") return "等待概念图就绪";
  if (isSlotPending(slot)) return "资源生成中";
  if (isSlotFailed(slot)) return "生成失败";
  return "资源就绪";
}

function bodyMarkdown(card) {
  return card?.body_markdown || card?.content || "";
}

function structuredPayload(card) {
  return card?.structured_payload || card?.metadata || {};
}
function cardMetadata(card) {
  return structuredPayload(card);
}

function previewText(card) {
  const metadata = cardMetadata(card);
  if (resourceType(card) === "concept_map") {
    return metadata.summary || textPreview(bodyMarkdown(card));
  }
  if (resourceType(card) === "interactive_exercise") {
    return metadata.prompt || textPreview(bodyMarkdown(card));
  }
  if (resourceType(card) === "video_summary") {
    return metadata.summary || textPreview(bodyMarkdown(card));
  }
  if (resourceType(card) === "diagnostic_quiz") {
    return quizQuestions.value[0]?.prompt || textPreview(bodyMarkdown(card));
  }
  return textPreview(bodyMarkdown(card));
}

function previewCode(card) {
  const metadata = cardMetadata(card);
  return metadata.code ? extractCodePreview(`\`\`\`\n${metadata.code}\n\`\`\``, 8) : codePreview(bodyMarkdown(card));
}

function conceptMarkdown(card) {
  const metadata = cardMetadata(card);
  if (!metadata.title && !metadata.summary && !Array.isArray(metadata.bullets)) {
    return bodyMarkdown(card);
  }

  const sections = Array.isArray(metadata.sections)
    ? `\n\n${metadata.sections.map((section) => `### ${section.heading}\n${section.body}`).join("\n\n")}`
    : "";
  const bullets = Array.isArray(metadata.bullets) && metadata.bullets.length
    ? `\n\n${metadata.bullets.map((bullet) => `- ${bullet}`).join("\n")}`
    : "";
  return `## ${metadata.title || cardLabel(resourceType(card))}\n\n${metadata.summary || ""}${sections}${bullets}`.trim();
}

function conceptMermaidSource(card) {
  return cardMetadata(card).mermaid_source || "";
}

function conceptSummary(card) {
  return cardMetadata(card).summary || textPreview(bodyMarkdown(card));
}

function conceptObjectives(card) {
  return Array.isArray(cardMetadata(card).learning_objectives) ? cardMetadata(card).learning_objectives : [];
}

function conceptSections(card) {
  return Array.isArray(cardMetadata(card).sections) ? cardMetadata(card).sections : [];
}

function conceptBullets(card) {
  return Array.isArray(cardMetadata(card).bullets) ? cardMetadata(card).bullets : [];
}

function conceptMisconceptions(card) {
  return Array.isArray(cardMetadata(card).common_misconceptions) ? cardMetadata(card).common_misconceptions : [];
}

function conceptReviewPrompts(card) {
  return Array.isArray(cardMetadata(card).review_prompts) ? cardMetadata(card).review_prompts : [];
}

function codeLanguage(card) {
  return cardMetadata(card).language || "python";
}

function practiceProblemId(card) {
  const metadata = cardMetadata(card);
  return metadata.practice?.problem_id
    || metadata.practice?.id
    || metadata.practice_problem_id
    || metadata.problem_id
    || "";
}

function practiceStarterCode(card) {
  const metadata = cardMetadata(card);
  return metadata.practice?.starter_code
    || metadata.starter_code
    || metadata.code_template
    || metadata.template
    || "";
}

function exerciseLanguage(card) {
  const metadata = cardMetadata(card);
  return metadata.practice?.language || metadata.language || "python";
}

function hasPracticeBinding(card) {
  if (resourceType(card) === "code_snippet") return true;
  const metadata = cardMetadata(card);
  return Boolean(
    metadata.practice?.problem_id
    || metadata.practice?.id
    || metadata.practice_problem_id
    || metadata.problem_id,
  );
}

function fullCode(card) {
  return cardMetadata(card).code || extractCodePreview(bodyMarkdown(card), 40);
}

function codeExplanation(card) {
  return cardMetadata(card).explanation || "";
}

function codeScenario(card) {
  return cardMetadata(card).scenario || codeExplanation(card) || textPreview(bodyMarkdown(card));
}

function codePrerequisites(card) {
  return Array.isArray(cardMetadata(card).prerequisites) ? cardMetadata(card).prerequisites : [];
}

function codeWalkthrough(card) {
  return Array.isArray(cardMetadata(card).walkthrough_steps) ? cardMetadata(card).walkthrough_steps : [];
}

function codeComplexityNotes(card) {
  return Array.isArray(cardMetadata(card).complexity_notes) ? cardMetadata(card).complexity_notes : [];
}

function codePitfalls(card) {
  return Array.isArray(cardMetadata(card).pitfalls) ? cardMetadata(card).pitfalls : [];
}

function codeExperiments(card) {
  return Array.isArray(cardMetadata(card).experiments) ? cardMetadata(card).experiments : [];
}

function exercisePrompt(card) {
  return cardMetadata(card).prompt || textPreview(bodyMarkdown(card));
}

function exerciseGoal(card) {
  return cardMetadata(card).goal || exercisePrompt(card);
}

function exerciseSteps(card) {
  return Array.isArray(cardMetadata(card).steps) ? cardMetadata(card).steps : [];
}

function exerciseCheckpoints(card) {
  return Array.isArray(cardMetadata(card).checkpoints) ? cardMetadata(card).checkpoints : [];
}

function exerciseHints(card) {
  return Array.isArray(cardMetadata(card).hints) ? cardMetadata(card).hints : [];
}

function exerciseQuestions(card) {
  const questions = cardMetadata(card).questions;
  if (!Array.isArray(questions)) return [];
  return questions.filter((question) => (
    question
    && String(question.id || "").trim()
    && String(question.prompt || "").trim()
    && Array.isArray(question.options)
    && question.options.length >= 2
  ));
}

function reviewPracticeQuestion(card) {
  if (!props.reviewItemId || props.reviewPhase !== "material_review") return null;
  return exerciseQuestions(card)[0] || null;
}

function reviewPracticeCard() {
  return props.cards.find((card) => (
    resourceType(card) === "interactive_exercise" && reviewPracticeQuestion(card)
  )) || null;
}

function reviewPracticeProgressKey(card = reviewPracticeCard()) {
  const itemId = String(props.reviewItemId || "").trim();
  const cardId = resourceId(card);
  if (!props.currentNode || !itemId || !cardId) return "";
  return `review-practice:${props.currentNode}:${itemId}:${cardId}`;
}

function persistReviewPracticeProgress(card = reviewPracticeCard()) {
  const question = reviewPracticeQuestion(card);
  const key = reviewPracticeProgressKey(card);
  if (!question || !key) return;
  learningAssets.write("quiz_progress", key, {
    kind: "review_practice",
    node_id: props.currentNode,
    resource_id: resourceId(card),
    review_item_id: props.reviewItemId,
    question_id: String(question.id),
    selected_option_index: reviewPracticeAnswerIndex.value,
    attempt_number: reviewPracticeAttemptNumber.value,
    practice_event_id: reviewPracticeEventId.value,
    error: reviewPracticeError.value,
  });
}

function restoreReviewPracticeProgress() {
  const card = reviewPracticeCard();
  const question = reviewPracticeQuestion(card);
  const key = reviewPracticeProgressKey(card);
  const progress = key ? learningAssets.read("quiz_progress", key, null) : null;
  if (!card || !question || !progress || progress.kind !== "review_practice") return;
  const selected = Number(progress.selected_option_index);
  reviewPracticeAnswerIndex.value = Number.isInteger(selected)
    && selected >= 0
    && selected < question.options.length
    ? selected
    : null;
  reviewPracticeAttemptNumber.value = Math.max(1, Number(progress.attempt_number) || 1);
  reviewPracticeEventId.value = String(progress.practice_event_id || "");
  reviewPracticeError.value = String(progress.error || "");
}

function reviewPracticeDomToken(card) {
  return `${props.reviewItemId}-${resourceId(card)}`.replace(/[^a-zA-Z0-9_-]/g, "_");
}

function reviewPracticePromptId(card) {
  return `review-practice-prompt-${reviewPracticeDomToken(card)}`;
}

function reviewPracticeInputName(card) {
  return `review-practice-${reviewPracticeDomToken(card)}`;
}

function reviewPracticeOptionId(card, optionIndex) {
  return `${reviewPracticeInputName(card)}-option-${optionIndex}`;
}

function selectReviewPracticeAnswer(card, optionIndex) {
  const question = reviewPracticeQuestion(card);
  if (!question || reviewPracticeSubmitting.value || !Number.isInteger(optionIndex)) return;
  if (!reviewPracticeStartedAt.value) reviewPracticeStartedAt.value = Date.now();
  if (reviewPracticeAnswerIndex.value !== optionIndex) reviewPracticeEventId.value = "";
  reviewPracticeAnswerIndex.value = optionIndex;
  reviewPracticeError.value = "";
  persistReviewPracticeProgress(card);
  emit("answer-selected", {
    resourceId: resourceId(card),
    questionId: String(question.id),
    selectedOptionIndex: optionIndex,
    attemptNumber: reviewPracticeAttemptNumber.value,
    usedHint: false,
    result: { selected_option_index: optionIndex, practice_kind: "targeted_practice" },
  });
}

function submitReviewPractice(card) {
  const question = reviewPracticeQuestion(card);
  const selectedOptionIndex = reviewPracticeAnswerIndex.value;
  const cardId = resourceId(card);
  if (!question || !cardId || !Number.isInteger(selectedOptionIndex) || reviewPracticeSubmitting.value) return;
  if (!reviewPracticeStartedAt.value) reviewPracticeStartedAt.value = Date.now();
  reviewPracticeSubmitting.value = true;
  reviewPracticeError.value = "";
  emit("prepare-review-retest", {
    reviewItemId: props.reviewItemId,
    resourceId: cardId,
    questionId: String(question.id),
    selectedOptionIndex,
    durationMs: Math.max(0, Date.now() - reviewPracticeStartedAt.value),
    attemptNumber: reviewPracticeAttemptNumber.value,
    usedHint: false,
    practiceEventId: reviewPracticeEventId.value,
    onPracticeRecorded: (eventId) => {
      reviewPracticeEventId.value = String(eventId || "");
      persistReviewPracticeProgress(card);
    },
    onIncorrect: () => {
      reviewPracticeSubmitting.value = false;
      reviewPracticeAttemptNumber.value += 1;
      reviewPracticeEventId.value = "";
      reviewPracticeError.value = "答案尚未通过验证。请重新选择。";
      persistReviewPracticeProgress(card);
    },
    onFailure: (error) => {
      reviewPracticeSubmitting.value = false;
      reviewPracticeError.value = String(error?.response?.data?.detail || error?.message || "练习提交失败，请原位重试。");
      persistReviewPracticeProgress(card);
    },
    onPrepared: () => {
      const key = reviewPracticeProgressKey(card);
      if (key) learningAssets.remove("quiz_progress", key);
    },
  });
}

function exerciseExpectedOutcome(card) {
  return cardMetadata(card).expected_outcome || "";
}

function exerciseSolutionOutline(card) {
  return cardMetadata(card).solution_outline || "";
}

function videoSummary(card) {
  return cardMetadata(card).summary || textPreview(bodyMarkdown(card));
}

function videoKeyPoints(card) {
  return Array.isArray(cardMetadata(card).key_points) ? cardMetadata(card).key_points : [];
}

function videoUrl(card) {
  return cardMetadata(card).video_url || "";
}

function videoTimeline(card) {
  return Array.isArray(cardMetadata(card).timeline) ? cardMetadata(card).timeline : [];
}

function videoWatchFocus(card) {
  return Array.isArray(cardMetadata(card).watch_focus) ? cardMetadata(card).watch_focus : [];
}

function videoReviewQuestions(card) {
  return Array.isArray(cardMetadata(card).review_questions) ? cardMetadata(card).review_questions : [];
}

function quizGuidance(card) {
  return cardMetadata(card).summary || "请先独立判断考查点，再结合当前节点材料选择答案。";
}

function quizAfterGuidance(card) {
  return cardMetadata(card).after_quiz_guidance || "";
}

function cardLabel(cardType) {
  return props.getCardLabel(cardType);
}

function taskStageLabel(cardType) {
  return {
    concept_map: "讲解",
    code_snippet: "示例",
    interactive_exercise: "练习",
    diagnostic_quiz: "反馈",
    video_summary: "补充",
  }[cardType] || cardLabel(cardType);
}

function agentLabel(cardType) {
  return props.getAgentLabel(cardType);
}

function cardColor(cardType) {
  switch (cardType) {
    case "concept_map": return "primary";
    case "code_snippet": return "info";
    case "interactive_exercise": return "tertiary";
    case "video_summary": return "secondary";
    case "diagnostic_quiz": return "warning";
    default: return "primary";
  }
}

<<<<<<< HEAD
function progressHint(cardType) {
  if (cardType === "diagnostic_quiz") {
    return 72;
  }
  if (cardType === "code_snippet") {
    return 58;
  }
  return 84;
=======
function getGridSpanClass(cardType) {
  switch (cardType) {
    case "concept_map":
    case "video_summary":
      return "col-span-1 md:col-span-6 xl:col-span-6";
    case "code_snippet":
      return "col-span-1 md:col-span-12 xl:col-span-12";
    case "interactive_exercise":
    case "diagnostic_quiz":
    default:
      return "col-span-1 md:col-span-6";
  }
>>>>>>> origin/main
}

function nodeChipClass(node) {
  if (node.id === selectedNodeId.value) {
    return "border-primary/45 bg-primary-soft font-semibold text-primary-dark ring-1 ring-primary/20";
  }

  if (node.mastery >= 0.65) {
    return "border-success/25 text-success hover:border-success/40 hover:bg-success-soft";
  }

  if (nextPendingNode.value?.id === node.id) {
    return "border-primary/30 bg-primary-soft/80 text-primary hover:border-primary/45";
  }

  return "border-subtle text-text-muted hover:border-hover hover:text-text-secondary hover:bg-card-hover";
}

function setNodeButtonRef(nodeId, element) {
  if (element instanceof HTMLElement) {
    nodeButtonRefs.set(nodeId, element);
    return;
  }

  nodeButtonRefs.delete(nodeId);
}

function selectNode(nodeId) {
  selectedNodeId.value = nodeId;
  emit("select-node", nodeId);
}

function alignNodeToLeft(nodeId) {
  const scroller = nodeScroller.value;
  const button = nodeButtonRefs.get(nodeId);
  if (!(scroller instanceof HTMLElement) || !(button instanceof HTMLElement)) {
    return;
  }

  const scrollerRect = scroller.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const targetLeft = Math.max(0, scroller.scrollLeft + buttonRect.left - scrollerRect.left);
  const workspace = scroller.closest(".workspace-shell");
  const reduceMotion = workspace?.classList.contains("is-reduced-motion")
    || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  scroller.scrollTo({
    left: targetLeft,
    behavior: reduceMotion ? "auto" : "smooth",
  });
}

<<<<<<< HEAD
=======
function isCardHydrated(cardId) {
  return hydratedCardIds.value.includes(cardId);
}

function hydrateCard(cardId) {
  if (!cardId || hydratedCardIds.value.includes(cardId)) {
    return;
  }

  hydratedCardIds.value = [...hydratedCardIds.value, cardId];
}

function canvasStateKey(nodeId = props.currentNode) {
  return nodeId ? `canvas:${nodeId}` : "";
}

function restoreCanvasState(allowedCardIds) {
  const key = canvasStateKey();
  const saved = key ? learningAssets.read("card_state", key, null) : null;
  const savedCardId = String(saved?.card_id || saved?.resource_id || "");
  return new Set(allowedCardIds).has(savedCardId) ? savedCardId : "";
}

function persistCanvasState(cardId) {
  const key = canvasStateKey();
  if (!key || !cardId) return;
  learningAssets.write("card_state", key, {
    node_id: props.currentNode,
    resource_id: cardId,
    card_id: cardId,
    expanded: true,
  });
}

>>>>>>> origin/main
function activateCard(cardId) {
  if (!cardId) {
    return;
  }

  setActiveCard(cardId);
}

function openCard(card) {
  if (!card?.resource_id) {
    return;
  }

  setActiveCard(card.resource_id);
  if (isSingleCardView.value) {
    return;
  }

  const filterKey = CARD_TYPES.find((item) => item.type === resourceType(card))?.sidebarKey;
  if (filterKey) {
    emit("filter-change", filterKey);
    return;
  }

  activateCard(card.resource_id);
}

function setActiveCard(cardId) {
  if (!cardId) {
    return;
  }

  activeCardId.value = cardId;
<<<<<<< HEAD
=======
  activeCardTypeHint.value = resourceType(props.cards.find((card) => resourceId(card) === cardId));

  if (shouldHydrate) {
    hydrateCard(cardId);
  }
  persistCanvasState(cardId);
>>>>>>> origin/main
}

function textPreview(content) {
  return extractTextPreview(content, 190);
}

function codePreview(content) {
  return extractCodePreview(content, 8);
}

function previewLabel(cardType) {
  switch (cardType) {
    case "code_snippet":
      return "代码预览";
    case "interactive_exercise":
      return "练习预览";
    case "diagnostic_quiz":
      return "诊断预览";
    case "video_summary":
      return "摘要预览";
    case "concept_map":
    default:
      return "内容预览";
  }
}

function bookmarkAssetKey(card) {
  const cardId = String(card?.resource_id || card?.id || "");
  return cardId && props.currentNode ? `${props.currentNode}:${cardId}` : "";
}

function isBookmarked(card) {
  const key = bookmarkAssetKey(card);
  const bookmark = key ? learningAssets.read("bookmarks", key, null) : null;
  return Boolean(bookmark && bookmark.favorite !== false);
}

function toggleBookmark(card) {
  const key = bookmarkAssetKey(card);
  if (!key) return;
  if (isBookmarked(card)) {
    learningAssets.remove("bookmarks", key);
    return;
  }
  learningAssets.write("bookmarks", key, {
    node_id: props.currentNode,
    resource_id: String(card?.resource_id || card?.id || ""),
    favorite: true,
    created_at: new Date().toISOString(),
  });
}

function annotationPrefix(card) {
  const cardId = String(card?.resource_id || card?.id || "");
  return cardId && props.currentNode ? `${props.currentNode}:${cardId}:` : "";
}

function annotationsFor(card) {
  const prefix = annotationPrefix(card);
  const annotations = learningAssets.read("annotations", null, {});
  if (!prefix || !annotations || typeof annotations !== "object") return [];
  return Object.entries(annotations)
    .filter(([key]) => key.startsWith(prefix))
    .map(([key, value]) => ({ ...value, key }));
}

function annotationKey(card) {
  const prefix = annotationPrefix(card);
  return prefix ? `${prefix}${Date.now()}:${Math.random().toString(36).slice(2, 8)}` : "";
}

function saveNoteAnnotation(card, content) {
  const key = annotationKey(card);
  if (!key || typeof content !== "string" || !content.trim()) return;
  learningAssets.write("annotations", key, {
    node_id: props.currentNode,
    resource_id: String(card?.resource_id || card?.id || ""),
    kind: "note",
    content: content.trim(),
    created_at: new Date().toISOString(),
  });
}

function saveHighlightAnnotation(card, payload) {
  const key = annotationKey(card);
  const selectedText = String(payload?.selectedText || selectedTextFor(card)).trim();
  if (!key || !selectedText) return;
  learningAssets.write("annotations", key, {
    node_id: props.currentNode,
    resource_id: String(card?.resource_id || card?.id || ""),
    kind: "highlight",
    selected_text: selectedText,
    color: String(payload?.color || "#F4C95D"),
    created_at: new Date().toISOString(),
  });
}

function removeAnnotation(key) {
  if (key) learningAssets.remove("annotations", String(key));
}

function captureSelectedText(card) {
  const cardId = String(card?.resource_id || card?.id || "");
  const selectedText = typeof window === "undefined" ? "" : String(window.getSelection()?.toString() || "").trim();
  if (!cardId || !selectedText) return;
  selectedTextByResource.value = { ...selectedTextByResource.value, [cardId]: selectedText.slice(0, 8_000) };
}

function selectedTextFor(card) {
  return selectedTextByResource.value[String(card?.resource_id || card?.id || "")] || "";
}

function quizProgressKey(resourceIdValue, nodeId = props.currentNode) {
  return resourceIdValue && nodeId ? `quiz:${nodeId}:${resourceIdValue}` : "";
}

function quizAttemptNumber(resourceIdValue) {
  return Math.max(1, Number(quizAttemptsByResource.value[resourceIdValue]) || 1);
}

function captureQuizProgress(resourceIdValue) {
  return {
    sessionId: String(props.sessionId || ""),
    nodeId: String(props.currentNode || ""),
    resourceId: String(resourceIdValue || ""),
    attemptNumber: quizAttemptNumber(resourceIdValue),
    answers: { ...answers.value },
    submittedQuestionIds: [...submittedQuestionIds.value],
    usedHint: Boolean(quizUsedHintByResource.value[resourceIdValue]),
  };
}

function persistQuizProgressSnapshot(progress) {
  const key = quizProgressKey(progress?.resourceId, progress?.nodeId);
  if (!key || !progress?.sessionId) return;
  learningAssets.write("quiz_progress", key, {
    node_id: progress.nodeId,
    resource_id: progress.resourceId,
    attempt_number: Math.max(1, Number(progress.attemptNumber) || 1),
    answers: { ...progress.answers },
    submitted_question_ids: [...new Set(progress.submittedQuestionIds)],
    used_hint: Boolean(progress.usedHint),
  });
}

function persistQuizProgress(resourceIdValue) {
  persistQuizProgressSnapshot(captureQuizProgress(resourceIdValue));
}

function restoreQuizProgress(resourceIdValue) {
  const key = quizProgressKey(resourceIdValue);
  const progress = key ? learningAssets.read("quiz_progress", key, null) : null;
  if (!resourceIdValue || !progress || typeof progress !== "object") return;
  answers.value = progress.answers && typeof progress.answers === "object"
    ? { ...progress.answers }
    : {};
  submittedQuestionIds.value = Array.isArray(progress.submitted_question_ids)
    ? [...new Set(progress.submitted_question_ids.map(String))]
    : [];
  quizAttemptsByResource.value = {
    ...quizAttemptsByResource.value,
    [resourceIdValue]: Math.max(1, Number(progress.attempt_number) || 1),
  };
  quizUsedHintByResource.value = {
    ...quizUsedHintByResource.value,
    [resourceIdValue]: Boolean(progress.used_hint),
  };
}

function isCurrentQuizProgress(progress) {
  return Boolean(
    progress
    && progress.sessionId === String(props.sessionId || "")
    && progress.nodeId === String(props.currentNode || "")
    && progress.resourceId === resourceId(quizCard.value),
  );
}

function questionSubmitted(questionId) {
  return submittedQuestionIds.value.includes(String(questionId || ""));
}

function questionSubmissionPending(questionId) {
  return submittingQuestionIds.value.includes(String(questionId || ""));
}

function canSubmitQuestion(question) {
  return Boolean(
    question?.id
    && Number.isInteger(answers.value[question.id])
    && !questionSubmitted(question.id)
    && !questionSubmissionPending(question.id)
    && !quizSubmitted.value
    && !quizSubmitting.value
    && !props.loading,
  );
}

function setAnswer(card, questionId, optionIndex) {
  const cardId = resourceId(card);
  if (!cardId || quizSubmitting.value || quizSubmitted.value || questionSubmitted(questionId)) return;
  if (!quizStartedAt.value) quizStartedAt.value = Date.now();
  answers.value = { ...answers.value, [questionId]: optionIndex };
  persistQuizProgress(cardId);
  emit("answer-selected", {
    resourceId: cardId,
    questionId,
    attemptNumber: quizAttemptNumber(cardId),
    usedHint: Boolean(quizUsedHintByResource.value[cardId]),
    result: { selected_option_index: optionIndex },
  });
}

function submitQuestionAnswer(card, question) {
  const cardId = resourceId(card);
  const questionId = String(question?.id || "");
  const selectedOptionIndex = answers.value[questionId];
  if (!cardId || !canSubmitQuestion(question)) return;
  const progress = captureQuizProgress(cardId);
  const attemptNumber = progress.attemptNumber;
  submittingQuestionIds.value = [...submittingQuestionIds.value, questionId];
  questionSubmissionErrors.value = { ...questionSubmissionErrors.value, [questionId]: "" };

  function settleSubmission(success, error) {
    if (success) {
      const completed = {
        ...progress,
        submittedQuestionIds: [...new Set([...progress.submittedQuestionIds, questionId])],
      };
      if (!isCurrentQuizProgress(progress)) {
        persistQuizProgressSnapshot(completed);
        return;
      }
      submittingQuestionIds.value = submittingQuestionIds.value.filter((id) => id !== questionId);
      submittedQuestionIds.value = completed.submittedQuestionIds;
      persistQuizProgress(cardId);
      return;
    }
    if (!isCurrentQuizProgress(progress)) return;
    submittingQuestionIds.value = submittingQuestionIds.value.filter((id) => id !== questionId);
    questionSubmissionErrors.value = {
      ...questionSubmissionErrors.value,
      [questionId]: String(error?.response?.data?.detail || error?.message || "Unable to save this answer. Please retry."),
    };
  }

  emit("submit-quiz", {
    eventKind: "answer_submitted",
    eventId: learningEventId("answer", progress, cardId, questionId, attemptNumber, selectedOptionIndex),
    sessionId: progress.sessionId,
    nodeId: progress.nodeId,
    resourceId: cardId,
    questionId,
    selectedOptionIndex,
    attemptNumber,
    usedHint: progress.usedHint,
    onRecorded: () => settleSubmission(true),
    onFailure: (error) => settleSubmission(false, error),
  });
}

function answerClass(questionId, optionIndex) {
  const selected = answers.value[questionId] === optionIndex;
  return selected
    ? "border-primary/30 bg-primary-soft text-primary"
    : "border-subtle bg-transparent text-text-secondary hover:border-secondary/25 hover:text-text-primary hover:bg-card-hover";
}

function submitQuizAnswers() {
  const resourceId = quizCard.value?.resource_id ?? quizCard.value?.id;
  if (!resourceId || !canSubmitQuiz.value) return;

  const progress = captureQuizProgress(String(resourceId));
  const attemptNumber = progress.attemptNumber;
  const isReview = Boolean(props.reviewItemId && props.reviewPhase === "retest");
  const submittedAnswers = quizQuestions.value.map((question) => ({
    questionId: question.id,
    selectedOptionIndex: progress.answers[question.id],
  }));
  quizSubmitting.value = true;
  quizSubmissionError.value = "";

  function settleSubmission(success, error) {
    if (!success) {
      if (!isCurrentQuizProgress(progress)) return;
      quizSubmitting.value = false;
      // Keep the submitted snapshot locked. Retrying uses the same event id,
      // so an acknowledged-but-lost response cannot become another attempt.
      quizSubmitted.value = true;
      quizSubmissionError.value = String(
        error?.response?.data?.detail || error?.message || "提交诊断失败，请原位重试。",
      );
      return;
    }

    const completed = { ...progress, attemptNumber: attemptNumber + 1 };
    persistQuizProgressSnapshot(completed);
    if (!isCurrentQuizProgress(progress)) return;
    quizSubmitting.value = false;
    quizSubmitted.value = true;
    quizSubmissionError.value = "";
    quizAttemptsByResource.value = {
      ...quizAttemptsByResource.value,
      [String(resourceId)]: attemptNumber + 1,
    };
  }

  emit("submit-quiz", {
    eventKind: "completion",
    eventId: learningEventId(isReview ? "review" : "lesson", progress, resourceId, attemptNumber),
    sessionId: progress.sessionId,
    nodeId: progress.nodeId,
    resourceId: String(resourceId),
    durationMs: Math.max(0, Date.now() - (quizStartedAt.value || Date.now())),
    attemptNumber,
    usedHint: progress.usedHint,
    isReview,
    answers: submittedAnswers,
    onRecorded: () => settleSubmission(true),
    onFailure: (error) => settleSubmission(false, error),
  });
<<<<<<< HEAD
  const score = quizQuestions.value.length ? correct / quizQuestions.value.length : 0;
  const resourceId = quizCard.value?.resource_id ?? quizCard.value?.id;
  if (!resourceId) return;
  if (!quizEventId.value) {
    quizEventId.value = `diagnostic-${resourceId}-${quizAttemptNumber.value}-${Date.now()}`;
  }
  submittedScore.value = score;
  emit("submit-quiz", {
    eventId: quizEventId.value,
    resourceId: String(resourceId),
    durationMs: Math.max(0, Date.now() - quizStartedAt.value),
    attemptNumber: quizAttemptNumber.value,
    usedHint: false,
    answers: quizQuestions.value.map((question) => ({
      questionId: question.id,
      selectedOptionIndex: answers.value[question.id],
    })),
    onRecorded() {
      quizAttemptNumber.value += 1;
      quizEventId.value = "";
    },
    onFailure() {
      submittedScore.value = null;
    },
  });
=======
}

function learningEventId(kind, progress, ...parts) {
  return ["eduagent", kind, progress?.sessionId, progress?.nodeId, ...parts]
    .map((part) => String(part ?? "").trim().replace(/\s+/g, "_"))
    .join(":");
>>>>>>> origin/main
}

function forwardWheelToContent(event) {
  if (!(scrollViewport.value instanceof HTMLElement)) {
    return;
  }

  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  if (scrollViewport.value.contains(target)) {
    return;
  }

  if (target.closest("textarea, input, select, [contenteditable='true']")) {
    return;
  }

  scrollViewport.value.scrollTop += event.deltaY;
}
</script>

<style scoped>
.resource-canvas {
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--space-elevated) 62%, transparent), transparent 22rem);
  overscroll-behavior: contain;
}

.resource-canvas__grid {
  display: grid;
  width: 100%;
  gap: 1rem;
}

.resource-canvas__grid--single {
  grid-template-columns: minmax(0, 1fr);
}

.resource-canvas__grid--single .resource-canvas__slot {
  min-height: max(36rem, calc(100dvh - 18rem));
}

.resource-canvas__grid--multiple {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 19rem), 1fr));
  grid-auto-rows: 30rem;
}

.resource-canvas__slot {
  min-width: 0;
}

.resource-canvas__header {
  display: grid;
  gap: 0.75rem;
  padding-bottom: 1rem;
}

.resource-canvas__heading-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.resource-canvas__eyebrow,
.resource-canvas__nodes-label,
.resource-canvas__metric span {
  color: var(--text-muted);
  font-size: 0.7rem;
  font-weight: 800;
  line-height: 1.2;
}

.resource-canvas__title-line {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.3rem;
}

.resource-canvas__title {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 1.35rem;
  font-weight: 850;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-canvas__actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 0.5rem;
}

.resource-canvas__status {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0;
  border-block: 1px solid var(--border-subtle);
  padding: 0.55rem 0;
}

.resource-canvas__metric {
  display: flex;
  flex-shrink: 0;
  align-items: baseline;
  gap: 0.4rem;
  padding: 0 0.85rem;
  border-right: 1px solid var(--border-subtle);
}

.resource-canvas__metric:first-child {
  padding-left: 0;
}

.resource-canvas__metric strong {
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

.resource-canvas__guidance {
  min-width: 0;
  overflow: hidden;
  margin-left: 0.85rem;
  color: var(--text-secondary);
  font-size: 0.78rem;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-canvas__nodes {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.75rem;
}

.resource-canvas__nodes-label {
  flex-shrink: 0;
}

.resource-canvas__filters {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.75rem;
  padding-top: 0.15rem;
}

.resource-canvas__filters-label {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 0.7rem;
  font-weight: 800;
  line-height: 1.2;
}

.resource-canvas__filter-scroll {
  display: flex;
  min-width: 0;
  flex: 1;
  gap: 0.35rem;
  overflow-x: auto;
  padding: 0.15rem;
}

.resource-canvas__filter {
  display: inline-flex;
  min-height: 2.75rem;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  border-radius: var(--radius-sm);
  padding: 0 0.8rem;
  color: var(--text-secondary);
  font-size: 0.75rem;
  font-weight: 750;
  transition:
    background-color var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard);
}

.resource-canvas__filter:hover {
  background: var(--space-elevated);
  color: var(--text-primary);
}

.resource-canvas__filter--active {
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
}

.resource-canvas__filter-count {
  display: inline-flex;
  min-width: 1.25rem;
  height: 1.25rem;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, currentColor 10%, transparent);
  padding: 0 0.3rem;
  font-family: var(--font-mono);
  font-size: 0.65rem;
  line-height: 1;
}

@media (max-width: 767px) {
  .resource-canvas__heading-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .resource-canvas__actions {
    width: 100%;
    overflow-x: auto;
  }

  .resource-canvas__status {
    overflow-x: auto;
  }

  .resource-canvas__metric--progress,
  .resource-canvas__guidance {
    display: none;
  }

  .resource-canvas__nodes {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.4rem;
  }

  .resource-canvas__filters {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.4rem;
  }

  .resource-canvas__filter-scroll {
    width: 100%;
  }
}
</style>
