<template>
  <div class="review-page min-h-screen">
    <header class="review-topbar">
      <div class="review-topbar__inner">
        <div class="review-topbar__left">
          <button
            type="button"
            class="icon-button focus-ring"
            aria-label="返回工作台"
            title="返回工作台"
            @click="goBack"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M19 12H5" />
              <path d="m12 19-7-7 7-7" />
            </svg>
          </button>
          <div class="review-brand">
            <span class="review-brand__mark">EA</span>
            <div>
              <p class="review-brand__name">EduAgent</p>
              <p class="review-brand__context">数据结构与算法</p>
            </div>
          </div>
        </div>

        <div class="review-topbar__right">
          <span class="review-topbar__label">复习中心</span>
        </div>
      </div>
    </header>

    <div class="review-layout">
      <main class="review-content">
        <div v-if="loading" class="state-panel state-panel--loading" aria-live="polite">
          <div class="skeleton-heading" />
          <div class="skeleton-copy" />
          <div class="skeleton-list">
            <div v-for="index in 3" :key="index" class="skeleton-card" />
          </div>
        </div>

        <section v-else-if="error" class="state-panel state-panel--error" role="alert">
          <div class="state-panel__icon state-panel__icon--error">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 8v4" />
              <path d="M12 16h.01" />
            </svg>
          </div>
          <h1>复习队列加载失败</h1>
          <p>{{ error }}</p>
          <button type="button" class="button button--primary focus-ring" :disabled="loading" @click="fetchData">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 11a8.1 8.1 0 0 0-14-4.9L4 8" />
              <path d="M4 4v4h4" />
              <path d="M4 13a8.1 8.1 0 0 0 14 4.9L20 16" />
              <path d="M20 20v-4h-4" />
            </svg>
            重新加载
          </button>
        </section>

        <template v-else>
          <section class="review-hero">
            <div>
              <p class="review-hero__eyebrow">错题复习工作台</p>
              <h1>{{ actionableCount ? `${actionableCount} 项需要处理` : "没有到期复习" }}</h1>
              <p class="review-hero__description">
                {{ actionableCount ? "先处理最需要注意的题目，再用一次重刷确认你真的掌握了。" : "今天没有需要立刻复习的题目，可以继续探索新的知识点。" }}
              </p>
            </div>
            <div class="review-hero__signal" :class="{ 'review-hero__signal--clear': !actionableCount }">
              <div class="signal-ring">
                <svg v-if="actionableCount" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 3v4" />
                  <path d="M12 17v4" />
                  <path d="m4.93 4.93 2.83 2.83" />
                  <path d="m16.24 16.24 2.83 2.83" />
                  <path d="M3 12h4" />
                  <path d="M17 12h4" />
                  <path d="m4.93 19.07 2.83-2.83" />
                  <path d="m16.24 7.76 2.83-2.83" />
                </svg>
                <svg v-else aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="m5 12 4 4L19 6" />
                </svg>
              </div>
              <div>
                <span class="review-hero__signal-label">{{ actionableCount ? "建议先从这里开始" : "状态良好" }}</span>
                <strong>{{ actionableCount ? `${todayQueue.length} 道今日到期` : "可以继续学习" }}</strong>
              </div>
            </div>
          </section>

          <section class="review-retest-cta" aria-labelledby="review-retest-title">
            <div class="review-retest-cta__copy">
              <div class="review-retest-cta__icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M20 11a8.1 8.1 0 0 0-14-4.9L4 8" />
                  <path d="M4 4v4h4" />
                  <path d="M4 13a8.1 8.1 0 0 0 14 4.9L20 16" />
                  <path d="M20 20v-4h-4" />
                </svg>
              </div>
              <div>
                <h2 id="review-retest-title">开始重刷</h2>
                <p>系统会准备一套复测题，按测验方式完成后再查看每道题的结果。</p>
              </div>
            </div>
            <div class="review-retest-cta__actions">
              <button
                type="button"
                class="button button--primary focus-ring"
                :disabled="loading || !todayQueue.length || startingIds.length"
                @click="startRetest('today')"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M8 5v14l11-7-11-7Z" />
                </svg>
                {{ startingIds.length ? "正在打开..." : "重刷今日待复习" }}
                <span class="review-retest-cta__count">{{ todayQueue.length }}</span>
              </button>
              <button
                type="button"
                class="button button--secondary focus-ring"
                :disabled="loading || !actionableCount || startingIds.length"
                @click="startRetest('all')"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M4 6h16M4 12h16M4 18h10" />
                </svg>
                重刷全部待处理
                <span class="review-retest-cta__count">{{ actionableCount }}</span>
              </button>
            </div>
          </section>

          <section class="review-overview" aria-label="复习概览">
            <article class="overview-item overview-item--attention">
              <span class="overview-item__label">待处理</span>
              <strong>{{ actionableCount }}</strong>
              <span class="overview-item__hint">需要你的下一步行动</span>
            </article>
            <article class="overview-item">
              <span class="overview-item__label">今日到期</span>
              <strong>{{ todayQueue.length }}</strong>
              <span class="overview-item__hint">{{ todayQueue.length ? "按优先级排好" : "今天没有新任务" }}</span>
            </article>
            <article class="overview-item">
              <span class="overview-item__label">已掌握</span>
              <strong>{{ completedCount }}</strong>
              <span class="overview-item__hint">已完成复习闭环</span>
            </article>
            <article class="overview-item overview-item--focus">
              <span class="overview-item__label">薄弱知识点</span>
              <strong>{{ weakNodes.length || "—" }}</strong>
              <span class="overview-item__hint">{{ weakNodes.length ? weakNodes[0].node_title : "完成诊断后生成" }}</span>
            </article>
          </section>

          <section v-if="weakNodes.length" class="focus-strip" aria-label="薄弱知识点">
            <div class="focus-strip__heading">
              <span class="focus-strip__dot" />
              <div>
                <p class="focus-strip__title">优先关注</p>
                <p class="focus-strip__copy">系统根据最近的答题证据，建议你先补齐这些节点。</p>
              </div>
            </div>
            <div class="focus-strip__nodes">
              <div v-for="node in weakNodes.slice(0, 3)" :key="node.node_id" class="focus-node">
                <div class="focus-node__topline">
                  <span>{{ reviewText(node.node_title || node.node_id, "node", node) }}</span>
                  <strong>{{ formatPercent(node.mastery) }}</strong>
                </div>
                <div class="focus-node__track">
                  <span :style="{ width: `${Math.max(4, Math.min(100, Number(node.mastery || 0) * 100))}%` }" />
                </div>
                <small>{{ node.outstanding_count || 0 }} 项待巩固</small>
              </div>
            </div>
          </section>

          <section class="review-list-section" aria-labelledby="review-list-title">
            <div class="review-list-header">
              <div>
                <h2 id="review-list-title">复习清单</h2>
                <p>{{ filteredItems.length ? `当前显示 ${filteredItems.length} 项` : "没有符合当前筛选条件的题目" }}</p>
              </div>
              <div class="review-list-header__tools">
                <label class="search-field">
                  <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="11" cy="11" r="6.5" />
                    <path d="m16 16 4.5 4.5" />
                  </svg>
                  <input v-model="searchQuery" type="search" placeholder="搜索题干、知识点" aria-label="搜索错题" />
                </label>
                <label class="select-field">
                  <span class="sr-only">排序方式</span>
                  <select v-model="sortMode" aria-label="排序方式">
                    <option value="priority">按优先级</option>
                    <option value="recent">最近更新</option>
                    <option value="topic">按知识点</option>
                  </select>
                  <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <path d="m6 9 6 6 6-6" />
                  </svg>
                </label>
              </div>
            </div>

            <div class="review-tabs" role="tablist" aria-label="错题分类">
              <button
                v-for="tab in tabs"
                :key="tab.key"
                type="button"
                class="review-tab focus-ring"
                :class="{ 'review-tab--active': activeTab === tab.key }"
                role="tab"
                :aria-selected="activeTab === tab.key"
                @click="activeTab = tab.key"
              >
                {{ tab.label }}
                <span>{{ tab.count }}</span>
              </button>
            </div>

            <div class="review-filters">
              <div class="filter-chips" aria-label="状态筛选">
                <button
                  v-for="filter in statusFilters"
                  :key="filter.value"
                  type="button"
                  class="filter-chip focus-ring"
                  :class="{ 'filter-chip--active': statusFilter === filter.value }"
                  @click="statusFilter = filter.value"
                >
                  <span v-if="filter.dot" class="filter-chip__dot" :class="`filter-chip__dot--${filter.dot}`" />
                  {{ filter.label }}
                </button>
              </div>
              <label v-if="errorTypes.length > 1" class="type-filter">
                <span>错误类型</span>
                <select v-model="errorTypeFilter" aria-label="错误类型">
                  <option value="all">全部类型</option>
                  <option v-for="type in errorTypes" :key="type" :value="type">{{ errorLabel(type) }}</option>
                </select>
              </label>
            </div>

            <TransitionGroup v-if="filteredItems.length" name="review-item" tag="div" class="review-items">
              <article
                v-for="item in filteredItems"
                :key="item.review_item_id"
                class="review-item"
                :class="{
                  'review-item--expanded': expandedIds.includes(item.review_item_id),
                  'review-item--removing': removingIds.includes(item.review_item_id),
                }"
              >
                <div class="review-item__status" :class="`review-item__status--${statusTone(item.status)}`" aria-hidden="true" />
                <div class="review-item__body">
                  <div class="review-item__meta">
                    <span class="item-tag item-tag--error">
                      {{ errorLabel(item.error_type) }}
                    </span>
                    <span class="item-meta-text">{{ reviewText(item.node_title || item.node_id, "node", item) }}</span>
                    <span class="item-meta-separator">·</span>
                    <span class="item-meta-text">{{ statusLabel(item.status) }}</span>
                  </div>

                  <h3>{{ reviewText(item.question_prompt, "question", item) || "这道题暂时没有题干" }}</h3>

                  <div v-if="expandedIds.includes(item.review_item_id)" class="review-item__details">
                    <div class="answer-grid">
                      <div class="answer-block answer-block--wrong">
                        <span>你的答案</span>
                        <strong>{{ reviewText(displayValue(item.original_answer, "未作答"), "answer", item) }}</strong>
                      </div>
                      <div class="answer-block answer-block--correct">
                        <span>正确答案</span>
                        <strong>{{ reviewText(displayValue(item.correct_answer, "暂无答案"), "correct", item) }}</strong>
                      </div>
                    </div>
                    <div v-if="item.explanation" class="explanation-block">
                      <span>解析</span>
                      <p>{{ reviewText(item.explanation, "explanation", item) }}</p>
                    </div>
                  </div>

                  <div class="review-item__footer">
                    <button
                      v-if="hasAnswerDetails(item)"
                      type="button"
                      class="text-button focus-ring"
                      :aria-expanded="expandedIds.includes(item.review_item_id)"
                      @click="toggleExpanded(item.review_item_id)"
                    >
                      {{ expandedIds.includes(item.review_item_id) ? "收起解析" : "查看答案与解析" }}
                      <svg :class="{ 'text-button__icon--up': expandedIds.includes(item.review_item_id) }" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                        <path d="m6 9 6 6 6-6" />
                      </svg>
                    </button>
                    <span v-else class="review-item__footer-note">完成定向练习后会生成更完整的解析</span>

                    <button
                      v-if="item.status !== 'completed'"
                      type="button"
                      class="button button--secondary button--compact focus-ring"
                      :disabled="startingIds.includes(item.review_item_id)"
                      @click="startReview(item)"
                    >
                      <span v-if="startingIds.includes(item.review_item_id)" class="button-loader" aria-hidden="true" />
                      <svg v-else aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
                        <path d="m9 18 6-6-6-6" />
                      </svg>
                      {{ startingIds.includes(item.review_item_id) ? "正在准备" : item.status === "in_progress" ? "继续复习" : "开始补救" }}
                    </button>
                    <span v-else class="completed-mark">
                      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
                        <path d="m5 12 4 4L19 6" />
                      </svg>
                      已完成
                    </span>
                    <button
                      type="button"
                      class="icon-button review-item__delete focus-ring"
                      aria-label="删除错题"
                      title="删除错题"
                      :disabled="removingIds.includes(item.review_item_id)"
                      @click="requestDelete(item)"
                    >
                      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M4 7h16" />
                        <path d="M10 11v6M14 11v6" />
                        <path d="M6 7l1 13h10l1-13" />
                        <path d="M9 7V4h6v3" />
                      </svg>
                      <span>删除</span>
                    </button>
                  </div>
                </div>
              </article>
            </TransitionGroup>

            <div v-else class="list-empty">
              <div class="list-empty__icon">
                <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M6 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
                  <path d="M8 9h8M8 13h6" />
                </svg>
              </div>
              <h3>{{ totalCount ? "没有符合条件的题目" : "没有错题记录" }}</h3>
              <p>{{ totalCount ? "可以调整上方筛选条件，看看其他复习任务。" : "继续学习，系统会在发现需要巩固的地方后把题目放到这里。" }}</p>
              <button v-if="totalCount && (searchQuery || errorTypeFilter !== 'all' || statusFilter !== 'all')" type="button" class="text-button focus-ring" @click="clearFilters">
                清除筛选
              </button>
            </div>
          </section>
        </template>
      </main>

      <aside class="review-tutor">
        <div class="review-tutor__header">
          <div>
            <p class="review-tutor__eyebrow">结合上下文复习</p>
            <h2>错题辅导</h2>
          </div>
          <span class="review-tutor__status"><span />在线</span>
        </div>
        <div class="review-tutor__body">
          <ChatArea
            :messages="tutorMessages"
            :busy="tutorBusy"
            :node-title="'错题复习'"
            :boot-mode="'ready'"
            session-id="student:data_structures"
            node-id="N01"
            :suggestions="tutorSuggestions"
            @send="onTutorSend"
          />
        </div>
      </aside>
    </div>

    <p v-if="actionError" class="review-toast" role="alert">{{ actionError }}</p>

    <div v-if="deleteTarget" class="review-modal-backdrop" role="presentation" @click.self="closeDeleteDialog">
      <section class="review-modal" role="dialog" aria-modal="true" aria-labelledby="delete-review-title">
        <button type="button" class="review-modal__close icon-button focus-ring" aria-label="关闭弹窗" title="关闭弹窗" @click="closeDeleteDialog">
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="m7 7 10 10M17 7 7 17" />
          </svg>
        </button>
        <div class="review-modal__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3 3.8 18a1.5 1.5 0 0 0 1.3 2.2h13.8a1.5 1.5 0 0 0 1.3-2.2L12 3Z" />
            <path d="M12 9v4M12 17h.01" />
          </svg>
        </div>
        <h2 id="delete-review-title">确认删除</h2>
        <p>确定要删除这道错题吗？删除后将从错题本中移除。</p>
        <div class="review-modal__actions">
          <button type="button" class="button button--secondary focus-ring" :disabled="removingIds.includes(deleteTarget.review_item_id)" @click="closeDeleteDialog">取消</button>
          <button type="button" class="button button--danger focus-ring" :disabled="removingIds.includes(deleteTarget.review_item_id)" @click="confirmDelete">
            {{ removingIds.includes(deleteTarget.review_item_id) ? "正在删除" : "确认删除" }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import ChatArea from "../components/ChatArea.vue";
import apiClient from "../services/apiClient";
import {
  deleteSessionReviewItem,
  startSessionDirectReviewRetest,
  startSessionReviewItem,
} from "../services/eduAgentApi";

const router = useRouter();
const sessionId = "student:data_structures";
const loading = ref(true);
const error = ref("");
const actionError = ref("");
const dashboard = ref({ mistakes: [], today_queue: [], weak_nodes: [] });
const activeTab = ref("pending");
const statusFilter = ref("all");
const errorTypeFilter = ref("all");
const searchQuery = ref("");
const sortMode = ref("priority");
const expandedIds = ref([]);
const startingIds = ref([]);
const removingIds = ref([]);
const deleteTarget = ref(null);

const tutorMessages = ref([]);
const tutorBusy = ref(false);
const tutorSuggestions = [
  "这道题考察了什么知识点？",
  "帮我分析一下这个错题的错误原因",
  "请出一道类似的题目让我巩固一下",
];

const mistakes = computed(() => Array.isArray(dashboard.value.mistakes) ? dashboard.value.mistakes : []);
const todayQueue = computed(() => Array.isArray(dashboard.value.today_queue) ? dashboard.value.today_queue : []);
const weakNodes = computed(() => Array.isArray(dashboard.value.weak_nodes) ? dashboard.value.weak_nodes : []);

const allReviewItems = computed(() => mistakes.value);

const actionableItems = computed(() => allReviewItems.value.filter((item) => item.status !== "completed"));
const actionableCount = computed(() => actionableItems.value.length);
const totalCount = computed(() => allReviewItems.value.length);
const completedCount = computed(() => allReviewItems.value.filter((item) => item.status === "completed").length);

const tabs = computed(() => [
  { key: "pending", label: "待处理", count: actionableItems.value.length },
  { key: "today", label: "今日到期", count: todayQueue.value.length },
  { key: "all", label: "全部错题", count: mistakes.value.length },
]);

const statusFilters = [
  { value: "all", label: "全部状态" },
  { value: "due", label: "待复习", dot: "warning" },
  { value: "in_progress", label: "复习中", dot: "primary" },
  { value: "completed", label: "已完成", dot: "success" },
];

const errorTypes = computed(() => {
  const values = new Set();
  for (const item of allReviewItems.value) {
    if (item.error_type) values.add(item.error_type);
  }
  return [...values].sort((left, right) => errorLabel(left).localeCompare(errorLabel(right), "zh-CN"));
});

const filteredItems = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  let source = allReviewItems.value;
  if (activeTab.value === "pending") source = actionableItems.value;
  if (activeTab.value === "today") source = uniqueItems(todayQueue.value);
  if (activeTab.value === "all") source = mistakes.value;

  const result = source.filter((item) => {
    if (statusFilter.value !== "all" && item.status !== statusFilter.value) return false;
    if (errorTypeFilter.value !== "all" && item.error_type !== errorTypeFilter.value) return false;
    if (!query) return true;
    const haystack = [item.question_prompt, item.node_title, item.node_id, item.explanation, errorLabel(item.error_type)]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });

  return [...result].sort((left, right) => {
    if (sortMode.value === "topic") {
      return String(left.node_title || left.node_id || "").localeCompare(String(right.node_title || right.node_id || ""), "zh-CN");
    }
    if (sortMode.value === "recent") {
      return dateValue(right.updated_at) - dateValue(left.updated_at);
    }
    return priorityValue(left) - priorityValue(right) || dateValue(right.updated_at) - dateValue(left.updated_at);
  });
});

