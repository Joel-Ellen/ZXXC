<template>
  <section
    class="resource-annotations"
    :data-bookmarked="isBookmarked ? 'true' : 'false'"
    aria-label="学习笔记和划线"
  >
    <div class="resource-annotations__composer">
      <div class="resource-annotations__heading-row">
        <div>
          <p class="resource-annotations__eyebrow">学习注记</p>
          <h4 class="resource-annotations__title">笔记与划线</h4>
        </div>
        <span v-if="orderedAnnotations.length" class="resource-annotations__count">
          {{ orderedAnnotations.length }} 条
        </span>
      </div>

      <label class="resource-annotations__label" :for="noteInputId">添加笔记</label>
      <textarea
        :id="noteInputId"
        v-model="noteDraft"
        class="resource-annotations__textarea"
        rows="3"
        maxlength="32000"
        placeholder="记录你的理解、疑问或下一步行动..."
        @keydown.ctrl.enter.exact.prevent="saveNote"
        @keydown.meta.enter.exact.prevent="saveNote"
      />
      <div class="resource-annotations__composer-actions">
        <span class="resource-annotations__helper">Ctrl / Cmd + Enter 保存</span>
        <button
          type="button"
          class="resource-annotations__button resource-annotations__button--primary"
          :disabled="!canSaveNote"
          @click="saveNote"
        >
          保存笔记
        </button>
      </div>
    </div>

    <div v-if="canHighlight" class="resource-annotations__highlight">
      <div class="resource-annotations__highlight-copy">
        <p class="resource-annotations__label">当前选中文本</p>
        <p
          class="resource-annotations__selection"
          :class="{ 'is-empty': !hasSelectedText }"
        >
          {{ hasSelectedText ? selectedText : "在学习内容中选中一段文字后，可将它保存为划线。" }}
        </p>
      </div>
      <div class="resource-annotations__highlight-actions">
        <label class="resource-annotations__color-control">
          <span>划线颜色</span>
          <input v-model="highlightColor" type="color" aria-label="选择划线颜色">
        </label>
        <button
          v-if="hasSelectedText"
          type="button"
          class="resource-annotations__button resource-annotations__button--secondary"
          @mousedown.prevent
          @click="saveHighlight"
        >
          保存划线
        </button>
      </div>
    </div>

    <section
      v-if="orderedAnnotations.length"
      class="resource-annotations__saved"
      aria-label="已保存的笔记和划线"
    >
      <p class="resource-annotations__label">已保存</p>
      <ul class="resource-annotations__list">
        <li
          v-for="annotation in orderedAnnotations"
          :key="annotationKey(annotation)"
          class="resource-annotations__item"
          :class="`is-${annotationKind(annotation)}`"
          :style="annotationStyle(annotation)"
        >
          <div class="resource-annotations__item-header">
            <span class="resource-annotations__kind">{{ annotationKindLabel(annotation) }}</span>
            <button
              v-if="annotationKey(annotation)"
              type="button"
              class="resource-annotations__remove"
              :aria-label="`删除${annotationKindLabel(annotation)}`"
              @click="removeAnnotation(annotation)"
            >
              删除
            </button>
          </div>
          <p class="resource-annotations__item-content">{{ annotationText(annotation) }}</p>
        </li>
      </ul>
    </section>
  </section>
</template>

<script setup>
import { computed, getCurrentInstance, ref } from "vue";

const props = defineProps({
  annotations: { type: Array, default: () => [] },
  canHighlight: { type: Boolean, default: false },
  selectedText: { type: String, default: "" },
  isBookmarked: { type: Boolean, default: false },
});

const emit = defineEmits(["save-note", "save-highlight", "remove"]);

const noteDraft = ref("");
const highlightColor = ref("#F4C95D");
const noteInputId = `resource-annotation-note-${getCurrentInstance()?.uid ?? "input"}`;

const hasSelectedText = computed(() => Boolean(props.selectedText.trim()));
const canSaveNote = computed(() => Boolean(noteDraft.value.trim()));
const orderedAnnotations = computed(() => [...props.annotations]
  .filter((annotation) => annotation && typeof annotation === "object")
  .sort((left, right) => annotationTimestamp(right) - annotationTimestamp(left)));

function saveNote() {
  const content = noteDraft.value.trim();
  if (!content) return;
  emit("save-note", content);
  noteDraft.value = "";
}

function saveHighlight() {
  const selectedText = props.selectedText.trim();
  if (!selectedText) return;
  emit("save-highlight", { selectedText, color: highlightColor.value });
}

function removeAnnotation(annotation) {
  const key = annotationKey(annotation);
  if (key) emit("remove", key);
}

function annotationKey(annotation) {
  return String(annotation?.id || annotation?.key || annotation?.annotation_id || "");
}

function annotationKind(annotation) {
  return String(annotation?.kind || annotation?.type || "note").toLowerCase() === "highlight"
    ? "highlight"
    : "note";
}

function annotationKindLabel(annotation) {
  return annotationKind(annotation) === "highlight" ? "划线" : "笔记";
}

function annotationText(annotation) {
  const candidate = annotationKind(annotation) === "highlight"
    ? annotation?.selected_text ?? annotation?.selectedText ?? annotation?.quote ?? annotation?.content
    : annotation?.content ?? annotation?.note ?? annotation?.text;
  return String(candidate || "未命名注记");
}

