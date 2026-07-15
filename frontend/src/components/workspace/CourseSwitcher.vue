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
      <span class="course-switcher__icon" aria-hidden="true"><IconDoc :size="16" /></span>
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
          <span class="course-switcher__item-icon" aria-hidden="true"><IconDoc :size="16" /></span>
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

        <div class="course-switcher__divider" />

        <button
          type="button"
          data-course-menu-item="true"
          role="menuitem"
          class="course-switcher__item course-switcher__item--browse focus-ring"
          @click="browseCourses"
        >
          <span class="course-switcher__browse-mark" aria-hidden="true">+</span>
          <span>选择其他课程</span>
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
import IconDoc from "../icons/IconDoc.vue";

const props = defineProps({
  activeCourse: { type: Object, default: null },
  enrolledCourses: { type: Array, default: () => [] },
  menuId: { type: String, default: "workspace-course-menu" },
});

const emit = defineEmits(["switch-course", "browse-courses"]);

const menuOpen = ref(false);
const triggerRef = ref(null);
const menuRef = ref(null);

const hasCourseSurface = computed(() => Boolean(props.activeCourse) || props.enrolledCourses.length > 0);
const activeCourseTitle = computed(() => props.activeCourse?.title_cn || "课程");
watch(menuOpen, async (isOpen) => {
  if (!isOpen) return;
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
  closeMenu({ restoreFocus: true });
  emit("switch-course", courseId);
}

function browseCourses() {
  closeMenu({ restoreFocus: true });
  emit("browse-courses");
}

function formatProgress(progress) {
  const value = Number.isFinite(progress) ? progress : 0;
  return `${Math.round(value * 100)}%`;
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
