<template>
  <section class="resource-canvas relative flex h-full min-h-0 flex-col px-4 py-4 sm:px-5 lg:px-6" @wheel="forwardWheelToContent">
    <header class="aurora-scroll max-h-[48vh] shrink-0 overflow-y-auto pb-4 pr-1 lg:pb-5">
      <div class="task-flow-header">
        <div class="task-flow-header__copy">
          <p>当前任务</p>
          <h2>{{ activeCardTitle }}</h2>
          <span>{{ learningTone }}</span>
        </div>

        <div class="task-flow-header__sequence" role="tablist" aria-label="学习任务顺序">
          <button
            v-for="slot in orderedCardTypeSlots"
            :key="slot.type"
            type="button"
            role="tab"
            class="task-flow-header__step focus-ring"
            :class="{ 'is-active': slot.card?.resource_id === activeCardId }"
            :aria-selected="String(slot.card?.resource_id === activeCardId)"
            :disabled="loading"
            @click="slot.card ? activateCard(slot.card.resource_id) : requestTaskResource(slot.type)"
          >
            {{ taskStageLabel(slot.type) }}
          </button>
        </div>
      </div>

      <section
        v-if="remediationTask"
        class="mt-4 border border-warning/25 bg-warning-soft/60 px-4 py-4 sm:px-5"
        aria-label="当前补救任务"
      >
        <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div class="min-w-0">
            <p class="text-[11px] font-bold text-warning">补救任务</p>
            <h3 class="mt-1 text-base font-bold text-text-primary">{{ remediationTask.title }}</h3>
            <ol class="mt-3 grid gap-2 text-sm leading-6 text-text-secondary">
              <li v-for="(step, index) in remediationTask.steps" :key="`${step.kind}-${index}`">
                <span class="font-semibold text-text-primary">{{ index + 1 }}. {{ step.label }}</span>
                <span v-if="step.detail">: {{ step.detail }}</span>
              </li>
            </ol>
          </div>
          <div class="flex shrink-0 flex-wrap gap-2">
            <button
              v-if="reviewItemId && reviewPhase === 'material_review'"
              type="button"
              class="workspace-shell-btn workspace-shell-btn--accent focus-ring min-h-11 px-4 py-2 text-xs font-semibold"
              @click="focusResourceType('interactive_exercise')"
            >
              去完成相似题
            </button>
            <button
              v-else-if="reviewItemId && reviewPhase === 'retest'"
              type="button"
              class="workspace-shell-btn workspace-shell-btn--accent focus-ring min-h-11 px-4 py-2 text-xs font-semibold"
              @click="focusResourceType('diagnostic_quiz')"
            >
              开始复测
            </button>
            <button
              v-else-if="reviewItemId && reviewPhase === 'code_resubmission'"
              type="button"
              class="workspace-shell-btn workspace-shell-btn--accent focus-ring min-h-11 px-4 py-2 text-xs font-semibold"
              @click="focusResourceType('code_snippet')"
            >
              修改并重新提交代码
            </button>
            <button
              v-else
              type="button"
              class="workspace-shell-btn workspace-shell-btn--accent focus-ring min-h-11 px-4 py-2 text-xs font-semibold"
              @click="$emit('open-review')"
            >
              查看并开始补救
            </button>
          </div>
        </div>
      </section>
    </header>

      <div
        ref="scrollViewport"
        class="aurora-scroll relative min-h-[12rem] flex-1 overflow-y-auto"
        @scroll.passive="handleContentScroll"
      >
        <div v-if="!cards.length && !loading" class="flex h-full min-h-[420px] items-center justify-center">
        <div class="flex max-w-[44ch] flex-col items-center text-center animate-fadeIn">
          <div class="mb-5 flex h-16 w-16 items-center justify-center rounded-lg border border-subtle bg-space-elevated">
            <svg
              width="52"
              height="52"
              viewBox="0 0 48 48"
              fill="none"
              class="text-secondary"
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

      <div class="task-stage mx-auto w-full max-w-[68rem]">
        <template v-for="(slot, index) in displaySlots" :key="slot.type">

          <!-- Case 1: card exists and not minimized -->
          <div
            v-if="slot.card"
            :data-resource-id="slot.card.resource_id"
            :data-resource-type="slot.type"
            class="task-stage__card h-full"
            :class="[
              slot.card.resource_id === activeCardId ? 'is-active' : '',
             ]"
          >
            <template v-for="card of [slot.card]" :key="card.resource_id">
            <ResourceCard
              class="h-full"
              :agent-name="agentLabel(resourceType(card))"
              :title="cardLabel(resourceType(card))"
              :is-ready="true"
              :is-active="card.resource_id === activeCardId"
              :is-expanded="isCardExpanded(card.resource_id)"
              :is-bookmarked="isBookmarked(card)"
              :activatable="false"
              :compact="true"
              :show-pin="false"
              :show-minimize="false"
              :color="cardColor(resourceType(card))"
              @activate="activateCard(card.resource_id)"
              @bookmark="toggleBookmark(card)"
            >
              <template #content>
              <div v-if="!isCardExpanded(card.resource_id)" class="space-y-4">
                <div class="workspace-shell-card-soft rounded-[20px] p-4">
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">
                    {{ previewLabel(resourceType(card)) }}
                  </p>

                  <pre
                    v-if="resourceType(card) === 'code_snippet'"
                    class="mt-3 overflow-x-auto rounded-[16px] border border-subtle/80 bg-[#08111f] px-4 py-3 text-xs leading-6 text-slate-100"
                  >{{ previewCode(card) }}</pre>

                  <p v-else class="mt-3 text-sm leading-7 text-text-secondary">
                    {{ previewText(card) }}
                  </p>
                </div>

                <button
                  type="button"
                    class="workspace-shell-btn workspace-shell-btn--accent focus-ring min-h-11 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.10em]"
                    @click.stop="activateCard(card.resource_id)"
                  >
                  {{ card.resource_id === activeCardId ? "展开完整内容" : "设为当前并展开" }}
                </button>
              </div>

              <div
                v-else
                class="space-y-5"
                :data-resource-content="resourceId(card)"
                @mouseup="captureSelectedText(card, $event)"
              >
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
                    <p
                      :id="reviewPracticePromptId(card)"
                      class="mt-2 text-sm leading-7 text-text-secondary"
                    >
                      {{ reviewPracticeQuestion(card).prompt }}
                    </p>
                    <div
                      class="mt-4 grid gap-2"
                      role="radiogroup"
                      :aria-labelledby="reviewPracticePromptId(card)"
                    >
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
                    <p
                      v-if="reviewPracticeError"
                      class="mt-3 text-sm leading-6 text-error"
                      role="alert"
                    >
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
                    <ul v-if="revealedExerciseHints(card).length" class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(hint, index) in revealedExerciseHints(card)" :key="`${card.resource_id}-hint-${index}`">{{ hint }}</li>
                    </ul>
                    <button
                      v-if="canRequestExerciseHint(card)"
                      type="button"
                      class="workspace-shell-btn focus-ring mt-3 min-h-11 px-3 py-2 text-[11px] font-semibold"
                      @click="requestExerciseHint(card)"
                    >
                      Show hint {{ revealedExerciseHints(card).length + 1 }}
                    </button>
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

                <VideoSummaryPanel
                  v-else-if="resourceType(card) === 'video_summary'"
                  :card="card"
                />

                <div v-else-if="resourceType(card) === 'diagnostic_quiz'" class="space-y-4">
                  <div v-if="quizGuidance(card)" class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">作答建议</p>
                    <p class="mt-3 text-sm leading-7 text-text-secondary">{{ quizGuidance(card) }}</p>
                  </div>

                  <div v-if="quizQuestions.length" class="space-y-4">
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
                          :disabled="questionSubmitted(question.id) || questionSubmissionPending(question.id) || quizSubmitted || quizSubmissionPending || quizEvidenceConsumed"
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
                      <div v-if="quizQuestionResult(question.id) || (quizSubmitted && question.explanation)" class="mt-3 workspace-shell-card-soft rounded-[16px] px-4 py-3">
                        <p v-if="quizQuestionResult(question.id)" class="text-sm font-semibold" :class="quizQuestionResult(question.id).correct ? 'text-success' : 'text-warning'">
                          {{ quizQuestionResult(question.id).correct ? 'Passed' : 'Needs review' }}
                        </p>
                        <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">题目解释</p>
                        <p class="mt-2 text-sm leading-6 text-text-secondary">{{ quizQuestionResult(question.id)?.explanation || question.explanation }}</p>
                      </div>
                    </div>

                    <div class="workspace-shell-card flex flex-wrap items-center justify-between gap-3 rounded-[20px] p-4">
                      <div class="text-sm font-light text-text-muted">
                        {{ diagnosticStatusText }}
                      </div>
                      <button
                        type="button"
                        class="focus-ring btn-capsule"
                        :disabled="!canSubmitQuiz"
                        @click="submitQuizAnswers"
                      >
                        {{ quizSubmitLabel }}
                      </button>
                    </div>

                    <div v-if="quizAfterGuidance(card) && (quizSubmitted || quizEvidenceConsumed)" class="workspace-shell-card rounded-[20px] p-4">
                      <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">提交后建议</p>
                      <p class="mt-3 text-sm leading-7 text-text-secondary">{{ quizAfterGuidance(card) }}</p>
                    </div>

                    <section v-if="quizReviewItems.length" class="space-y-3" aria-label="本次错题反馈">
                      <div
                        v-for="item in quizReviewItems"
                        :key="item.review_item_id"
                        class="workspace-shell-card rounded-[20px] p-4"
                      >
                        <p class="text-[10px] font-black uppercase tracking-[0.14em] text-warning">{{ errorTypeLabel(item.error_type) }}</p>
                        <p class="mt-2 text-sm font-semibold text-text-primary">{{ item.question_prompt }}</p>
                        <dl class="mt-3 grid gap-2 text-sm leading-6 text-text-secondary sm:grid-cols-2">
                          <div><dt class="text-[11px] text-text-muted">你的答案</dt><dd class="mt-1">{{ item.original_answer || '未作答' }}</dd></div>
                          <div><dt class="text-[11px] text-text-muted">正确答案</dt><dd class="mt-1 text-success">{{ item.correct_answer }}</dd></div>
                        </dl>
                        <p v-if="item.explanation" class="mt-3 text-sm leading-6 text-text-secondary">{{ item.explanation }}</p>
                      </div>
                    </section>
                  </div>

                  <div v-else class="workspace-shell-card rounded-[20px] p-4">
                    <p class="text-sm leading-7 text-text-muted">该诊断资源未提供可验证的题目数据，暂不能提交诊断。</p>
                  </div>
                </div>

                <MarkdownContent
                  v-else
                  :content="bodyMarkdown(card)"
                />

                <div data-resource-annotations>
                  <ResourceAnnotations
                    :annotations="annotationsFor(card)"
                    :can-highlight="Boolean(resourceId(card) && currentNode)"
                    :selected-text="selectedTextFor(card)"
                    :is-bookmarked="isBookmarked(card)"
                    @save-note="saveNoteAnnotation(card, $event)"
                    @save-highlight="saveHighlightAnnotation(card, $event)"
                    @remove="removeAnnotation"
                  />
                </div>
              </div>
            </template>
          </ResourceCard>
          </template><!-- end alias -->
          </div><!-- end existing-card slot -->

          <!-- Case 2: empty slot — show placeholder with generate button -->
          <div
            v-else-if="!slot.card"
            class="task-stage__empty min-h-[240px]"
          >
            <div
              class="slot-empty group h-full rounded-[22px] border border-dashed border-subtle/50 bg-space-elevated/40 flex flex-col items-center justify-center gap-4 p-6"
              :style="{ '--rail-accent': slot.color }"
            >
              <span class="slot-empty-icon text-[2.25rem] opacity-40 group-hover:opacity-75 transition-opacity duration-300"
                    :style="{ animationDelay: `${index * 0.4}s` }"
                    aria-hidden="true">{{ slot.icon }}</span>
              <div class="text-center space-y-0.5">
                <p class="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-text-muted">{{ slot.label }}</p>
                <p class="text-[11px] text-text-muted opacity-50">尚未生成</p>
              </div>
              <button
                v-if="currentNode"
                type="button"
                class="btn-ripple workspace-shell-btn workspace-shell-btn--accent focus-ring min-h-11 px-4 py-2 text-[11px] font-semibold tracking-[0.06em] transition-all duration-200"
                :disabled="loading"
                @click="$emit('generate-card', { nodeId: currentNode, cardType: slot.type })"
              >
                生成
              </button>
            </div>
          </div>

        </template><!-- end cardTypeSlots v-for -->
      </div>

    </div>

  </section>