function annotationTimestamp(annotation) {
  const timestamp = Date.parse(String(annotation?.updated_at || annotation?.created_at || ""));
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function annotationStyle(annotation) {
  const color = String(annotation?.color || "");
  return /^#[0-9a-f]{3,8}$/i.test(color) ? { "--annotation-color": color } : {};
}
</script>

<style scoped>
.resource-annotations {
  display: grid;
  gap: 0.75rem;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-subtle);
}

.resource-annotations__composer,
.resource-annotations__highlight,
.resource-annotations__saved {
  min-width: 0;
  padding: 0.75rem;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: color-mix(in srgb, var(--card-bg) 86%, var(--space-elevated));
}

.resource-annotations__heading-row,
.resource-annotations__composer-actions,
.resource-annotations__highlight-actions,
.resource-annotations__item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.625rem;
}

.resource-annotations__eyebrow,
.resource-annotations__label,
.resource-annotations__helper,
.resource-annotations__count,
.resource-annotations__kind,
.resource-annotations__color-control {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.6875rem;
  font-weight: 700;
  line-height: 1.4;
}

.resource-annotations__eyebrow {
  font-size: 0.625rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.resource-annotations__title {
  margin: 0.2rem 0 0;
  color: var(--text-primary);
  font-size: 0.875rem;
  font-weight: 700;
  line-height: 1.35;
}

.resource-annotations__count,
.resource-annotations__kind {
  flex: none;
  border-radius: 999px;
  padding: 0.2rem 0.5rem;
  background: var(--card-bg-hover);
}

.resource-annotations__label {
  display: block;
  margin-top: 0.75rem;
}

.resource-annotations__textarea {
  display: block;
  box-sizing: border-box;
  width: 100%;
  min-height: 4.5rem;
  margin-top: 0.4rem;
  padding: 0.625rem 0.7rem;
  resize: vertical;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--input-bg);
  color: var(--text-primary);
  font: inherit;
  font-size: 0.8125rem;
  line-height: 1.55;
}

.resource-annotations__textarea::placeholder {
  color: var(--text-muted);
}

.resource-annotations__textarea:focus-visible,
.resource-annotations__button:focus-visible,
.resource-annotations__remove:focus-visible,
.resource-annotations__color-control input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.resource-annotations__composer-actions {
  margin-top: 0.625rem;
}

.resource-annotations__button,
.resource-annotations__remove {
  flex: none;
  min-height: 2.75rem;
  border: 1px solid transparent;
  border-radius: 8px;
  font: inherit;
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease;
}

.resource-annotations__button {
  padding: 0.55rem 0.7rem;
}

.resource-annotations__button--primary {
  background: var(--color-primary);
  color: var(--color-primary-text);
}

.resource-annotations__button--primary:hover:not(:disabled) {
  background: var(--color-primary-dark);
}

.resource-annotations__button--secondary {
  border-color: color-mix(in srgb, var(--color-warning) 48%, var(--border-subtle));
  background: var(--color-warning-soft);
  color: var(--color-warning-dark);
}

.resource-annotations__button--secondary:hover {
  background: color-mix(in srgb, var(--color-warning-soft) 70%, var(--color-warning));
}

.resource-annotations__button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.resource-annotations__highlight {
  display: grid;
  gap: 0.625rem;
}

.resource-annotations__highlight-copy .resource-annotations__label {
  margin-top: 0;
}

.resource-annotations__selection,
.resource-annotations__item-content {
  margin: 0.35rem 0 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.resource-annotations__selection {
  max-height: 5rem;
  overflow: auto;
  color: var(--text-secondary);
  font-size: 0.8125rem;
  line-height: 1.55;
}

.resource-annotations__selection.is-empty {
  color: var(--text-muted);
}

.resource-annotations__highlight-actions {
  align-items: flex-end;
}

.resource-annotations__color-control {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.resource-annotations__color-control input {
  width: 2.75rem;
  height: 2.75rem;
  padding: 0.125rem;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: var(--input-bg);
  cursor: pointer;
}

.resource-annotations__saved > .resource-annotations__label {
  margin-top: 0;
}

.resource-annotations__list {
  display: grid;
  gap: 0.5rem;
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
}

.resource-annotations__item {
  min-width: 0;
  padding: 0.625rem;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--space-panel);
}

.resource-annotations__item.is-highlight {
  background: color-mix(in srgb, var(--annotation-color, var(--color-warning)) 13%, var(--space-panel));
}

.resource-annotations__kind {
  padding: 0.15rem 0.45rem;
}

.resource-annotations__item.is-highlight .resource-annotations__kind {
  color: var(--color-warning-dark);
  background: var(--color-warning-soft);
}

.resource-annotations__item-content {
  color: var(--text-secondary);
  font-size: 0.8125rem;
  line-height: 1.55;
}

.resource-annotations__remove {
  min-width: 2.75rem;
  padding: 0.35rem 0.45rem;
  background: transparent;
  color: var(--text-muted);
}

.resource-annotations__remove:hover {
  border-color: var(--color-error-soft);
  background: var(--color-error-soft);
  color: var(--color-error-dark);
}

@media (max-width: 480px) {
  .resource-annotations__composer-actions,
  .resource-annotations__highlight-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .resource-annotations__button {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .resource-annotations__button,
  .resource-annotations__remove {
    transition: none;
  }
}
</style>