function uniqueItems(items) {
  const seen = new Set();
  return items.filter((item) => {
    if (!item?.review_item_id || seen.has(item.review_item_id)) return false;
    seen.add(item.review_item_id);
    return true;
  });
}

function dateValue(value) {
  const timestamp = Date.parse(value || "");
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function priorityValue(item) {
  const statusRank = { due: 0, in_progress: 1, completed: 3 };
  const dueDate = dateValue(item.next_review_at);
  return (statusRank[item.status] ?? 2) * 10 ** 13 + (dueDate || Date.now());
}

function formatPercent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number * 100)}%` : "—";
}

function displayValue(value, fallback) {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

const REVIEW_TEXT_TRANSLATIONS = new Map([
  ["What should be checked before applying the method?", "应用该方法前需要检查什么？"],
  ["The number of comments", "注释数量"],
  ["Its preconditions", "它的前提条件"],
  ["Preconditions determine whether a method can preserve its invariant.", "前提条件决定方法能否保持其不变量。"],
  ["A boundary case violates a required assumption. What is the best response?", "边界情况违反了必要假设，最合适的处理方式是什么？"],
  ["Which statement best identifies the governing constraint of 算法复杂度分析?", "下面哪项最能准确说明算法复杂度分析的核心约束？"],
]);

function reviewText(value, kind, item = null) {
  const text = String(value || "").trim();
  if (!text) return text;

  const translated = REVIEW_TEXT_TRANSLATIONS.get(text);
  if (translated) return translated;
  if (!/[A-Za-z]{2,}/.test(text)) return text;
  if (/[{}()[\];=]|\b(def|class|return|import|const|let|function)\b/.test(text)) return text;

  if (kind === "node") return "当前知识点";
  if (kind === "question") {
    const nodeTitle = reviewText(item?.node_title || "当前知识点", "node");
    return `请结合“${nodeTitle}”的定义、约束和边界条件判断这道题。`;
  }
  if (kind === "answer") return "请根据题目要求和前提条件作答。";
  if (kind === "correct") return "请检查相关定义、约束和边界条件。";
  if (kind === "explanation") return "请根据题目中的定义、约束和边界条件进行判断。";
  return "暂无中文内容";
}

function chineseErrorMessage(value, fallback) {
  const message = String(value || "").trim();
  return /[\u3400-\u9fff]/.test(message) ? message : fallback;
}

function hasAnswerDetails(item) {
  return Boolean(item.original_answer || item.correct_answer || item.explanation);
}

function statusLabel(status) {
  return status === "due" ? "待复习" : status === "in_progress" ? "复习中" : status === "completed" ? "已完成" : "待处理";
}

function statusTone(status) {
  return status === "completed" ? "success" : status === "in_progress" ? "primary" : "warning";
}

function toggleExpanded(id) {
  expandedIds.value = expandedIds.value.includes(id)
    ? expandedIds.value.filter((value) => value !== id)
    : [...expandedIds.value, id];
}

function clearFilters() {
  searchQuery.value = "";
  statusFilter.value = "all";
  errorTypeFilter.value = "all";
}

function setItemState(id, patch) {
  for (const key of ["mistakes", "today_queue"]) {
    const list = Array.isArray(dashboard.value[key]) ? dashboard.value[key] : [];
    const index = list.findIndex((item) => item.review_item_id === id);
    if (index < 0) continue;
    dashboard.value[key] = list.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item);
  }
}

async function startReview(item) {
  if (!item?.review_item_id || startingIds.value.includes(item.review_item_id)) return;
  actionError.value = "";
  startingIds.value = [...startingIds.value, item.review_item_id];
  try {
    const result = await startSessionReviewItem(sessionId, item.review_item_id);
    if (result?.status !== "ok" || !result?.learning_task?.node_id) {
      throw new Error(result?.detail || "暂时无法打开这条复习任务，请稍后重试。");
    }
    setItemState(item.review_item_id, {
      status: result.review_item?.status || "in_progress",
      phase: result.learning_task.phase || "material_review",
    });
    const courseId = dashboard.value.course_id || "course-a";
    await router.push({
      name: "learn",
      params: { courseId, nodeId: result.learning_task.node_id },
      query: {
        reviewItem: item.review_item_id,
        reviewPhase: result.learning_task.phase || "material_review",
      },
    });
  } catch (requestError) {
    actionError.value = chineseErrorMessage(
      requestError?.response?.data?.detail,
      "暂时无法打开这条复习任务，请稍后重试。",
    );
  } finally {
    startingIds.value = startingIds.value.filter((id) => id !== item.review_item_id);
  }
}

function goBack() {
  router.push("/app");
}

async function startRetest(mode) {
  const candidates = mode === "today" ? todayQueue.value : actionableItems.value;
  const item = candidates.find((candidate) => candidate?.status !== "completed");
  if (!item) {
    actionError.value = mode === "today" ? "今天暂时没有可重刷的题目。" : "当前没有待处理的错题。";
    return;
  }
  actionError.value = "";
  startingIds.value = [...startingIds.value, item.review_item_id];
  try {
    const result = await startSessionDirectReviewRetest(sessionId, item.review_item_id);
    if (result?.status !== "ok" || !result?.learning_task?.node_id) {
      throw new Error(result?.detail || "暂时无法生成新的复测题，请稍后重试。");
    }
    setItemState(item.review_item_id, {
      status: result.review_item?.status || "in_progress",
      phase: "retest",
      retest_resource_id: result.learning_task.retest_resource_id || "",
    });
    await router.push({
      name: "retest",
      query: {
        mode,
        reviewItem: item.review_item_id,
        nodeId: result.learning_task.node_id,
        resourceId: result.learning_task.retest_resource_id || "",
      },
    });
  } catch (requestError) {
    actionError.value = chineseErrorMessage(
      requestError?.response?.data?.detail,
      requestError?.message || "暂时无法生成新的复测题，请稍后重试。",
    );
  } finally {
    startingIds.value = startingIds.value.filter((id) => id !== item.review_item_id);
  }
}

function requestDelete(item) {
  if (!item?.review_item_id || removingIds.value.includes(item.review_item_id)) return;
  deleteTarget.value = item;
}

function closeDeleteDialog() {
  if (!deleteTarget.value || removingIds.value.includes(deleteTarget.value.review_item_id)) return;
  deleteTarget.value = null;
}

async function confirmDelete() {
  const item = deleteTarget.value;
  if (!item?.review_item_id || removingIds.value.includes(item.review_item_id)) return;
  const id = item.review_item_id;
  actionError.value = "";
  removingIds.value = [...removingIds.value, id];
  try {
    const result = await deleteSessionReviewItem(sessionId, id);
    if (result?.status !== "deleted") {
      throw new Error("删除错题失败，请稍后重试。");
    }
    dashboard.value.mistakes = mistakes.value.filter((candidate) => candidate.review_item_id !== id);
    dashboard.value.today_queue = todayQueue.value.filter((candidate) => candidate.review_item_id !== id);
    expandedIds.value = expandedIds.value.filter((value) => value !== id);
    deleteTarget.value = null;
  } catch (requestError) {
    actionError.value = chineseErrorMessage(requestError?.response?.data?.detail, "删除错题失败，请稍后重试。");
  } finally {
    removingIds.value = removingIds.value.filter((value) => value !== id);
  }
}

function onTutorSend({ text }) {
  const userMsg = { id: `u-${Date.now()}`, role: "user", content: text };
  tutorMessages.value = [...tutorMessages.value, userMsg];
  const assistantId = `a-${Date.now()}`;
  tutorMessages.value = [...tutorMessages.value, { id: assistantId, role: "assistant", content: "", isStreaming: true }];
  tutorBusy.value = true;
  apiClient.post(`/sessions/${encodeURIComponent(sessionId)}/tutor-stream`, {
    question: `请始终使用简体中文回答，不要使用英文。用户问题：${text}`,
  }, {
    responseType: "stream",
    onDownloadProgress(event) {
      const chunk = event?.event?.target?.response || event?.currentTarget?.response || "";
      chunk.split("\n").filter((line) => line.startsWith("data: ")).forEach((line) => {
        try {
          const data = JSON.parse(line.slice(6));
          if (!data.token) return;
          const index = tutorMessages.value.findIndex((message) => message.id === assistantId);
          if (index >= 0) {
            const messages = [...tutorMessages.value];
            messages[index] = { ...messages[index], content: messages[index].content + data.token };
            tutorMessages.value = messages;
          }
        } catch (_) {
          // Stream chunks can split JSON across progress events.
        }
      });
    },
  }).then(() => {
    const index = tutorMessages.value.findIndex((message) => message.id === assistantId);
    if (index >= 0) {
      const messages = [...tutorMessages.value];
      messages[index] = { ...messages[index], isStreaming: false };
      tutorMessages.value = messages;
    }
  }).catch(() => {
    const index = tutorMessages.value.findIndex((message) => message.id === assistantId);
    if (index >= 0) {
      const messages = [...tutorMessages.value];
      messages[index] = { ...messages[index], isStreaming: false, content: messages[index].content || "辅导服务暂不可用。" };
      tutorMessages.value = messages;
    }
  }).finally(() => {
    tutorBusy.value = false;
  });
}

async function fetchData() {
  loading.value = true;
  error.value = "";
  try {
    const { data } = await apiClient.get(`/sessions/${encodeURIComponent(sessionId)}/review`);
    if (!data || data.status !== "ok") throw new Error(data?.detail || "复习队列暂时不可用，请原位重试。");
    dashboard.value = {
      ...dashboard.value,
      ...data,
      mistakes: Array.isArray(data.mistakes) ? data.mistakes : [],
      today_queue: Array.isArray(data.today_queue) ? data.today_queue : [],
      weak_nodes: Array.isArray(data.weak_nodes) ? data.weak_nodes : [],
    };
    activeTab.value = actionableCount.value ? "pending" : "today";
  } catch (requestError) {
    error.value = chineseErrorMessage(
      requestError?.response?.data?.detail,
      "复习队列暂时不可用，请原位重试。",
    );
  } finally {
    loading.value = false;
  }
}

function errorLabel(type) {
  if (!type) return "其他";
  const key = String(type).toLowerCase().replace(/[\s-]+/g, "_");
  const map = {
    definition: "概念不清",
    understanding: "理解有误",
    application: "不会应用",
    concept: "概念错误",
    concept_understanding: "概念理解",
    concept_application: "概念应用",
    syntax_error: "语法错误",
    wrong_answer: "答案错误",
    runtime_error: "运行错误",
    time_limit: "超时",
    internal_error: "系统错误",
    code_error: "代码错误",
    logic_error: "逻辑错误",
    memory_limit: "内存超限",
    output_error: "输出错误",
    compilation_error: "编译错误",
    semantic_error: "语义错误",
    incomplete: "未完成",
    boundary: "边界条件",
    boundary_condition: "边界条件",
    edge_case: "边界情况",
    design_error: "设计错误",
    type_error: "类型错误",
    null_pointer: "空值错误",
    off_by_one: "差一错误",
    infinite_loop: "死循环",
    stack_overflow: "栈溢出",
    index_error: "索引错误",
    key_error: "键值错误",
    value_error: "数值错误",
    timeout: "超时",
    resource_error: "资源错误",
    network_error: "网络错误",
    assertion_error: "断言失败",
    arithmetic_error: "算术错误",
    overflow: "溢出",
    underflow: "下溢",
    precision: "精度问题",
    rounding: "舍入错误",
  };
  return map[key] || "其他错误";
}

onMounted(() => {
  fetchData();
});
</script>

<style scoped>
.review-page {
  --review-ink: var(--text-primary);
  --review-muted: var(--text-muted);
  --review-subtle: color-mix(in srgb, var(--text-muted) 70%, transparent);
  --review-line: color-mix(in srgb, var(--border-subtle) 88%, var(--text-primary) 12%);
  --review-surface: color-mix(in srgb, var(--space-surface) 94%, white 6%);
  background: var(--space-bg);
  color: var(--review-ink);
}

.review-topbar {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  border-bottom: 1px solid var(--review-line);
  background: color-mix(in srgb, var(--space-panel) 96%, transparent);
  backdrop-filter: blur(18px);
}

.review-topbar__inner {
  width: min(1440px, calc(100% - 48px));
  min-height: 68px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.review-topbar__left,
.review-topbar__right,
.review-brand,
.review-item__meta,
.review-item__footer,
.review-list-header,
.review-list-header__tools,
.review-tabs,
.review-filters,
.review-hero__signal,
.focus-strip__heading,
.focus-node__topline {
  display: flex;
  align-items: center;
}

.review-topbar__left,
.review-brand {
  gap: 12px;
}

.review-topbar__right {
  gap: 16px;
}

.review-topbar__label {
  color: var(--review-muted);
  font-size: 13px;
}

.icon-button {
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--review-line);
  border-radius: 10px;
  color: var(--review-muted);
  background: transparent;
  transition: border-color 180ms ease, color 180ms ease, background 180ms ease;
}

.icon-button:hover {
  border-color: var(--border-hover);
  color: var(--review-ink);
  background: var(--card-bg-hover);
}

.icon-button svg {
  width: 19px;
  height: 19px;
}

.review-brand__mark {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  color: var(--color-primary-text);
  background: var(--color-primary);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.02em;
}

.review-brand__name {
  margin: 0;
  color: var(--review-ink);
  font-size: 14px;
  font-weight: 750;
  line-height: 1.2;
}

.review-brand__context {
  margin: 3px 0 0;
  color: var(--review-muted);
  font-size: 11px;
  line-height: 1.2;
}

.review-layout {
  width: min(1440px, calc(100% - 48px));
  min-height: calc(100vh - 68px);
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
}

.review-content {
  min-width: 0;
  padding: 48px clamp(24px, 4vw, 64px) 80px 0;
}

.review-tutor {
  position: fixed;
  top: 68px;
  right: max(24px, calc((100vw - 1440px) / 2));
  z-index: var(--z-sticky);
  width: 340px;
  height: calc(100dvh - 68px);
  max-height: calc(100dvh - 68px);
  min-height: 0;
  overflow: hidden;
  border-left: 1px solid var(--review-line);
  background: color-mix(in srgb, var(--space-surface) 75%, transparent);
}

.review-tutor__header {
  min-height: 90px;
  padding: 22px 24px 18px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--review-line);
}

.review-tutor__eyebrow,
.review-hero__eyebrow {
  margin: 0 0 7px;
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.review-tutor h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 750;
}

.review-tutor__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding-top: 2px;
  color: var(--review-muted);
  font-size: 11px;
}

.review-tutor__status span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
}

.review-tutor__body {
  height: calc(100% - 90px);
  min-height: 0;
  overflow: hidden;
}

.review-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 32px;
  padding-bottom: 36px;
}

.review-hero h1 {
  max-width: 620px;
  margin: 0;
  color: var(--review-ink);
  font-size: clamp(28px, 3.2vw, 46px);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.12;
}

.review-hero__description {
  max-width: 560px;
  margin: 14px 0 0;
  color: var(--review-muted);
  font-size: 15px;
  line-height: 1.8;
}

.review-hero__signal {
  flex: 0 0 auto;
  min-width: 220px;
  gap: 12px;
  padding: 15px 17px;
  border: 1px solid color-mix(in srgb, var(--color-warning) 30%, var(--review-line));
  border-radius: 12px;
  background: color-mix(in srgb, var(--color-warning-soft) 58%, var(--review-surface));
}

.review-hero__signal--clear {
  border-color: color-mix(in srgb, var(--color-success) 32%, var(--review-line));
  background: color-mix(in srgb, var(--color-success-soft) 56%, var(--review-surface));
}

.signal-ring {
  width: 38px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: var(--color-warning-dark);
  background: var(--color-warning-soft);
}

.review-hero__signal--clear .signal-ring {
  color: var(--color-success-dark);
  background: var(--color-success-soft);
}

.signal-ring svg {
  width: 19px;
  height: 19px;
}

.review-hero__signal-label,
.review-hero__signal strong {
  display: block;
}

.review-hero__signal-label {
  color: var(--review-muted);
  font-size: 11px;
}

.review-hero__signal strong {
  margin-top: 3px;
  color: var(--review-ink);
  font-size: 13px;
}

.review-retest-cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin: 0 0 8px;
  padding: 20px 22px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 24%, var(--review-line));
  border-radius: 14px;
  background: color-mix(in srgb, var(--color-primary-soft) 64%, var(--review-surface));
}

.review-retest-cta__copy,
.review-retest-cta__actions {
  display: flex;
  align-items: center;
}

.review-retest-cta__copy {
  gap: 13px;
}

.review-retest-cta__icon {
  width: 42px;
  height: 42px;
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 11px;
  color: var(--color-primary-dark);
  background: var(--color-primary-soft);
}

.review-retest-cta__icon svg {
  width: 21px;
  height: 21px;
}

.review-retest-cta h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 780;
}

.review-retest-cta p {
  max-width: 560px;
  margin: 5px 0 0;
  color: var(--review-muted);
  font-size: 12px;
  line-height: 1.6;
}

.review-retest-cta__actions {
  flex: 0 0 auto;
  gap: 9px;
}

.review-retest-cta__actions .button {
  min-height: 40px;
  white-space: nowrap;
}

.review-retest-cta__actions .button svg {
  width: 16px;
  height: 16px;
}

.review-retest-cta__count {
  min-width: 20px;
  padding: 2px 6px;
  border-radius: 999px;
  color: currentColor;
  background: color-mix(in srgb, currentColor 14%, transparent);
  font-size: 11px;
  text-align: center;
}

.review-overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border-top: 1px solid var(--review-line);
  border-bottom: 1px solid var(--review-line);
}

.overview-item {
  min-width: 0;
  padding: 18px 18px 20px 0;
}

.overview-item + .overview-item {
  padding-left: 18px;
  border-left: 1px solid var(--review-line);
}

.overview-item__label,
.overview-item__hint {
  display: block;
}

.overview-item__label {
  color: var(--review-muted);
  font-size: 12px;
}

.overview-item strong {
  display: block;
  margin-top: 8px;
  color: var(--review-ink);
  font-size: 24px;
  font-weight: 780;
  line-height: 1;
}

.overview-item__hint {
  overflow: hidden;
  margin-top: 9px;
  color: var(--review-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overview-item--attention strong {
  color: var(--color-warning-dark);
}

.overview-item--focus strong {
  color: var(--color-primary-dark);
}

.focus-strip {
  margin-top: 28px;
  padding: 18px 20px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 22%, var(--review-line));
  border-radius: 12px;
  background: color-mix(in srgb, var(--color-primary-soft) 40%, var(--review-surface));
}

.focus-strip__heading {
  gap: 10px;
}

.focus-strip__dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--color-primary);
}

.focus-strip__title,
.focus-strip__copy {
  margin: 0;
}

.focus-strip__title {
  color: var(--review-ink);
  font-size: 13px;
  font-weight: 750;
}

.focus-strip__copy {
  margin-top: 3px;
  color: var(--review-muted);
  font-size: 12px;
}

.focus-strip__nodes {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}

.focus-node__topline {
  justify-content: space-between;
  gap: 12px;
  color: var(--review-ink);
  font-size: 12px;
}

.focus-node__topline span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.focus-node__topline strong {
  color: var(--color-primary-dark);
  font-size: 12px;
}

.focus-node__track {
  height: 5px;
  margin-top: 9px;
  overflow: hidden;
  border-radius: 99px;
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
}

.focus-node__track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--color-primary);
}

.focus-node small {
  display: block;
  margin-top: 7px;
  color: var(--review-muted);
  font-size: 11px;
}

.review-list-section {
  margin-top: 44px;
}

.review-list-header {
  justify-content: space-between;
  gap: 24px;
}

.review-list-header h2 {
  margin: 0;
  font-size: 19px;
  font-weight: 780;
}

.review-list-header p {
  margin: 6px 0 0;
  color: var(--review-muted);
  font-size: 12px;
}

.review-list-header__tools {
  gap: 8px;
}

.search-field,
.select-field,
.type-filter {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.search-field {
  width: 210px;
}

.search-field svg {
  position: absolute;
  left: 12px;
  width: 16px;
  height: 16px;
  color: var(--review-muted);
  pointer-events: none;
}

.search-field input,
.select-field select,
.type-filter select {
  min-height: 40px;
  border: 1px solid var(--review-line);
  border-radius: 9px;
  color: var(--review-ink);
  background: var(--review-surface);
  font-size: 12px;
  outline: none;
  transition: border-color 180ms ease, box-shadow 180ms ease;
}

.search-field input {
  width: 100%;
  padding: 0 12px 0 36px;
}

.search-field input::placeholder {
  color: var(--review-muted);
}

.search-field input:focus,
.select-field select:focus,
.type-filter select:focus {
  border-color: var(--border-strong);
  box-shadow: 0 0 0 3px var(--focus-ring-color);
}

.select-field select,
.type-filter select {
  padding: 0 34px 0 12px;
  appearance: none;
}

.select-field svg {
  position: absolute;
  right: 11px;
  width: 14px;
  height: 14px;
  color: var(--review-muted);
  pointer-events: none;
}

.review-tabs {
  margin-top: 26px;
  gap: 24px;
  overflow-x: auto;
  border-bottom: 1px solid var(--review-line);
}

.review-tab {
  position: relative;
  min-height: 43px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  flex: 0 0 auto;
  border: 0;
  color: var(--review-muted);
  background: transparent;
  font-size: 13px;
  font-weight: 650;
  white-space: nowrap;
}

.review-tab::after {
  content: "";
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 2px;
  background: transparent;
}

.review-tab span {
  min-width: 18px;
  padding: 2px 5px;
  border-radius: 99px;
  color: var(--review-muted);
  background: var(--card-bg-hover);
  font-size: 10px;
  text-align: center;
}

.review-tab:hover,
.review-tab--active {
  color: var(--color-primary-dark);
}

.review-tab--active::after {
  background: var(--color-primary);
}

.review-tab--active span {
  color: var(--color-primary-dark);
  background: var(--color-primary-soft);
}

.review-filters {
  justify-content: space-between;
  gap: 16px;
  padding: 14px 0 4px;
}

.filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.filter-chip {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 99px;
  color: var(--review-muted);
  background: transparent;
  font-size: 11px;
}

.filter-chip:hover,
.filter-chip--active {
  border-color: var(--review-line);
  color: var(--review-ink);
  background: var(--review-surface);
}

.filter-chip--active {
  box-shadow: var(--shadow-xs);
}

.filter-chip__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.filter-chip__dot--warning {
  background: var(--color-warning);
}

.filter-chip__dot--primary {
  background: var(--color-primary);
}

.filter-chip__dot--success {
  background: var(--color-success);
}

.type-filter {
  gap: 8px;
  color: var(--review-muted);
  font-size: 11px;
}

.type-filter select {
  min-height: 32px;
  padding-top: 0;
  padding-bottom: 0;
  font-size: 11px;
}

.review-items {
  position: relative;
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.review-item {
  position: relative;
  overflow: hidden;
  display: flex;
  border: 1px solid var(--review-line);
  border-radius: 11px;
  background: var(--review-surface);
  transition: border-color 180ms ease, background 180ms ease, transform 180ms ease, opacity 180ms ease;
}

.review-item:hover {
  border-color: var(--border-hover);
  background: color-mix(in srgb, var(--card-bg-hover) 35%, var(--review-surface));
}

.review-item--removing {
  opacity: 0;
  transform: translateX(12px);
}

.review-item__status {
  width: 4px;
  flex: 0 0 auto;
}

.review-item__status--warning {
  background: var(--color-warning);
}

.review-item__status--primary {
  background: var(--color-primary);
}

.review-item__status--success {
  background: var(--color-success);
}

.review-item__body {
  min-width: 0;
  flex: 1;
  padding: 17px 18px 15px;
}

.review-item__meta {
  flex-wrap: wrap;
  gap: 7px;
}

.item-tag {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 750;
}

.item-tag--error {
  color: var(--color-error-dark);
  background: var(--color-error-soft);
}

.item-tag--info {
  color: var(--color-info-dark);
  background: var(--color-info-soft);
}

.item-meta-text {
  color: var(--review-muted);
  font-size: 11px;
}

.item-meta-separator {
  color: var(--review-subtle);
  font-size: 12px;
}

.review-item h3 {
  max-width: 760px;
  margin: 12px 0 0;
  color: var(--review-ink);
  font-size: 15px;
  font-weight: 680;
  line-height: 1.7;
}

.review-item__details {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid var(--review-line);
}

.answer-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.answer-block {
  min-width: 0;
  padding: 11px 12px;
  border-radius: 8px;
}

.answer-block span,
.answer-block strong {
  display: block;
}

.answer-block span {
  color: var(--review-muted);
  font-size: 10px;
}

.answer-block strong {
  margin-top: 6px;
  overflow-wrap: anywhere;
  font-size: 13px;
  font-weight: 680;
  line-height: 1.55;
}

.answer-block--wrong {
  background: var(--color-error-soft);
}

.answer-block--wrong strong {
  color: var(--color-error-dark);
}

.answer-block--correct {
  background: var(--color-success-soft);
}

.answer-block--correct strong {
  color: var(--color-success-dark);
}

.explanation-block {
  margin-top: 10px;
  padding: 12px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-primary-soft) 38%, var(--review-surface));
}

.explanation-block span {
  color: var(--color-primary-dark);
  font-size: 10px;
  font-weight: 750;
}

.explanation-block p {
  margin: 6px 0 0;
  color: var(--review-ink);
  font-size: 12px;
  line-height: 1.7;
}

.review-item__footer {
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
}

.review-item__delete {
  width: auto;
  height: 36px;
  min-width: 36px;
  gap: 6px;
  padding: 0 10px;
  margin-left: auto;
  border-color: color-mix(in srgb, var(--color-error) 22%, var(--review-line));
  color: var(--color-error-dark);
  background: var(--color-error-soft);
}

.review-item__delete:hover:not(:disabled) {
  border-color: var(--color-error);
  background: color-mix(in srgb, var(--color-error-soft) 78%, white 22%);
}

.review-item__delete svg {
  width: 16px;
  height: 16px;
}

.review-item__delete span {
  font-size: 12px;
  font-weight: 700;
}

.text-button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 36px;
  padding: 0;
  border: 0;
  color: var(--color-primary-dark);
  background: transparent;
  font-size: 12px;
  font-weight: 650;
}

.text-button:hover {
  color: var(--color-primary);
}

.text-button svg {
  width: 14px;
  height: 14px;
  transition: transform 180ms ease;
}

.text-button__icon--up {
  transform: rotate(180deg);
}

.review-item__footer-note {
  color: var(--review-muted);
  font-size: 11px;
}

.completed-mark {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--color-success-dark);
  font-size: 12px;
  font-weight: 650;
}

.completed-mark svg {
  width: 15px;
  height: 15px;
}

.button {
  min-height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 15px;
  border: 1px solid transparent;
  border-radius: 9px;
  font-size: 12px;
  font-weight: 700;
  transition: background 180ms ease, border-color 180ms ease, color 180ms ease, transform 180ms ease;
}

.button:hover:not(:disabled) {
  transform: translateY(-1px);
}

.button:disabled {
  opacity: 0.56;
  cursor: not-allowed;
}

.button svg {
  width: 15px;
  height: 15px;
}

.button--compact {
  min-height: 38px;
  padding-right: 12px;
  padding-left: 12px;
}

.button--primary {
  color: var(--color-primary-text);
  background: var(--color-primary);
}

.button--primary:hover:not(:disabled) {
  background: var(--color-primary-light);
}

.button--secondary {
  color: var(--color-primary-dark);
  border-color: color-mix(in srgb, var(--color-primary) 35%, var(--review-line));
  background: var(--color-primary-soft);
}

.button--secondary:hover:not(:disabled) {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary-soft) 80%, white 20%);
}

.button--danger {
  color: var(--color-primary-text);
  background: var(--color-error);
}

.button--danger:hover:not(:disabled) {
  background: var(--color-error-dark);
}

.button__chevron {
  width: 13px !important;
  height: 13px !important;
  margin-left: 1px;
}

.review-action-menu {
  position: relative;
}

.review-action-menu__panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: var(--z-dropdown);
  width: 210px;
  padding: 5px;
  border: 1px solid var(--review-line);
  border-radius: 10px;
  background: var(--review-surface);
  box-shadow: var(--shadow-md);
}

.menu-item {
  width: 100%;
  min-height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 10px;
  border: 0;
  border-radius: 7px;
  color: var(--review-ink);
  background: transparent;
  font-size: 12px;
  text-align: left;
}

.menu-item:hover:not(:disabled) {
  background: var(--card-bg-hover);
}

.menu-item:disabled {
  color: var(--review-muted);
  cursor: not-allowed;
}

.menu-item__count {
  color: var(--review-muted);
  font-size: 11px;
}

.state-panel {
  min-height: 560px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  text-align: center;
}

.state-panel h1,
.state-panel p {
  margin: 0;
}

.state-panel h1 {
  font-size: 20px;
  font-weight: 780;
}

.state-panel p {
  max-width: 460px;
  margin-top: 10px;
  color: var(--review-muted);
  font-size: 13px;
  line-height: 1.7;
}

.state-panel .button {
  margin-top: 22px;
}

.state-panel__icon {
  width: 52px;
  height: 52px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 18px;
  border-radius: 50%;
}

.state-panel__icon svg {
  width: 25px;
  height: 25px;
}

.state-panel__icon--error {
  color: var(--color-error-dark);
  background: var(--color-error-soft);
}

.skeleton-heading,
.skeleton-copy,
.skeleton-card {
  background: color-mix(in srgb, var(--review-muted) 12%, transparent);
  animation: review-pulse 1.3s ease-in-out infinite;
}

.skeleton-heading {
  width: min(360px, 70%);
  height: 34px;
  border-radius: 7px;
}

.skeleton-copy {
  width: min(520px, 90%);
  height: 15px;
  margin-top: 15px;
  border-radius: 6px;
}

.skeleton-list {
  width: 100%;
  margin-top: 44px;
  display: grid;
  gap: 10px;
}

.skeleton-card {
  height: 112px;
  border-radius: 11px;
}

.list-empty {
  min-height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  padding: 32px 20px;
  border: 1px dashed var(--review-line);
  border-radius: 11px;
  text-align: center;
}

.list-empty__icon {
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: var(--color-primary-dark);
  background: var(--color-primary-soft);
}

.list-empty__icon svg {
  width: 21px;
  height: 21px;
}

.list-empty h3 {
  margin: 16px 0 0;
  font-size: 14px;
  font-weight: 750;
}

.list-empty p {
  max-width: 360px;
  margin: 7px 0 0;
  color: var(--review-muted);
  font-size: 12px;
  line-height: 1.7;
}

.list-empty .text-button {
  margin-top: 16px;
}

.review-toast {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: var(--z-toast);
  max-width: min(420px, calc(100% - 48px));
  margin: 0;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--color-error) 28%, var(--review-line));
  border-radius: 9px;
  color: var(--color-error-dark);
  background: color-mix(in srgb, var(--color-error-soft) 80%, var(--review-surface));
  box-shadow: var(--shadow-sm);
  font-size: 12px;
}

.review-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: center;
  padding: 24px;
  background: color-mix(in srgb, var(--space-bg) 70%, transparent);
  backdrop-filter: blur(5px);
}

.review-modal {
  position: relative;
  width: min(420px, 100%);
  padding: 28px;
  border: 1px solid var(--review-line);
  border-radius: 14px;
  color: var(--review-ink);
  background: var(--review-surface);
  box-shadow: var(--shadow-lg, 0 18px 55px rgb(0 0 0 / 18%));
  text-align: center;
}

.review-modal__close {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 32px;
  height: 32px;
  min-width: 32px;
  border: 0;
  background: transparent;
}

.review-modal__close svg {
  width: 17px;
  height: 17px;
}

.review-modal__icon {
  width: 42px;
  height: 42px;
  margin: 0 auto 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: var(--color-error-dark);
  background: var(--color-error-soft);
}

.review-modal__icon svg {
  width: 22px;
  height: 22px;
}

.review-modal h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 760;
}

.review-modal p {
  margin: 10px 0 0;
  color: var(--review-muted);
  font-size: 13px;
  line-height: 1.7;
}

.review-modal__actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-top: 22px;
}

.button-loader {
  width: 13px;
  height: 13px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: review-spin 0.7s linear infinite;
}

.review-item-enter-active,
.review-item-leave-active {
  position: absolute;
  width: 100%;
  z-index: 0;
  transition: opacity 240ms ease, transform 240ms ease;
  pointer-events: none;
}

.review-item-move {
  transition: transform 340ms cubic-bezier(0.22, 1, 0.36, 1);
}

.review-item-enter-from,
.review-item-leave-to {
  opacity: 0;
  transform: translateX(18px) scale(0.985);
}

@keyframes review-pulse {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 0.82; }
}

@keyframes review-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .review-page *,
  .review-page *::before,
  .review-page *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}

@media (max-width: 1180px) {
  .review-layout,
  .review-topbar__inner {
    width: min(100% - 32px, 1000px);
  }

  .review-layout {
    grid-template-columns: minmax(0, 1fr) 300px;
  }

  .review-content {
    padding-right: 32px;
  }

  .review-tutor {
    right: max(16px, calc((100vw - 1000px) / 2));
    width: 300px;
  }

  .review-hero__signal {
    min-width: 190px;
  }
}

@media (max-width: 920px) {
  .review-layout {
    display: block;
  }

  .review-content {
    padding-right: 0;
  }

  .review-tutor {
    position: static;
    width: auto;
    height: auto;
    max-height: none;
    min-height: 0;
    overflow: visible;
    margin: 0 auto 32px;
    border-top: 1px solid var(--review-line);
    border-left: 0;
  }

  .review-tutor__body {
    height: 500px;
    min-height: 0;
  }
}

@media (max-width: 720px) {
  .review-topbar__inner,
  .review-layout {
    width: min(100% - 28px, 100%);
  }

  .review-topbar__inner {
    min-height: 62px;
  }

  .review-topbar__label {
    display: none;
  }

  .review-content {
    padding: 32px 0 56px;
  }

  .review-hero {
    align-items: flex-start;
    flex-direction: column;
    gap: 20px;
    padding-bottom: 28px;
  }

  .review-hero h1 {
    font-size: 30px;
  }

  .review-hero__signal {
    width: 100%;
  }

  .review-retest-cta {
    align-items: stretch;
    flex-direction: column;
    gap: 16px;
    padding: 18px;
  }

  .review-retest-cta__actions {
    flex-direction: column;
    align-items: stretch;
  }

  .review-retest-cta__actions .button {
    justify-content: center;
  }

  .review-overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .overview-item {
    padding: 16px 14px 17px 0;
  }

  .overview-item + .overview-item {
    padding-left: 14px;
  }

  .overview-item:nth-child(3) {
    border-top: 1px solid var(--review-line);
  }

  .overview-item:nth-child(4) {
    border-top: 1px solid var(--review-line);
  }

  .focus-strip__nodes {
    grid-template-columns: 1fr;
    gap: 14px;
  }

  .review-list-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 14px;
  }

  .review-list-header__tools,
  .search-field,
  .select-field {
    width: 100%;
  }

  .review-list-header__tools {
    flex-direction: column;
    align-items: stretch;
  }

  .review-filters {
    align-items: flex-start;
    flex-direction: column;
  }

  .review-tabs {
    gap: 18px;
  }

  .answer-grid {
    grid-template-columns: 1fr;
  }

  .review-item__footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .review-item__footer .button,
  .review-item__footer .completed-mark {
    align-self: stretch;
  }

  .review-item__footer .button {
    width: 100%;
  }

  .review-item__delete {
    align-self: flex-end;
    margin-left: 0;
  }

  .review-tutor__body {
    height: 560px;
  }
}
</style>