</template>

<script setup>
import { computed, defineAsyncComponent, defineComponent, h, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import MarkdownContent from "./MarkdownContent.vue";
import ResourceAnnotations from "./ResourceAnnotations.vue";
import ResourceCard from "./ResourceCard.vue";
import { useLearningAssetsStore } from "../stores/learningAssets";
import { extractCodePreview, extractTextPreview } from "../utils/markdownPreview.js";

const CodePracticePanel = createAsyncLearningPanel({
  label: "代码练习",
  loadingMessage: "正在加载代码编辑器",
  minimumHeight: "28rem",
  loader: () => import("./CodePracticePanel.vue"),
});

const VideoSummaryPanel = createAsyncLearningPanel({
  label: "视频摘要",
  loadingMessage: "正在加载视频摘要",
  minimumHeight: "18rem",
  loader: () => import("./VideoSummaryPanel.vue"),
});

function createAsyncLearningPanel({ label, loadingMessage, minimumHeight, loader }) {
  const loadError = ref(null);
  let retryLoad = null;

  const LoadingState = defineComponent({
    name: `Async${label}State`,
    setup() {
      return () => {
        if (loadError.value) {
          return h("section", {
            class: "async-panel-state async-panel-state--error",
            style: { minHeight: minimumHeight },
            role: "alert",
            "aria-live": "assertive",
          }, [
            h("p", { class: "async-panel-state__title" }, `${label}加载失败`),
            h("p", { class: "async-panel-state__detail" }, "模块暂时不可用，请重新加载。"),
            h("button", {
              type: "button",
              class: "workspace-shell-btn workspace-shell-btn--accent focus-ring min-h-11 px-4 py-2 text-xs font-semibold",
              onClick: () => {
                const retry = retryLoad;
                if (!retry) return;
                loadError.value = null;
                retryLoad = null;
                retry();
              },
            }, `重新加载${label}`),
          ]);
        }

        return h("section", {
          class: "async-panel-state",
          style: { minHeight: minimumHeight },
          role: "status",
          "aria-live": "polite",
          "aria-busy": "true",
        }, [
          h("p", { class: "async-panel-state__title" }, loadingMessage),
          h("div", { class: "async-panel-state__skeleton", "aria-hidden": "true" }, [
            h("span"),
            h("span"),
            h("span", { class: "is-panel" }),
          ]),
        ]);
      };
    },
  });

  return defineAsyncComponent({
    loader,
    loadingComponent: LoadingState,
    delay: 0,
    suspensible: false,
    onError(error, retry) {
      loadError.value = error;
      retryLoad = retry;
    },
  });
}

const props = defineProps({
  cards: { type: Array, default: () => [] },
  sessionId: { type: String, default: "" },
  currentNode: { type: String, default: "" },
  nodeTitle: { type: String, default: "" },
  pathNodes: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
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

const emit = defineEmits([
  "submit-quiz",
  "select-node",
  "refresh",
  "generate-card",
  "content-viewed",
  "hint-requested",
  "answer-selected",
  "code-run",
  "code-submitted",
  "open-review",
  "prepare-review-retest",
]);

const activeCardId = ref("");
const answers = ref({});
const submittedQuestionIds = ref([]);
const submittingQuestionIds = ref([]);
const questionSubmissionErrors = ref({});
const quizSubmitted = ref(false);
const quizSubmitting = ref(false);
const quizSubmissionError = ref("");
const quizResourceId = ref("");
const scrollViewport = ref(null);
const revealedHintsByResource = ref({});
const quizAttemptsByResource = ref({});
const reviewPracticeAnswerIndex = ref(null);
const reviewPracticeAttemptNumber = ref(1);
const reviewPracticeSubmitting = ref(false);
const reviewPracticeError = ref("");
const reviewPracticeEventId = ref("");
const reviewPracticeStartedAt = ref(0);
const quizProgressResourceKey = ref("");
const observedResourceId = ref("");
const canvasMounted = ref(false);
const selectedTextByResource = ref({});
const learningAssets = useLearningAssetsStore();
const restoredCanvasLayoutKey = ref("");
const restoredReviewPracticeKey = ref("");
const dirtyCanvasLayoutKeys = new Set();
const restoredQuizProgressKeys = new Set();
const dirtyQuizProgressKeys = new Set();
const restoredScrollKeys = new Set();
const dirtyContentScrollKeys = new Set();
let contentScrollSaveTimer = null;

const CANVAS_LAYOUT_STORAGE_PREFIX = "eduagent:resource-canvas-layout:v1";

// ── 5-type slot system ─────────────────────────────────────────────────
const CARD_TYPES = [
  { type: "concept_map",          label: "概念导图", icon: "🗺", sidebarKey: "concept",  color: "var(--learning-concept)" },
  { type: "code_snippet",         label: "代码示例", icon: "💻", sidebarKey: "code",     color: "var(--learning-code)" },
  { type: "interactive_exercise", label: "互动练习", icon: "✏️", sidebarKey: "practice", color: "var(--learning-practice)" },
  { type: "video_summary",        label: "视频摘要", icon: "🎬", sidebarKey: "video",    color: "var(--learning-video)" },
  { type: "diagnostic_quiz",      label: "诊断测验", icon: "📋", sidebarKey: "quiz",     color: "var(--learning-quiz)" },
];

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
const allCardTypeSlots = computed(() =>
  CARD_TYPES.map((meta) => ({
    ...meta,
    card: cardsByType.value[meta.type] ?? null,
  })),
);

const cardTypeSlots = computed(() => (
  props.filterType && props.filterType !== "all"
    ? allCardTypeSlots.value.filter((slot) => slot.sidebarKey === props.filterType)
    : allCardTypeSlots.value
));

const cardsIdentityKey = computed(() => [
  props.sessionId,
  props.currentNode,
  ...props.cards.map(resourceId).filter(Boolean),
].join("|"));

watch(
  cardsIdentityKey,
  () => {
    const cards = props.cards;
    const nextIds = cards.map(resourceId).filter(Boolean);
    const nextIdSet = new Set(nextIds);

    if (!nextIdSet.has(activeCardId.value)) {
      const initialTaskCard = [
        "concept_map",
        "code_snippet",
        "interactive_exercise",
        "diagnostic_quiz",
        "video_summary",
      ]
        .map((type) => cards.find((card) => resourceType(card) === type))
        .find(Boolean);
      activeCardId.value = resourceId(initialTaskCard)
        || nextIds[0]
        || "";
    }

    const nextQuizResourceId = resourceId(cards.find((card) => resourceType(card) === "diagnostic_quiz"));
    const nextQuizProgressKey = quizProgressStorageKey(nextQuizResourceId);
    if (nextQuizProgressKey !== quizProgressResourceKey.value) {
      quizResourceId.value = nextQuizResourceId;
      quizProgressResourceKey.value = nextQuizProgressKey;
      restoreQuizProgress(nextQuizResourceId);
    }

    restoreCanvasLayout();
    restoreReviewPracticeProgress();
    void restoreContentScrollPosition();
  },
  { immediate: true },
);

watch(
  [cardsIdentityKey, () => props.focusCardType],
  () => {
    if (props.focusCardType) {
      focusResourceType(props.focusCardType);
    }
  },
  { immediate: true, flush: "post" },
);

watch(
  () => props.currentNode,
  (nextNode, previousNode) => {
    if (nextNode === previousNode) {
      return;
    }

    if (previousNode) {
      persistContentScrollPosition(previousNode);
    }

    if (contentScrollSaveTimer) {
      window.clearTimeout(contentScrollSaveTimer);
      contentScrollSaveTimer = null;
    }

    // Restore/dirty guards are only valid while their node is mounted. The
    // actual values are already stored under node/resource-scoped keys, so a
    // browser Back navigation must be allowed to hydrate them again.
    restoredQuizProgressKeys.clear();
    dirtyQuizProgressKeys.clear();
    dirtyCanvasLayoutKeys.clear();
    restoredScrollKeys.clear();
    dirtyContentScrollKeys.clear();

    activeCardId.value = "";
    answers.value = {};
    submittedQuestionIds.value = [];
    submittingQuestionIds.value = [];
    questionSubmissionErrors.value = {};
    quizSubmitted.value = false;
    quizSubmitting.value = false;
    quizSubmissionError.value = "";
    quizResourceId.value = "";
    quizProgressResourceKey.value = "";
    revealedHintsByResource.value = {};
    quizAttemptsByResource.value = {};
    reviewPracticeAnswerIndex.value = null;
    reviewPracticeAttemptNumber.value = 1;
    reviewPracticeSubmitting.value = false;
    reviewPracticeError.value = "";
    reviewPracticeEventId.value = "";
    reviewPracticeStartedAt.value = 0;
    observedResourceId.value = "";
    selectedTextByResource.value = {};
    restoredCanvasLayoutKey.value = "";
    restoredReviewPracticeKey.value = "";
  },
  { flush: "sync" },
);

watch(
  () => [props.reviewItemId, props.reviewPhase],
  () => {
    reviewPracticeAnswerIndex.value = null;
    reviewPracticeAttemptNumber.value = 1;
    reviewPracticeSubmitting.value = false;
    reviewPracticeError.value = "";
    reviewPracticeEventId.value = "";
    reviewPracticeStartedAt.value = 0;
    restoredReviewPracticeKey.value = "";
    void nextTick(() => restoreReviewPracticeProgress());
  },
  { flush: "sync" },
);

watch(
  () => learningAssets.hydrated,
  () => {
    restoreCanvasLayout();
    restoreQuizProgress(quizResourceId.value);
    restoreReviewPracticeProgress();
    void restoreContentScrollPosition();
  },
);

watch(
  () => activeCardId.value,
  async (cardId) => {
    if (!canvasMounted.value || !cardId) {
      return;
    }

    await nextTick();
    observeResource(cardId);
  },
  { flush: "post" },
);

onMounted(async () => {
  canvasMounted.value = true;
  await nextTick();
  observeResource(activeCardId.value);
  restoreReviewPracticeProgress();
  await restoreContentScrollPosition();
});

onBeforeUnmount(() => {
  if (contentScrollSaveTimer) {
    window.clearTimeout(contentScrollSaveTimer);
    contentScrollSaveTimer = null;
  }
  persistCanvasLayout();
  persistContentScrollPosition();
});

const sortedCards = computed(() => allCardTypeSlots.value
  .map((slot) => slot.card)
  .filter(Boolean));

const orderedCardTypeSlots = computed(() => {
  const sequence = [
    "concept_map",
    "code_snippet",
    "interactive_exercise",
    "diagnostic_quiz",
    "video_summary",
  ];
  const sequenceIndex = new Map(sequence.map((type, index) => [type, index]));
  return [...cardTypeSlots.value].sort((left, right) => (
    (sequenceIndex.get(left.type) ?? Number.MAX_SAFE_INTEGER)
    - (sequenceIndex.get(right.type) ?? Number.MAX_SAFE_INTEGER)
  ));
});

const displaySlots = computed(() => {
  const activeSlot = orderedCardTypeSlots.value.find(
    (slot) => slot.card?.resource_id === activeCardId.value,
  );
  return activeSlot ? [activeSlot] : orderedCardTypeSlots.value.slice(0, 1);
});

const quizCard = computed(() =>
  sortedCards.value.find((card) => resourceType(card) === "diagnostic_quiz"),
);

const currentQuizDiagnostic = computed(() => {
  const diagnostic = props.lastDiagnostic;
  const resourceId = quizCard.value?.resource_id ?? quizCard.value?.id;
  if (!diagnostic || !resourceId) {
    return null;
  }

  return diagnostic.evaluatedNodeId === props.currentNode
    && diagnostic.resourceId === resourceId
    ? diagnostic
    : null;
});

const quizEvidenceConsumed = computed(() => Boolean(
  currentQuizDiagnostic.value && !currentQuizDiagnostic.value.failed,
));

const quizSubmissionPending = computed(() => quizSubmitting.value);

const quizQuestions = computed(() => {
  const structuredQuestions = structuredPayload(quizCard.value)?.questions;
  if (!Array.isArray(structuredQuestions)) {
    return [];
  }

  return structuredQuestions
    .map((question) => {
      const id = question?.id ?? question?.question_id;
      return {
        id: id === undefined || id === null ? "" : String(id),
        prompt: typeof question?.prompt === "string" ? question.prompt.trim() : "",
        options: Array.isArray(question?.options) ? question.options : [],
        explanation: typeof question?.explanation === "string" ? question.explanation : "",
        skillTag: typeof question?.skill_tag === "string" ? question.skill_tag : "",
        difficulty: typeof question?.difficulty === "string" ? question.difficulty : "",
      };
    })
    .filter((question) => question.id && question.prompt && question.options.length >= 2);
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
  && !quizEvidenceConsumed.value
  && !quizSubmissionPending.value
));
const quizSubmitLabel = computed(() => {
  if (quizEvidenceConsumed.value) {
    return "诊断已提交";
  }
  if (quizSubmissionPending.value) {
    return "提交中...";
  }
  if (quizSubmissionError.value) {
    return "重新提交诊断";
  }
  if (allAnswered.value && !allQuestionsSubmitted.value) {
    return "Submit each answer";
  }
  if (currentQuizDiagnostic.value?.failed) {
    return "重新提交诊断";
  }
  return "提交诊断";
});

const currentNodeMeta = computed(() =>
  props.pathNodes.find((node) => node.id === props.currentNode),
);

const currentMastery = computed(() =>
  Math.round((currentNodeMeta.value?.mastery ?? 0) * 100),
);

const activeCardTitle = computed(() => {
  const activeCard = sortedCards.value.find((card) => card.resource_id === activeCardId.value) ?? sortedCards.value[0];
  return activeCard ? taskStageLabel(resourceType(activeCard)) : "当前内容";
});

const learningTone = computed(() => {
  if (props.loading) return "资源装配中";
  if (!props.cards.length) return "等待资源";
  if (currentMastery.value >= 65) return "节点达标";
  return "继续学习";
});

const diagnosticStatusText = computed(() => {
  if (quizSubmissionError.value) {
    return quizSubmissionError.value;
  }
  if (currentQuizDiagnostic.value) {
    if (currentQuizDiagnostic.value.failed) {
      return currentQuizDiagnostic.value.failureMessage || "诊断提交失败，请重试。";
    }

    const scorePercent = toPercent(currentQuizDiagnostic.value.score);
    const beforePercent = toPercent(currentQuizDiagnostic.value.masteryBefore);
    const afterPercent = toPercent(currentQuizDiagnostic.value.masteryAfter);
    const scoreText = scorePercent === null ? "上次诊断已由服务端处理" : `上次诊断得分 ${scorePercent}%`;
    const masteryText = beforePercent === null || afterPercent === null
      ? ""
      : ` · 掌握度 ${beforePercent}% -> ${afterPercent}%`;
    if (currentQuizDiagnostic.value.advancedToNextNode) {
      return `${scoreText}${masteryText} · 已推进到 ${currentQuizDiagnostic.value.nextNodeTitle || "下一节点"}`;
    }
    if (currentQuizDiagnostic.value.requiresRemediation) {
      return `${scoreText}${masteryText} · 未达标，请完成上方补救任务后再复测`;
    }
    return `${scoreText}${masteryText} · 继续停留当前节点`;
  }

  if (quizSubmissionPending.value) {
    return "答案已提交，正在等待服务端评分。";
  }

  return "请先回答所有题目，再提交服务端评分。";
});

const quizReviewItems = computed(() => (
  Array.isArray(currentQuizDiagnostic.value?.reviewItems)
    ? currentQuizDiagnostic.value.reviewItems
    : []
));

const remediationTask = computed(() => {
  if (props.reviewItemId) {
    if (props.reviewPhase === "code_resubmission") {
      return {
        title: "根据服务端测试结果修改代码后重新提交",
        steps: [
          { kind: "review_material", label: "复盘失败原因", detail: "查看代码面板中的公开失败用例和判题结果。" },
          { kind: "targeted_practice", label: "修改并运行代码", detail: "在代码编辑器中修正实现，可先运行公开测试。" },
          { kind: "retest", label: "提交完整测试", detail: "只有服务端判定通过后，补救任务才会完成并更新掌握度。" },
        ],
      };
    }
    return {
      title: props.reviewPhase === "retest" ? "现在完成服务端复测" : "先完成定向练习，再进行复测",
      steps: props.reviewPhase === "retest"
        ? [{ kind: "retest", label: "完成复测", detail: "复测结果会更新错题完成状态和掌握度归因。" }]
        : [
          { kind: "review_material", label: "复盘解析", detail: "核对错题本中的原答案、正确答案和解析。" },
          { kind: "targeted_practice", label: "完成相似题练习", detail: "聚焦当前展开的互动练习。" },
          { kind: "retest", label: "生成并完成复测", detail: "通过后系统才会关闭本条错题。" },
        ],
    };
  }
  const diagnostic = currentQuizDiagnostic.value;
  if (diagnostic?.requiresRemediation && diagnostic?.remediation) {
    return diagnostic.remediation;
  }
  return null;
});

function toPercent(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return Math.round(value * 100);
}

function errorTypeLabel(errorType) {
  return {
    concept_understanding: "概念理解偏差",
    application_context: "适用场景判断偏差",
    boundary_condition: "边界条件遗漏",
  }[errorType] || "需要复盘";
}

function resourceType(card) {
  return card?.resource_type || card?.card_type || card?.type || "";
}

function resourceId(card) {
  return card?.resource_id || card?.id || "";
}

function canvasLayoutStorageKey(nodeId = props.currentNode) {
  const sessionId = String(props.sessionId || "").trim();
  const normalizedNodeId = String(nodeId || "").trim();
  if (!sessionId || !normalizedNodeId) return "";
  return `${CANVAS_LAYOUT_STORAGE_PREFIX}:${sessionId}:${normalizedNodeId}`;
}

function persistCanvasLayout(nodeId = props.currentNode) {
  const key = canvasLayoutStorageKey(nodeId);
  if (!key) return;

  const cardIds = props.cards.map(resourceId).filter(Boolean);
  const allowedIds = new Set(cardIds);
  const activeCard = String(activeCardId.value || "").trim();
  const normalizedActiveCard = allowedIds.has(activeCard) ? activeCard : "";

  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(key, JSON.stringify({
        version: 2,
        active_card_id: normalizedActiveCard,
      }));
    } catch {
      // The synchronized learning asset remains the durable source.
    }
  }

  const assetKey = canvasStateAssetKey(nodeId);
  if (assetKey && normalizedActiveCard && String(learningAssets.sessionId || "") === String(props.sessionId || "")) {
    dirtyCanvasLayoutKeys.add(assetKey);
    learningAssets.write("card_state", assetKey, {
      node_id: String(nodeId || ""),
      resource_id: normalizedActiveCard,
      card_id: normalizedActiveCard,
      expanded: true,
    });
  }
}

function restoreCanvasLayout() {
  const cardIds = props.cards.map(resourceId).filter(Boolean);
  const key = canvasLayoutStorageKey();
  const assetKey = canvasStateAssetKey();
  const restoreKey = `${key}:${cardsIdentityKey.value}:${learningAssets.hydrated ? "remote" : "cache"}`;
  if (
    !key
    || !cardIds.length
    || restoredCanvasLayoutKey.value === restoreKey
    || (assetKey && dirtyCanvasLayoutKeys.has(assetKey))
  ) {
    return;
  }

  let saved = null;
  if (typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem(key);
      saved = raw ? JSON.parse(raw) : null;
    } catch {
      saved = null;
    }
  }

  const allowedIds = new Set(cardIds);
  const synchronizedState = assetKey
    ? learningAssets.read("card_state", assetKey, null)
    : null;
  const savedActiveId = String(
    synchronizedState?.card_id
    || synchronizedState?.resource_id
    || saved?.active_card_id
    || "",
  ).trim();
  activeCardId.value = allowedIds.has(savedActiveId)
    ? savedActiveId
    : cardIds[0] ?? "";
  restoredCanvasLayoutKey.value = restoreKey;
}

