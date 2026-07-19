<template>
  <Teleport to="body">
    <Transition name="ppt-preview">
      <div
        v-if="open && model"
        class="ppt-preview-overlay"
        @click.self="emit('close')"
      >
        <section
          ref="dialog"
          class="ppt-preview-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ppt-preview-title"
          tabindex="-1"
          @keydown="handleKeydown"
        >
          <header class="ppt-preview-header">
            <div class="min-w-0">
              <p class="ppt-preview-eyebrow">节点课件预览</p>
              <div class="ppt-preview-title-row">
                <h2 id="ppt-preview-title">{{ model.title }}</h2>
                <span class="ppt-preview-page-count">{{ currentIndex + 1 }} / {{ slides.length }}</span>
              </div>
            </div>

            <div class="ppt-preview-actions">
              <button
                type="button"
                class="workspace-shell-btn workspace-shell-btn--accent focus-ring inline-flex min-h-11 items-center gap-2 px-3 py-2 text-xs font-semibold"
                :disabled="downloading"
                title="下载当前节点学习 PPT"
                @click="emit('download')"
              >
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 3v11" />
                  <path d="m7 10 5 5 5-5" />
                  <path d="M5 20h14" />
                </svg>
                <span>{{ downloading ? "正在生成..." : "下载 PPT" }}</span>
              </button>
              <button
                type="button"
                class="ppt-preview-icon-btn focus-ring"
                aria-label="关闭课件预览"
                title="关闭课件预览"
                @click="emit('close')"
              >
                <svg aria-hidden="true" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
                  <path d="m6 6 12 12" />
                  <path d="m18 6-12 12" />
                </svg>
              </button>
            </div>
          </header>

          <div class="ppt-preview-toolbar">
            <span>学习课件</span>
            <p v-if="status" class="ppt-preview-status" role="status" aria-live="polite">{{ status }}</p>
          </div>

          <div class="ppt-preview-body">
            <nav class="ppt-preview-thumbnails" aria-label="课件页码">
              <p class="ppt-preview-section-label">页面</p>
              <div class="ppt-preview-thumbnail-list">
                <button
                  v-for="(slide, index) in slides"
                  :key="`${slide.kind}-${index}`"
                  type="button"
                  class="ppt-preview-thumbnail focus-ring"
                  :class="{ 'ppt-preview-thumbnail--active': index === currentIndex }"
                  :aria-current="index === currentIndex ? 'page' : undefined"
                  :aria-label="`第 ${index + 1} 页：${slide.title || '节点课件'}`"
                  @click="selectSlide(index)"
                >
                  <span class="ppt-preview-thumbnail-number">{{ String(index + 1).padStart(2, "0") }}</span>
                  <span class="ppt-preview-thumbnail-title">{{ slide.title || "节点课件" }}</span>
                </button>
              </div>
            </nav>

            <main class="ppt-preview-stage" aria-live="polite">
              <button
                type="button"
                class="ppt-preview-nav-btn focus-ring"
                aria-label="上一页"
                title="上一页"
                :disabled="currentIndex === 0"
                @click="previousSlide"
              >
                <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="m15 18-6-6 6-6" />
                </svg>
              </button>

              <div class="ppt-preview-slide-viewport">
                <article v-if="currentSlide" class="ppt-preview-slide" :class="{ 'ppt-preview-slide--cover': currentSlide.kind === 'cover' }">
                  <template v-if="currentSlide.kind === 'cover'">
                    <div class="ppt-preview-cover-mark">EDUAGENT / NODE STUDY</div>
                    <div class="ppt-preview-cover-rule" />
                    <h3>{{ currentSlide.title }}</h3>
                    <p class="ppt-preview-cover-subtitle">{{ currentSlide.subtitle }}</p>
                    <p class="ppt-preview-cover-detail">{{ currentSlide.detail }}</p>
                  </template>

                  <template v-else-if="currentSlide.kind === 'agenda'">
                    <span class="ppt-preview-slide-kicker">节点学习</span>
                    <h3>{{ currentSlide.title }}</h3>
                    <ol class="ppt-preview-agenda-list">
                      <li v-for="(item, index) in currentSlide.items || []" :key="`agenda-${index}`">{{ item }}</li>
                    </ol>
                  </template>

                  <template v-else-if="currentSlide.kind === 'columns'">
                    <span class="ppt-preview-slide-kicker">{{ currentSlide.kicker || "学习要点" }}</span>
                    <h3>{{ currentSlide.title }}</h3>
                    <div class="ppt-preview-columns">
                      <section v-for="(column, columnIndex) in currentSlide.columns || []" :key="`column-${columnIndex}`" class="ppt-preview-column">
                        <h4>{{ column.heading }}</h4>
                        <ul>
                          <li v-for="(item, itemIndex) in column.items || []" :key="`column-${columnIndex}-item-${itemIndex}`">{{ item }}</li>
                        </ul>
                      </section>
                    </div>
                  </template>

                  <template v-else-if="currentSlide.kind === 'code'">
                    <span class="ppt-preview-slide-kicker">{{ currentSlide.kicker || "可运行片段" }}</span>
                    <h3>{{ currentSlide.title }}</h3>
                    <p class="ppt-preview-code-language">{{ codeLanguageLabel(currentSlide.language) }}</p>
                    <pre class="ppt-preview-code"><code>{{ currentSlide.code }}</code></pre>
                  </template>

                  <template v-else-if="currentSlide.kind === 'summary'">
                    <span class="ppt-preview-slide-kicker">节点学习</span>
                    <h3>{{ currentSlide.title }}</h3>
                    <ol class="ppt-preview-summary-list">
                      <li v-for="(item, index) in currentSlide.bullets || []" :key="`summary-${index}`">
                        <span>{{ String(index + 1).padStart(2, "0") }}</span>
                        <strong>{{ item }}</strong>
                      </li>
                    </ol>
                    <p class="ppt-preview-slide-note">{{ currentSlide.detail }}</p>
                  </template>

                  <template v-else>
                    <span class="ppt-preview-slide-kicker">{{ currentSlide.kicker || "学习资料" }}</span>
                    <h3>{{ currentSlide.title }}</h3>
                    <p class="ppt-preview-slide-lead">{{ currentSlide.lead }}</p>
                    <ul v-if="currentSlide.bullets?.length" class="ppt-preview-bullets">
                      <li v-for="(item, index) in currentSlide.bullets" :key="`bullet-${index}`">{{ item }}</li>
                    </ul>
                    <p v-if="currentSlide.note" class="ppt-preview-slide-note">{{ currentSlide.note }}</p>
                  </template>
                </article>
              </div>

              <button
                type="button"
                class="ppt-preview-nav-btn focus-ring"
                aria-label="下一页"
                title="下一页"
                :disabled="currentIndex >= slides.length - 1"
                @click="nextSlide"
              >
                <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="m9 18 6-6-6-6" />
                </svg>
              </button>
            </main>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { CODE_LANGUAGE_LABEL, normalizeCodeLanguage } from "../utils/codeExample.js";

