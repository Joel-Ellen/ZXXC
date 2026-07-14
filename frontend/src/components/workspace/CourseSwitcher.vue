<template>
  <div v-if="hasCourseSurface" class="course-switcher relative">
    <button
      ref="triggerRef"
      type="button"
      class="course-switcher__trigger focus-ring"
      :aria-controls="menuId"
      :aria-expanded="String(menuOpen)"
      aria-haspopup="menu"
      @click="toggleMenu"
      @keydown.down.prevent="openMenu('first')"
      @keydown.up.prevent="openMenu('last')"
    >
      <span class="course-switcher__icon" aria-hidden="true">{{ activeCourse?.icon || "📌" }}</span>
      <span class="course-switcher__title">{{ activeCourseTitle }}</span>
      <svg
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.6"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="course-switcher__chevron"
        :class="{ 'is-open': menuOpen }"
        aria-hidden="true"
      >
        <path d="m6 9 6 6 6-6" />
      </svg>
    </button>

    <transition name="course-menu-fade">
      <div
        v-if="menuOpen"
        :id="menuId"
        ref="menuRef"
        class="course-switcher__menu"
        role="menu"
        aria-label="已选课程"
        tabindex="-1"
        @click.stop
        @keydown="onMenuKeydown"
      >
        <p class="course-switcher__menu-label">已选课程</p>

        <button
          v-for="course in enrolledCourses"
          :key="course.course_id"
          type="button"
          data-course-menu-item="true"
          role="menuitemradio"
          :aria-checked="String(course.course_id === activeCourse?.course_id)"
          class="course-switcher__item focus-ring"
          :class="{ 'is-selected': course.course_id === activeCourse?.course_id }"
          @click="selectCourse(course.course_id)"
        >
          <span class="course-switcher__item-icon" aria-hidden="true">{{ course.icon || "📌" }}</span>
          <span class="course-switcher__item-copy">
            <span class="course-switcher__item-title">{{ course.title_cn || "课程" }}</span>
            <span class="course-switcher__item-meta">{{ formatProgress(course.progress) }}</span>
          </span>
          <IconCheck
            v-if="course.course_id === activeCourse?.course_id"
            :size="14"
            class="course-switcher__check"
            aria-hidden="true"
          />
        </button>

        <div
          v-if="pendingCourse"
          class="course-switcher__confirmation"
          role="group"
          aria-label="确认切换课程"
        >
          <p>切换到「{{ pendingCourse.title_cn || "该课程" }}」？</p>
          <span>当前课程的学习位置会保留。</span>
          <div class="course-switcher__confirmation-actions">
            <button
              ref="confirmRef"
              type="button"
              class="course-switcher__confirm focus-ring"
              @click="confirmCourseSwitch"
            >
              确认
            </button>
            <button
              type="button"
              class="course-switcher__cancel focus-ring"
              @click="cancelCourseSwitch"
            >
              取消
            </button>
          </div>
        </div>

        <div class="course-switcher__divider" />

        <button
          type="button"
          data-course-menu-item="true"
          role="menuitem"
          class="course-switcher__item course-switcher__item--browse focus-ring"
          @click="browseCourses"
        >
          <span class="course-switcher__browse-mark" aria-hidden="true">+</span>
          <span>浏览更多课程</span>
        </button>
      </div>
    </transition>

    <div
      v-if="menuOpen"
      class="course-switcher__scrim"
      aria-hidden="true"
      @click="closeMenu({ restoreFocus: true })"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import IconCheck from "../icons/IconCheck.vue";

const props = defineProps({
  activeCourse: { type: Object, default: null },
  enrolledCourses: { type: Array, default: () => [] },
  menuId: { type: String, default: "workspace-course-menu" },
});

const emit = defineEmits(["switch-course", "browse-courses"]);

const menuOpen = ref(false);
const triggerRef = ref(null);
const menuRef = ref(null);
const confirmRef = ref(null);
const pendingCourseId = ref("");