function scopedAssetKey(prefix, resourceIdValue = "", nodeIdValue = props.currentNode) {
  const nodeId = String(nodeIdValue || "").trim();
  const resource = String(resourceIdValue || "").trim();
  if (!nodeId) return "";
  return resource ? `${prefix}:${nodeId}:${resource}` : `${prefix}:${nodeId}`;
}

function quizProgressAssetKey(resourceIdValue, nodeIdValue = props.currentNode) {
  return scopedAssetKey("quiz", resourceIdValue, nodeIdValue);
}

function canvasStateAssetKey(nodeIdValue = props.currentNode) {
  return scopedAssetKey("canvas", "", nodeIdValue);
}

function bookmarkAssetKey(resourceIdValue) {
  return scopedAssetKey("bookmark", resourceIdValue);
}

function scrollPositionAssetKey(nodeId = props.currentNode) {
  const normalizedNodeId = String(nodeId || "").trim();
  return normalizedNodeId ? `resource-canvas:${normalizedNodeId}` : "";
}

function annotationAssetKey(card) {
  const nodeId = String(props.currentNode || "").trim();
  const cardId = resourceId(card);
  if (!nodeId || !cardId) return "";
  const nonce = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `annotation:${nodeId}:${cardId}:${nonce}`;
}

function annotationEntries() {
  const entries = learningAssets.read("annotations", null, {});
  return entries && typeof entries === "object" && !Array.isArray(entries) ? entries : {};
}