const props = defineProps({
  open: { type: Boolean, default: false },
  model: { type: Object, default: null },
  downloading: { type: Boolean, default: false },
  status: { type: String, default: "" },
});

const emit = defineEmits(["close", "download"]);
const dialog = ref(null);
const currentIndex = ref(0);
let previousBodyOverflow = "";

const slides = computed(() => (Array.isArray(props.model?.slides) ? props.model.slides : []));
const currentSlide = computed(() => slides.value[currentIndex.value] || slides.value[0] || null);

watch(
  () => props.open,
  (open) => {
    if (!open) {
      if (typeof document !== "undefined") document.body.style.overflow = previousBodyOverflow;
      return;
    }
    if (typeof document !== "undefined") {
      previousBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    currentIndex.value = 0;
    nextTick(() => dialog.value?.focus());
  },
);

onBeforeUnmount(() => {
  if (typeof document !== "undefined") document.body.style.overflow = previousBodyOverflow;
});

watch(
  () => slides.value.length,
  (length) => {
    if (currentIndex.value >= length) currentIndex.value = Math.max(0, length - 1);
  },
);

function selectSlide(index) {
  currentIndex.value = Math.max(0, Math.min(index, slides.value.length - 1));
}

function previousSlide() {
  selectSlide(currentIndex.value - 1);
}

function nextSlide() {
  selectSlide(currentIndex.value + 1);
}

function codeLanguageLabel(value) {
  return normalizeCodeLanguage(value).toUpperCase() || CODE_LANGUAGE_LABEL;
}

function handleKeydown(event) {
  if (event.key === "Tab") {
    trapFocus(event);
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    emit("close");
    return;
  }
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    previousSlide();
    return;
  }
  if (event.key === "ArrowRight") {
    event.preventDefault();
    nextSlide();
  }
}