const hasCourseSurface = computed(() => Boolean(props.activeCourse) || props.enrolledCourses.length > 0);
const activeCourseTitle = computed(() => props.activeCourse?.title_cn || "课程");
const pendingCourse = computed(() => props.enrolledCourses.find((course) => (
  course.course_id === pendingCourseId.value
)) || null);
watch(menuOpen, async (isOpen) => {
  if (!isOpen) {
    pendingCourseId.value = "";
    return;
  }
  await nextTick();
  focusMenuItem("selected");
});

onBeforeUnmount(() => {
  menuOpen.value = false;
});

async function openMenu(target = "selected") {
  menuOpen.value = true;
  await nextTick();
  focusMenuItem(target);
}

function toggleMenu() {
  if (menuOpen.value) {
    closeMenu({ restoreFocus: true });
    return;
  }

  openMenu();
}

function closeMenu({ restoreFocus = false } = {}) {
  if (!menuOpen.value && !restoreFocus) return;

  menuOpen.value = false;
  if (!restoreFocus) return;

  nextTick(() => {
    if (triggerRef.value instanceof HTMLElement) {
      triggerRef.value.focus({ preventScroll: true });
    }
  });
}

function menuItems() {
  if (!(menuRef.value instanceof HTMLElement)) return [];

  return Array.from(menuRef.value.querySelectorAll('[data-course-menu-item="true"]')).filter((element) => (
    element instanceof HTMLElement
  ));
}

function focusMenuItem(target = "selected") {
  const items = menuItems();
  if (!items.length) return;

  let index = 0;
  if (target === "last") {
    index = items.length - 1;
  } else if (target === "selected") {
    const selectedIndex = items.findIndex((item) => item.getAttribute("aria-checked") === "true");
    index = selectedIndex >= 0 ? selectedIndex : 0;
  }

  items[index]?.focus();
}

function moveFocus(step) {
  const items = menuItems();
  if (!items.length) return;

  const currentIndex = items.findIndex((item) => item === document.activeElement);
  const safeIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = (safeIndex + step + items.length) % items.length;
  items[nextIndex]?.focus();
}

function onMenuKeydown(event) {
  if (!menuOpen.value) return;

  if (event.key === "ArrowDown") {
    event.preventDefault();
    moveFocus(1);
    return;
  }

  if (event.key === "ArrowUp") {
    event.preventDefault();
    moveFocus(-1);
    return;
  }

  if (event.key === "Home") {
    event.preventDefault();
    focusMenuItem("first");
    return;
  }

  if (event.key === "End") {
    event.preventDefault();
    focusMenuItem("last");
    return;
  }

  if (event.key === "Escape") {
    event.preventDefault();
    closeMenu({ restoreFocus: true });
    return;
  }

  if (event.key === "Tab") {
    window.setTimeout(() => closeMenu(), 0);
  }
}

function selectCourse(courseId) {
  if (courseId === props.activeCourse?.course_id) {
    closeMenu({ restoreFocus: true });
    return;
  }
  pendingCourseId.value = courseId;
  nextTick(() => confirmRef.value?.focus());
}

function confirmCourseSwitch() {
  const courseId = pendingCourseId.value;
  if (!courseId) return;
  pendingCourseId.value = "";
  closeMenu({ restoreFocus: true });
  emit("switch-course", courseId);
}

function cancelCourseSwitch() {
  pendingCourseId.value = "";
  nextTick(() => focusMenuItem("selected"));
}

function browseCourses() {
  closeMenu({ restoreFocus: true });
  emit("browse-courses");
}

function formatProgress(progress) {
  const numeric = Number(progress);
  const value = Number.isFinite(numeric) ? numeric : 0;
  const ratio = value > 1 && value <= 100 ? value / 100 : value;
  return `${Math.round(Math.min(1, Math.max(0, ratio)) * 100)}%`;
}
</script>

<style scoped>
.course-switcher {
  min-width: 0;
}