function annotationsFor(card) {
  const cardId = resourceId(card);
  if (!cardId || !props.currentNode) return [];
  return Object.entries(annotationEntries())
    .filter(([, annotation]) => (
      annotation
      && annotation.node_id === props.currentNode
      && annotation.resource_id === cardId
    ))
    .map(([key, annotation]) => ({ ...annotation, key }));
}

function isBookmarked(card) {
  const key = bookmarkAssetKey(resourceId(card));
  const bookmark = key ? learningAssets.read("bookmarks", key, null) : null;
  return Boolean(bookmark && bookmark.favorite !== false);
}

function toggleBookmark(card) {
  const cardId = resourceId(card);
  const key = bookmarkAssetKey(cardId);
  if (!key || !cardId) return;
  if (isBookmarked(card)) {
    learningAssets.remove("bookmarks", key);
    return;
  }
  learningAssets.write("bookmarks", key, {
    node_id: props.currentNode,
    resource_id: cardId,
    title: String(card?.title || cardLabel(resourceType(card)) || "").slice(0, 240),
    favorite: true,
  });
}

function selectedTextFor(card) {
  return selectedTextByResource.value[resourceId(card)] || "";
}

function captureSelectedText(card, event) {
  const cardId = resourceId(card);
  if (!cardId || typeof window === "undefined") return;
  const selection = window.getSelection();
  const root = event?.currentTarget;
  if (!selection || !root || selection.rangeCount === 0 || selection.isCollapsed) return;
  const range = selection.getRangeAt(0);
  if (!(root instanceof HTMLElement) || !root.contains(range.commonAncestorContainer)) return;
  const selectedText = selection.toString().trim();
  if (!selectedText) return;
  selectedTextByResource.value = {
    ...selectedTextByResource.value,
    [cardId]: selectedText.slice(0, 8_000),
  };
}