function trapFocus(event) {
  if (!dialog.value) return;
  const focusableElements = Array.from(dialog.value.querySelectorAll(
    "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
  )).filter((element) => element instanceof HTMLElement);
  if (!focusableElements.length) return;

  const first = focusableElements[0];
  const last = focusableElements[focusableElements.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
</script>

<style scoped>
.ppt-preview-overlay {
  position: fixed;
  z-index: var(--z-modal-backdrop);
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: rgba(15, 23, 42, 0.42);
  backdrop-filter: blur(3px);
}

.ppt-preview-dialog {
  position: relative;
  z-index: var(--z-modal);
  display: flex;
  width: min(1200px, 96vw);
  max-height: min(900px, 94dvh);
  flex-direction: column;
  overflow: hidden;
  border-radius: var(--radius-lg);
  background: var(--space-surface);
  color: var(--text-primary);
  box-shadow: var(--shadow-lg);
}

.ppt-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid var(--border-subtle);
  padding: 1rem 1.25rem;
}

.ppt-preview-eyebrow,
.ppt-preview-section-label {
  color: var(--text-muted);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  line-height: 1.2;
}

.ppt-preview-title-row {
  display: flex;
  align-items: baseline;
  gap: 0.65rem;
  margin-top: 0.35rem;
}

.ppt-preview-title-row h2 {
  overflow: hidden;
  font-size: 1.15rem;
  font-weight: 800;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ppt-preview-page-count {
  flex-shrink: 0;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.72rem;
}

.ppt-preview-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 0.5rem;
}

.ppt-preview-icon-btn,
.ppt-preview-nav-btn {
  display: inline-flex;
  min-height: 2.75rem;
  min-width: 2.75rem;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  transition: background-color var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard);
}

.ppt-preview-icon-btn:hover,
.ppt-preview-nav-btn:hover:not(:disabled) {
  border-color: var(--border-hover);
  background: var(--color-primary-soft);
  color: var(--text-primary);
}

.ppt-preview-icon-btn:disabled,
.ppt-preview-nav-btn:disabled {
  cursor: not-allowed;
  opacity: 0.38;
}

.ppt-preview-toolbar {
  display: flex;
  min-height: 2.5rem;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid var(--border-subtle);
  padding: 0.55rem 1.25rem;
  color: var(--text-secondary);
  font-size: 0.72rem;
  font-weight: 700;
}

.ppt-preview-status {
  overflow: hidden;
  color: var(--color-primary-dark);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ppt-preview-body {
  display: flex;
  min-height: 0;
  flex: 1;
}

.ppt-preview-thumbnails {
  display: flex;
  width: 220px;
  flex-shrink: 0;
  flex-direction: column;
  gap: 0.7rem;
  overflow-y: auto;
  border-right: 1px solid var(--border-subtle);
  background: var(--space-elevated);
  padding: 1rem 0.8rem;
}

.ppt-preview-thumbnail-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  overflow-y: auto;
}

.ppt-preview-thumbnail {
  display: flex;
  min-height: 2.75rem;
  align-items: center;
  gap: 0.65rem;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  padding: 0.45rem 0.5rem;
  text-align: left;
  color: var(--text-secondary);
  transition: background-color var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);
}