.course-switcher__trigger {
  display: inline-grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  min-height: 2.75rem;
  width: min(18rem, 100%);
  gap: 0.55rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--space-elevated);
  color: var(--text-secondary);
  padding: 0.45rem 0.7rem;
  text-align: left;
  transition:
    border-color var(--duration-base) var(--ease-standard),
    background var(--duration-base) var(--ease-standard),
    color var(--duration-base) var(--ease-standard);
}

.course-switcher__trigger:hover {
  border-color: color-mix(in srgb, var(--color-primary) 24%, var(--border-strong));
  background: var(--card-bg-hover);
  color: var(--text-primary);
}

.course-switcher__icon,
.course-switcher__item-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.course-switcher__icon {
  width: 1.5rem;
  font-size: 1rem;
}

.course-switcher__title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
  font-weight: 700;
}

.course-switcher__chevron {
  color: var(--text-muted);
  transition: transform var(--duration-base) var(--ease-standard);
}

.course-switcher__chevron.is-open {
  transform: rotate(180deg);
}

.course-switcher__menu {
  position: absolute;
  left: 0;
  top: calc(100% + 0.5rem);
  z-index: var(--z-modal);
  width: min(20rem, calc(100vw - 2rem));
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--space-panel);
  box-shadow: var(--workspace-shadow-focus);
  padding: 0.45rem;
}

.course-switcher__menu-label {
  padding: 0.45rem 0.65rem 0.35rem;
  color: var(--text-muted);
  font-size: 0.7rem;
  font-weight: 800;
}

.course-switcher__item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  width: 100%;
  min-height: 44px;
  gap: 0.7rem;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  padding: 0.65rem;
  text-align: left;
  transition:
    background var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard);
}

.course-switcher__item:hover,
.course-switcher__item:focus-visible {
  background: var(--card-bg-hover);
  color: var(--text-primary);
}

.course-switcher__item.is-selected {
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
}

.course-switcher__item-copy {
  min-width: 0;
}

.course-switcher__item-title,
.course-switcher__item-meta {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.course-switcher__item-title {
  font-size: var(--font-size-sm);
  font-weight: 700;
}

.course-switcher__item-meta {
  margin-top: 0.12rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.68rem;
}

.course-switcher__check {
  color: var(--color-primary-dark);
}

.course-switcher__divider {
  height: 1px;
  margin: 0.3rem 0.45rem;
  background: var(--border-subtle);
}

.course-switcher__confirmation {
  margin: 0.35rem 0.2rem;
  border: 1px solid color-mix(in srgb, var(--color-primary) 24%, var(--border-subtle));
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
  padding: 0.7rem;
}

.course-switcher__confirmation p {
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: 700;
}

.course-switcher__confirmation > span {
  display: block;
  margin-top: 0.2rem;
  color: var(--text-secondary);
  font-size: 0.72rem;
}

.course-switcher__confirmation-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin-top: 0.65rem;
}

.course-switcher__confirm,
.course-switcher__cancel {
  min-height: 44px;
  border-radius: var(--radius-pill);
  padding: 0.45rem 0.85rem;
  font-size: var(--font-size-sm);
  font-weight: 700;
}

.course-switcher__confirm {
  border: 1px solid var(--color-primary);
  background: var(--color-primary);
  color: var(--color-primary-text);
}

.course-switcher__cancel {
  border: 1px solid var(--border-subtle);
  background: var(--space-panel);
  color: var(--text-secondary);
}

.course-switcher__item--browse {
  grid-template-columns: auto minmax(0, 1fr);
  color: var(--text-muted);
}

.course-switcher__browse-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: var(--radius-pill);
  background: var(--color-secondary-soft);
  color: var(--color-secondary-dark);
  font-weight: 900;
}

.course-switcher__scrim {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal-backdrop);
}

.course-menu-fade-enter-active,
.course-menu-fade-leave-active {
  transition:
    opacity var(--duration-fast) var(--ease-standard),
    transform var(--duration-fast) var(--ease-standard);
}

.course-menu-fade-enter-from,
.course-menu-fade-leave-to {
  opacity: 0;
  transform: translateY(-0.25rem);
}
</style>