function saveNoteAnnotation(card, content) {
  const cardId = resourceId(card);
  const key = annotationAssetKey(card);
  if (!cardId || !key || typeof content !== "string" || !content.trim()) return;
  learningAssets.write("annotations", key, {
    node_id: props.currentNode,
    resource_id: cardId,
    kind: "note",
    content: content.trim(),
  });
}

function saveHighlightAnnotation(card, payload) {
  const cardId = resourceId(card);
  const key = annotationAssetKey(card);
  const selectedText = String(payload?.selectedText || selectedTextFor(card) || "").trim();
  if (!cardId || !key || !selectedText) return;

  const value = {
    node_id: props.currentNode,
    resource_id: cardId,
    kind: "highlight",
    selected_text: selectedText,
    color: /^#[0-9a-f]{3,8}$/i.test(String(payload?.color || "")) ? payload.color : "#F4C95D",
  };
  const source = bodyMarkdown(card);
  const startOffset = source.indexOf(selectedText);
  if (startOffset >= 0) {
    value.start_offset = startOffset;
    value.end_offset = startOffset + selectedText.length;
  }
  learningAssets.write("annotations", key, value);
}

function removeAnnotation(key) {
  if (key) learningAssets.remove("annotations", String(key));
}

function handleContentScroll() {
  const key = scrollPositionAssetKey();
  if (!key) return;
  dirtyContentScrollKeys.add(key);
  if (contentScrollSaveTimer) return;
  contentScrollSaveTimer = window.setTimeout(() => {
    contentScrollSaveTimer = null;
    persistContentScrollPosition();
  }, 250);
}

function persistContentScrollPosition(nodeId = props.currentNode) {
  if (!(scrollViewport.value instanceof HTMLElement)) return;
  const key = scrollPositionAssetKey(nodeId);
  if (!key || !nodeId) return;
  learningAssets.write("scroll_positions", key, {
    node_id: String(nodeId),
    top: Math.max(0, Math.round(scrollViewport.value.scrollTop)),
  });
}

async function restoreContentScrollPosition() {
  const key = scrollPositionAssetKey();
  const restoreKey = `${key}:${learningAssets.hydrated ? "remote" : "cache"}`;
  if (!key || dirtyContentScrollKeys.has(key) || restoredScrollKeys.has(restoreKey)) return;
  await nextTick();
  if (!(scrollViewport.value instanceof HTMLElement)) return;
  const saved = learningAssets.read("scroll_positions", key, null);
  const top = Number(saved?.top);
  if (Number.isFinite(top) && top > 0) {
    scrollViewport.value.scrollTop = top;
  }
  restoredScrollKeys.add(restoreKey);
}

function quizProgressStorageKey(resourceIdValue, {
  sessionId = props.sessionId,
  nodeId = props.currentNode,
} = {}) {
  const resourceId = String(resourceIdValue || "").trim();
  const normalizedSessionId = String(sessionId || "").trim();
  const normalizedNodeId = String(nodeId || "").trim();
  if (!resourceId || !normalizedSessionId || !normalizedNodeId) {
    return "";
  }
  return `eduagent:quiz-progress:v1:${normalizedSessionId}:${normalizedNodeId}:${resourceId}`;
}

function captureQuizProgress(resourceIdValue) {
  const resourceId = String(resourceIdValue || "").trim();
  return {
    sessionId: String(props.sessionId || "").trim(),
    nodeId: String(props.currentNode || "").trim(),
    resourceId,
    attemptNumber: quizAttemptNumber(resourceId),
    answers: { ...answers.value },
    submittedQuestionIds: [...submittedQuestionIds.value],
    usedHint: Boolean(revealedHintsByResource.value[resourceId]),
  };
}