.ppt-preview-thumbnail:hover {
  background: var(--space-surface);
  color: var(--text-primary);
}

.ppt-preview-thumbnail--active {
  border-color: var(--border-hover);
  background: var(--space-surface);
  color: var(--text-primary);
}

.ppt-preview-thumbnail-number {
  flex-shrink: 0;
  width: 1.6rem;
  color: var(--color-primary);
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 800;
}

.ppt-preview-thumbnail-title {
  min-width: 0;
  overflow: hidden;
  font-size: 0.72rem;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ppt-preview-stage {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex: 1;
  align-items: center;
  gap: 0.5rem;
  background: var(--space-bg);
  padding: 1rem;
}

.ppt-preview-slide-viewport {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex: 1;
  align-items: center;
  justify-content: center;
  overflow: auto;
}

.ppt-preview-slide {
  display: flex;
  width: min(100%, 920px);
  aspect-ratio: 16 / 9;
  flex-shrink: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: #faf7ef;
  padding: 7%;
  color: #17352d;
}

.ppt-preview-slide--cover {
  border-color: #17352d;
  background: #17352d;
  color: #ffffff;
}

.ppt-preview-cover-mark,
.ppt-preview-slide-kicker,
.ppt-preview-code-language {
  color: #2e8c8a;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  line-height: 1.2;
  text-transform: uppercase;
}

.ppt-preview-cover-mark {
  color: #b8d6a7;
}

.ppt-preview-cover-rule {
  width: 4.5rem;
  height: 0.28rem;
  margin-top: 3.5%;
  background: #c8a858;
}

.ppt-preview-slide h3 {
  margin-top: 1.2rem;
  overflow-wrap: anywhere;
  font-size: 2rem;
  font-weight: 850;
  line-height: 1.2;
  text-wrap: balance;
}

.ppt-preview-slide--cover h3 {
  margin-top: 12%;
  color: #ffffff;
  font-size: 2.25rem;
}

.ppt-preview-cover-subtitle {
  margin-top: 11%;
  color: #d7e9e0;
  font-size: 1.15rem;
  font-weight: 700;
}

.ppt-preview-cover-detail {
  margin-top: 3%;
  color: #a8c7b9;
  font-size: 0.8rem;
}

.ppt-preview-slide-lead {
  max-width: 65ch;
  margin-top: 1.25rem;
  color: #17352d;
  font-size: 1.08rem;
  font-weight: 750;
  line-height: 1.45;
  text-wrap: pretty;
}

.ppt-preview-bullets,
.ppt-preview-agenda-list,
.ppt-preview-column ul {
  display: grid;
  gap: 0.55rem;
  margin-top: 1.1rem;
  padding-left: 1.2rem;
  color: #4f6b61;
  font-size: 0.9rem;
  line-height: 1.45;
}

.ppt-preview-agenda-list {
  gap: 0.7rem;
  padding-left: 1.65rem;
  color: #17352d;
  font-size: 1.08rem;
  font-weight: 700;
}

.ppt-preview-slide-note {
  margin-top: auto;
  padding-top: 1rem;
  color: #1e5e4d;
  font-size: 0.74rem;
  font-style: italic;
  line-height: 1.4;
}

.ppt-preview-columns {
  display: grid;
  min-height: 0;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  margin-top: 1rem;
}

.ppt-preview-column {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #cfe0d7;
  border-radius: var(--radius-sm);
  background: #fffef9;
  padding: 0.85rem;
}

.ppt-preview-column h4 {
  overflow-wrap: anywhere;
  color: #17352d;
  font-size: 0.9rem;
  font-weight: 800;
  line-height: 1.3;
}

.ppt-preview-column ul {
  margin-top: 0.75rem;
  font-size: 0.76rem;
}

.ppt-preview-code-language {
  margin-top: 0.9rem;
}

.ppt-preview-code {
  min-height: 0;
  flex: 1;
  overflow: auto;
  margin-top: 0.8rem;
  border-radius: var(--radius-sm);
  background: #10231f;
  padding: 1rem;
  color: #e7f4ee;
  font-family: var(--font-mono);
  font-size: 0.76rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.ppt-preview-summary-list {
  display: grid;
  gap: 0.8rem;
  margin-top: 1.2rem;
}

.ppt-preview-summary-list li {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  border-bottom: 1px solid #cfe0d7;
  padding-bottom: 0.75rem;
}

.ppt-preview-summary-list li > span {
  flex-shrink: 0;
  color: #2e8c8a;
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 800;
}

.ppt-preview-summary-list strong {
  overflow-wrap: anywhere;
  font-size: 1rem;
  line-height: 1.35;
}

.ppt-preview-nav-btn {
  flex-shrink: 0;
  background: var(--space-surface);
}

.ppt-preview-enter-active,
.ppt-preview-leave-active {
  transition: opacity var(--duration-base) var(--ease-standard);
}

.ppt-preview-enter-from,
.ppt-preview-leave-to {
  opacity: 0;
}

@media (max-width: 760px) {
  .ppt-preview-overlay {
    align-items: stretch;
    padding: 0;
  }

  .ppt-preview-dialog {
    width: 100%;
    max-height: 100dvh;
    border-radius: 0;
  }

  .ppt-preview-header {
    padding: 0.85rem 1rem;
  }

  .ppt-preview-toolbar {
    padding-inline: 1rem;
  }

  .ppt-preview-body {
    flex-direction: column;
  }

  .ppt-preview-thumbnails {
    width: auto;
    max-height: 7.2rem;
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
    padding: 0.65rem 0.8rem;
  }

  .ppt-preview-thumbnail-list {
    flex-direction: row;
    overflow-x: auto;
    overflow-y: hidden;
  }

  .ppt-preview-thumbnail {
    width: 10rem;
    flex-shrink: 0;
  }

  .ppt-preview-stage {
    position: relative;
    padding: 0.65rem 2.5rem;
  }

  .ppt-preview-slide {
    width: 100%;
    padding: 7%;
  }

  .ppt-preview-slide-viewport {
    width: 100%;
    padding-inline: 0;
  }

  .ppt-preview-stage > .ppt-preview-nav-btn {
    position: absolute;
    top: 50%;
    z-index: 2;
    transform: translateY(-50%);
  }

  .ppt-preview-stage > .ppt-preview-nav-btn:first-child {
    left: 0.4rem;
  }

  .ppt-preview-stage > .ppt-preview-nav-btn:last-child {
    right: 0.4rem;
  }

  .ppt-preview-slide h3,
  .ppt-preview-slide--cover h3 {
    font-size: 1.2rem;
  }

  .ppt-preview-cover-subtitle,
  .ppt-preview-agenda-list {
    font-size: 0.78rem;
  }

  .ppt-preview-slide-lead {
    margin-top: 0.75rem;
    font-size: 0.72rem;
  }

  .ppt-preview-bullets,
  .ppt-preview-column ul {
    gap: 0.25rem;
    margin-top: 0.65rem;
    font-size: 0.62rem;
  }

  .ppt-preview-columns {
    gap: 0.4rem;
    margin-top: 0.65rem;
  }

  .ppt-preview-column {
    padding: 0.55rem;
  }

  .ppt-preview-column h4 {
    font-size: 0.68rem;
  }

  .ppt-preview-column ul {
    padding-left: 0.85rem;
  }

  .ppt-preview-code {
    margin-top: 0.5rem;
    padding: 0.65rem;
    font-size: 0.58rem;
  }

  .ppt-preview-summary-list {
    gap: 0.4rem;
    margin-top: 0.7rem;
  }

  .ppt-preview-summary-list li {
    gap: 0.4rem;
    padding-bottom: 0.4rem;
  }

  .ppt-preview-summary-list li > span,
  .ppt-preview-summary-list strong {
    font-size: 0.68rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ppt-preview-enter-active,
  .ppt-preview-leave-active,
  .ppt-preview-icon-btn,
  .ppt-preview-nav-btn,
  .ppt-preview-thumbnail {
    transition: none;
  }
}
</style>