function isCurrentQuizProgress(progress) {
  return Boolean(
    progress
      && progress.sessionId === String(props.sessionId || "").trim()
      && progress.nodeId === String(props.currentNode || "").trim()
      && progress.resourceId === String(quizResourceId.value || "").trim(),
  );
}

function persistQuizProgressSnapshot(progress) {
  if (!progress?.resourceId || !progress.sessionId || !progress.nodeId) return;
  const storageKey = quizProgressStorageKey(progress.resourceId, progress);
  const assetKey = quizProgressAssetKey(progress.resourceId, progress.nodeId);
  const value = {
    node_id: progress.nodeId,
    resource_id: progress.resourceId,
    attempt_number: Math.max(1, Number(progress.attemptNumber) || 1),
    answers: normalizeQuizAnswers(progress.answers),
    submitted_question_ids: normalizeSubmittedQuestionIds(progress.submittedQuestionIds),
    used_hint: Boolean(progress.usedHint),
  };

  if (storageKey && typeof window !== "undefined") {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(value));
    } catch {
      // Storage is an ergonomic aid; the canonical answer events remain server-side.
    }
  }
  if (assetKey && String(learningAssets.sessionId || "") === progress.sessionId) {
    dirtyQuizProgressKeys.add(assetKey);
    learningAssets.write("quiz_progress", assetKey, value);
  }
}

function normalizeQuizAnswers(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(value)
      .filter(([questionId, optionIndex]) => (
        Boolean(String(questionId || "").trim())
        && Number.isInteger(Number(optionIndex))
        && Number(optionIndex) >= 0
      ))
      .map(([questionId, optionIndex]) => [questionId, Number(optionIndex)]),
  );
}

function normalizeSubmittedQuestionIds(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value
    .map((questionId) => String(questionId || "").trim())
    .filter(Boolean))];
}

function restoreQuizProgress(resourceIdValue) {
  const resourceId = String(resourceIdValue || "").trim();
  const assetKey = quizProgressAssetKey(resourceId);
  const restoreKey = `${assetKey}:${learningAssets.hydrated ? "remote" : "cache"}`;
  if (!resourceId || (assetKey && dirtyQuizProgressKeys.has(assetKey)) || restoredQuizProgressKeys.has(restoreKey)) {
    return;
  }

  answers.value = {};
  submittedQuestionIds.value = [];
  submittingQuestionIds.value = [];
  questionSubmissionErrors.value = {};
  // A page reload cannot tell whether a terminal POST was still in flight.
  // Treat it as idle and let the authoritative event-history restore decide
  // whether this diagnostic was already consumed.
  quizSubmitted.value = false;
  quizSubmitting.value = false;
  quizSubmissionError.value = "";
  const storageKey = quizProgressStorageKey(resourceId);
  let localProgress = null;
  if (storageKey && typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem(storageKey);
      localProgress = raw ? JSON.parse(raw) : null;
    } catch {
      localProgress = null;
    }
  }

  const synchronizedProgress = assetKey
    ? learningAssets.read("quiz_progress", assetKey, null)
    : null;
  const progress = synchronizedProgress && typeof synchronizedProgress === "object"
    ? synchronizedProgress
    : localProgress;

  const attemptNumber = Math.max(1, Number(progress?.attempt_number) || 1);
  quizAttemptsByResource.value = {
    ...quizAttemptsByResource.value,
    [resourceId]: attemptNumber,
  };
  answers.value = normalizeQuizAnswers(progress?.answers);
  submittedQuestionIds.value = normalizeSubmittedQuestionIds(progress?.submitted_question_ids);
  if (progress?.used_hint) {
    revealedHintsByResource.value = {
      ...revealedHintsByResource.value,
      [resourceId]: Math.max(1, Number(revealedHintsByResource.value[resourceId]) || 0),
    };
  }
  restoredQuizProgressKeys.add(restoreKey);
}

function persistQuizProgress(resourceIdValue = quizResourceId.value) {
  const resourceId = String(resourceIdValue || "").trim();
  if (!resourceId) return;
  persistQuizProgressSnapshot(captureQuizProgress(resourceId));
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
  if (resourceType(card) === "code_snippet") {
    return true;
  }
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
    && typeof question === "object"
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

function reviewPracticeProgressCard() {
  return props.cards.find((card) => (
    resourceType(card) === "interactive_exercise"
    && exerciseQuestions(card).length > 0
  )) || null;
}

function reviewPracticeProgressKey(card = reviewPracticeProgressCard()) {
  const session = String(props.sessionId || "").trim();
  const node = String(props.currentNode || "").trim();
  const item = String(props.reviewItemId || "").trim();
  const resource = resourceId(card);
  if (!session || !node || !item || !resource) return "";
  return `review-practice:${node}:${item}:${resource}`;
}

function persistReviewPracticeProgress(card = reviewPracticeProgressCard()) {
  const question = reviewPracticeQuestion(card);
  const key = reviewPracticeProgressKey(card);
  if (!question || !key || String(learningAssets.sessionId || "") !== String(props.sessionId || "")) return;
  learningAssets.write("quiz_progress", key, {
    kind: "review_practice",
    node_id: String(props.currentNode || ""),
    resource_id: resourceId(card),
    review_item_id: String(props.reviewItemId || ""),
    question_id: String(question.id || ""),
    selected_option_index: Number.isInteger(reviewPracticeAnswerIndex.value)
      ? reviewPracticeAnswerIndex.value
      : null,
    attempt_number: Math.max(1, Number(reviewPracticeAttemptNumber.value) || 1),
    used_hint: Boolean(revealedHintsByResource.value[resourceId(card)]),
    practice_event_id: String(reviewPracticeEventId.value || ""),
    error: String(reviewPracticeError.value || ""),
    updated_at: Date.now(),
  });
}

function restoreReviewPracticeProgress() {
  if (!props.reviewItemId || props.reviewPhase !== "material_review") return;
  const card = reviewPracticeProgressCard();
  const question = reviewPracticeQuestion(card);
  const key = reviewPracticeProgressKey(card);
  if (!card || !question || !key) return;
  const restoreKey = `${key}:${learningAssets.hydrated ? "remote" : "cache"}`;
  if (restoredReviewPracticeKey.value === restoreKey) return;
  restoredReviewPracticeKey.value = restoreKey;

  const progress = learningAssets.read("quiz_progress", key, null);
  if (!progress || typeof progress !== "object" || Array.isArray(progress)) return;
  if (
    progress.kind !== "review_practice"
    || String(progress.node_id || "") !== String(props.currentNode || "")
    || String(progress.resource_id || "") !== resourceId(card)
    || String(progress.review_item_id || "") !== String(props.reviewItemId || "")
    || String(progress.question_id || "") !== String(question.id || "")
  ) {
    return;
  }

  const selectedOptionIndex = Number(progress.selected_option_index);
  reviewPracticeAnswerIndex.value = Number.isInteger(selectedOptionIndex)
    && selectedOptionIndex >= 0
    && selectedOptionIndex < question.options.length
    ? selectedOptionIndex
    : null;
  reviewPracticeAttemptNumber.value = Math.max(1, Number(progress.attempt_number) || 1);
  reviewPracticeEventId.value = String(progress.practice_event_id || "");
  reviewPracticeError.value = String(progress.error || "");
  reviewPracticeStartedAt.value = reviewPracticeAnswerIndex.value === null ? 0 : Date.now();
  if (progress.used_hint) {
    revealedHintsByResource.value = {
      ...revealedHintsByResource.value,
      [resourceId(card)]: Math.max(1, Number(revealedHintsByResource.value[resourceId(card)]) || 0),
    };
  }
}

function clearReviewPracticeProgress(card = reviewPracticeProgressCard()) {
  const key = reviewPracticeProgressKey(card);
  if (key && String(learningAssets.sessionId || "") === String(props.sessionId || "")) {
    learningAssets.remove("quiz_progress", key);
  }
  restoredReviewPracticeKey.value = "";
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
  if (reviewPracticeAnswerIndex.value !== optionIndex) {
    reviewPracticeEventId.value = "";
  }
  reviewPracticeAnswerIndex.value = optionIndex;
  reviewPracticeError.value = "";
  persistReviewPracticeProgress(card);
  emit("answer-selected", {
    resourceId: resourceId(card),
    questionId: String(question.id),
    selectedOptionIndex: optionIndex,
    attemptNumber: reviewPracticeAttemptNumber.value,
    usedHint: Boolean(revealedHintsByResource.value[resourceId(card)]),
    result: {
      selected_option_index: optionIndex,
      review_item_id: props.reviewItemId,
      practice_kind: "targeted_practice",
    },
  });
}

function submitReviewPractice(card) {
  const question = reviewPracticeQuestion(card);
  const selectedOptionIndex = reviewPracticeAnswerIndex.value;
  const practiceResourceId = resourceId(card);
  if (
    !question
    || !practiceResourceId
    || !Number.isInteger(selectedOptionIndex)
    || reviewPracticeSubmitting.value
  ) {
    return;
  }
  if (!reviewPracticeStartedAt.value) reviewPracticeStartedAt.value = Date.now();
  reviewPracticeSubmitting.value = true;
  reviewPracticeError.value = "";
  emit("prepare-review-retest", {
    reviewItemId: props.reviewItemId,
    resourceId: practiceResourceId,
    questionId: String(question.id),
    selectedOptionIndex,
    durationMs: Math.max(0, Date.now() - reviewPracticeStartedAt.value),
    attemptNumber: reviewPracticeAttemptNumber.value,
    usedHint: Boolean(revealedHintsByResource.value[practiceResourceId]),
    practiceEventId: reviewPracticeEventId.value,
    onPracticeRecorded: (eventId) => {
      reviewPracticeEventId.value = String(eventId || "");
      persistReviewPracticeProgress(card);
    },
    onIncorrect: () => {
      reviewPracticeSubmitting.value = false;
      reviewPracticeAttemptNumber.value += 1;
      reviewPracticeEventId.value = "";
      reviewPracticeError.value = "答案尚未通过验证。请回看条件和边界后重新选择。";
      persistReviewPracticeProgress(card);
    },
    onFailure: (error) => {
      reviewPracticeSubmitting.value = false;
      reviewPracticeError.value = error?.response?.data?.detail
        || error?.message
        || "练习提交失败，请原位重试。";
      persistReviewPracticeProgress(card);
    },
    onPrepared: () => {
      clearReviewPracticeProgress(card);
    },
  });
}

function revealedExerciseHints(card) {
  const id = resourceId(card);
  const count = revealedHintsByResource.value[id] ?? 0;
  return exerciseHints(card).slice(0, count);
}

function canRequestExerciseHint(card) {
  return revealedExerciseHints(card).length < exerciseHints(card).length;
}

function requestExerciseHint(card) {
  const id = resourceId(card);
  if (!id || !canRequestExerciseHint(card)) {
    return;
  }

  const nextHintIndex = revealedExerciseHints(card).length;
  revealedHintsByResource.value = {
    ...revealedHintsByResource.value,
    [id]: nextHintIndex + 1,
  };
  if (props.reviewItemId && props.reviewPhase === "material_review") {
    persistReviewPracticeProgress(card);
  }
  emit("hint-requested", {
    resourceId: id,
    attemptNumber: 1,
    usedHint: true,
    result: { hint_index: nextHintIndex },
  });
}

function exerciseExpectedOutcome(card) {
  return cardMetadata(card).expected_outcome || "";
}

function exerciseSolutionOutline(card) {
  return cardMetadata(card).solution_outline || "";
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

function isCardExpanded(cardId) {
  return cardId === activeCardId.value;
}

function activateCard(cardId) {
  if (!cardId) {
    return;
  }

  setActiveCard(cardId);
}

function setActiveCard(cardId) {
  if (!cardId) {
    return;
  }

  activeCardId.value = cardId;
  persistCanvasLayout();
}

function focusResourceType(cardType) {
  const target = props.cards.find((card) => resourceType(card) === cardType);
  const targetId = target ? resourceId(target) : "";
  if (targetId) {
    setActiveCard(targetId);
  }
}

function requestTaskResource(cardType) {
  if (!props.currentNode || props.loading || !cardType) {
    return;
  }

  emit("generate-card", {
    nodeId: props.currentNode,
    cardType,
  });
}

async function scrollToAnnotations() {
  await nextTick();
  const target = scrollViewport.value?.querySelector("[data-resource-annotations]");
  if (!(target instanceof HTMLElement)) {
    return;
  }

  target.scrollIntoView({ behavior: "smooth", block: "start" });
  target.querySelector("textarea, input")?.focus({ preventScroll: true });
}

defineExpose({ scrollToAnnotations });

function observeResource(cardId) {
  if (!cardId || observedResourceId.value === cardId) {
    return;
  }

  const card = props.cards.find((item) => resourceId(item) === cardId);
  if (!card) {
    return;
  }

  observedResourceId.value = cardId;
  emit("content-viewed", {
    resourceId: cardId,
    attemptNumber: quizAttemptNumber(card),
    usedHint: Boolean(revealedHintsByResource.value[cardId]),
    result: { resource_type: resourceType(card) },
  });
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

function quizAttemptNumber(cardOrResourceId = quizCard.value) {
  const id = typeof cardOrResourceId === "string"
    ? cardOrResourceId
    : resourceId(cardOrResourceId);
  return Math.max(1, Number(quizAttemptsByResource.value[id] ?? 1));
}

function questionSubmitted(questionId) {
  return submittedQuestionIds.value.includes(String(questionId || ""));
}

function questionSubmissionPending(questionId) {
  return submittingQuestionIds.value.includes(String(questionId || ""));
}

function quizQuestionResult(questionId) {
  const normalizedQuestionId = String(questionId || "").trim();
  if (!normalizedQuestionId) {
    return null;
  }

  const questionResults = currentQuizDiagnostic.value?.questionResults;
  const result = Array.isArray(questionResults)
    ? questionResults.find((item) => item?.question_id === normalizedQuestionId)
    : null;
  if (result && typeof result === "object") {
    return {
      correct: result.correct === true,
      explanation: typeof result.explanation === "string" ? result.explanation : "",
    };
  }

  const reviewItem = quizReviewItems.value.find(
    (item) => item?.question_id === normalizedQuestionId,
  );
  if (!reviewItem) {
    return null;
  }
  return {
    correct: false,
    explanation: typeof reviewItem.explanation === "string" ? reviewItem.explanation : "",
  };
}

function canSubmitQuestion(question) {
  return Boolean(
    question?.id
    && answers.value[question.id] !== undefined
    && !questionSubmitted(question.id)
    && !questionSubmissionPending(question.id)
    && !quizSubmitted.value
    && !quizSubmissionPending.value
    && !quizEvidenceConsumed.value
    && !props.loading,
  );
}

function setAnswer(card, questionId, optionIndex) {
  const id = resourceId(card);
  if (!id || !questionId || !Number.isInteger(optionIndex)
    || questionSubmitted(questionId) || questionSubmissionPending(questionId)
    || quizSubmitted.value || quizSubmissionPending.value) {
    return;
  }

  answers.value = {
    ...answers.value,
    [questionId]: optionIndex,
  };
  emit("answer-selected", {
    resourceId: id,
    questionId,
    attemptNumber: quizAttemptNumber(card),
    usedHint: false,
    result: { selected_option_index: optionIndex },
  });
  persistQuizProgress(id);
}

function submitQuestionAnswer(card, question) {
  const id = resourceId(card);
  const questionId = String(question?.id || "").trim();
  const selectedOptionIndex = answers.value[questionId];
  if (!id || !questionId || !Number.isInteger(selectedOptionIndex) || !canSubmitQuestion(question)) {
    return;
  }

  const submissionProgress = captureQuizProgress(id);
  const attemptNumber = submissionProgress.attemptNumber;

  submittingQuestionIds.value = [...submittingQuestionIds.value, questionId];
  questionSubmissionErrors.value = {
    ...questionSubmissionErrors.value,
    [questionId]: "",
  };

  function settleSubmission(success, error) {
    if (success) {
      const completedProgress = {
        ...submissionProgress,
        submittedQuestionIds: [
          ...new Set([...submissionProgress.submittedQuestionIds, questionId]),
        ],
      };
      if (!isCurrentQuizProgress(submissionProgress)) {
        persistQuizProgressSnapshot(completedProgress);
        return;
      }

      submittingQuestionIds.value = submittingQuestionIds.value.filter((item) => item !== questionId);
      if (!questionSubmitted(questionId)) {
        submittedQuestionIds.value = [...submittedQuestionIds.value, questionId];
      }
      questionSubmissionErrors.value = {
        ...questionSubmissionErrors.value,
        [questionId]: "",
      };
      persistQuizProgress(id);
      return;
    }

    if (!isCurrentQuizProgress(submissionProgress)) return;

    submittingQuestionIds.value = submittingQuestionIds.value.filter((item) => item !== questionId);
    const detail = error?.response?.data?.detail || error?.message || "Unable to save this answer. Please retry.";
    questionSubmissionErrors.value = {
      ...questionSubmissionErrors.value,
      [questionId]: String(detail),
    };
  }

  emit("submit-quiz", {
    eventKind: "answer_submitted",
    eventId: learningEventId(
      "answer",
      submissionProgress,
      id,
      questionId,
      attemptNumber,
      selectedOptionIndex,
    ),
    sessionId: submissionProgress.sessionId,
    nodeId: submissionProgress.nodeId,
    resourceId: id,
    questionId,
    selectedOptionIndex,
    attemptNumber,
    usedHint: submissionProgress.usedHint,
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
  if (!resourceId || !canSubmitQuiz.value) {
    return;
  }

  const submissionProgress = captureQuizProgress(String(resourceId));
  const attemptNumber = submissionProgress.attemptNumber;
  const isReview = Boolean(props.reviewItemId && props.reviewPhase === "retest");
  const submittedAnswers = quizQuestions.value.map((question) => ({
    questionId: question.id,
    selectedOptionIndex: submissionProgress.answers[question.id],
  }));
  quizSubmitting.value = true;
  quizSubmissionError.value = "";

  function settleSubmission(success, error) {
    if (!success) {
      if (!isCurrentQuizProgress(submissionProgress)) return;
      quizSubmitting.value = false;
      // Keep the submitted answer snapshot locked. Retrying reuses the same
      // event id, so an acknowledged-but-lost response cannot be changed into
      // a second mastery-bearing attempt.
      quizSubmitted.value = true;
      const detail = error?.response?.data?.detail || error?.message || "提交诊断失败，请重试。";
      quizSubmissionError.value = String(detail);
      return;
    }

    const completedProgress = {
      ...submissionProgress,
      attemptNumber: attemptNumber + 1,
    };
    if (!isCurrentQuizProgress(submissionProgress)) {
      persistQuizProgressSnapshot(completedProgress);
      return;
    }

    quizSubmitting.value = false;
    quizSubmitted.value = true;
    quizSubmissionError.value = "";
    quizAttemptsByResource.value = {
      ...quizAttemptsByResource.value,
      [String(resourceId)]: attemptNumber + 1,
    };
    persistQuizProgress(String(resourceId));
  }

  emit("submit-quiz", {
    eventKind: "completion",
    eventId: learningEventId(isReview ? "review" : "lesson", submissionProgress, resourceId, attemptNumber),
    sessionId: submissionProgress.sessionId,
    nodeId: submissionProgress.nodeId,
    resourceId: String(resourceId),
    attemptNumber,
    usedHint: submissionProgress.usedHint,
    isReview,
    answers: submittedAnswers,
    onRecorded: () => settleSubmission(true),
    onFailure: (error) => settleSubmission(false, error),
  });
}

function learningEventId(kind, progress, ...parts) {
  return ["eduagent", kind, progress?.sessionId, progress?.nodeId, ...parts]
    .map((part) => String(part ?? "").trim().replace(/\s+/g, "_"))
    .join(":");
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
  background: var(--space-bg);
}

.task-flow-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid var(--border-subtle);
  padding: 0.25rem 0 1rem;
}

.task-flow-header__copy {
  min-width: 0;
}

.task-flow-header__copy p,
.task-flow-header__copy span {
  color: var(--text-muted);
  font-size: 0.72rem;
  line-height: 1.3;
}

.task-flow-header__copy p {
  margin: 0;
  font-weight: 700;
}

.task-flow-header__copy h2 {
  margin: 0.32rem 0 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: var(--font-size-xl);
  font-weight: 750;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-flow-header__copy span {
  display: block;
  margin-top: 0.3rem;
}

.task-flow-header__sequence {
  display: flex;
  min-width: 0;
  max-width: 64%;
  gap: 0.25rem;
  overflow-x: auto;
  padding-bottom: 0.1rem;
}

.task-flow-header__step {
  flex: 0 0 auto;
  min-width: 2.75rem;
  min-height: 2.75rem;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 650;
  padding: 0.35rem 0.55rem;
  white-space: nowrap;
}

.task-flow-header__step:hover:not(:disabled) {
  background: var(--card-bg-hover);
  color: var(--text-secondary);
}

.task-flow-header__step.is-active {
  border-color: color-mix(in srgb, var(--color-primary) 25%, var(--border-subtle));
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
}

.task-flow-header__step:disabled {
  cursor: wait;
  opacity: 1;
}

.task-stage {
  padding: 0.35rem 0 1.5rem;
}

.task-stage__card,
.task-stage__empty {
  width: 100%;
}

.task-stage__empty .slot-empty {
  border-radius: var(--radius-md);
  background: var(--space-elevated);
}

:deep(.async-panel-state) {
  display: grid;
  align-content: start;
  gap: 1rem;
  width: 100%;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--space-elevated);
  padding: 1rem;
}

:deep(.async-panel-state--error) {
  align-content: center;
  justify-items: start;
  border-color: color-mix(in srgb, var(--color-error) 28%, var(--border-subtle));
}

:deep(.async-panel-state__title),
:deep(.async-panel-state__detail) {
  margin: 0;
}

:deep(.async-panel-state__title) {
  color: var(--text-primary);
  font-size: 0.875rem;
  font-weight: 700;
}

:deep(.async-panel-state__detail) {
  color: var(--text-secondary);
  font-size: 0.8125rem;
  line-height: 1.6;
}

:deep(.async-panel-state__skeleton) {
  display: grid;
  gap: 0.75rem;
}

:deep(.async-panel-state__skeleton span) {
  display: block;
  width: 48%;
  height: 0.75rem;
  border-radius: 4px;
  background: color-mix(in srgb, var(--border-subtle) 74%, transparent);
  animation: async-panel-pulse 1.2s ease-in-out infinite alternate;
}

:deep(.async-panel-state__skeleton span:first-child) {
  width: 72%;
}

:deep(.async-panel-state__skeleton .is-panel) {
  width: 100%;
  height: 14rem;
}

@keyframes async-panel-pulse {
  from { opacity: 0.45; }
  to { opacity: 0.9; }
}

@media (max-width: 767px) {
  .resource-canvas {
    padding: 0.85rem;
  }

  .task-flow-header {
    align-items: stretch;
    flex-direction: column;
    gap: 0.7rem;
  }

  .task-flow-header__sequence {
    max-width: none;
  }

  .task-stage {
    padding-bottom: 0.85rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  :deep(.async-panel-state__skeleton span) {
    animation: none;
  }
}
</style>
