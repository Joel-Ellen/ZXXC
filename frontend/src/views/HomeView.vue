<template>
  <AppPageFrame>
    <section class="px-4 py-6 sm:px-6 lg:px-8">
      <div class="mx-auto w-full max-w-7xl">
        <CourseManagementView
          :courses="managedCourses"
          :active-course="lifecycle.activeCourse"
          :recent-learning="lifecycle.recentLearning"
          :loading="lifecycle.loading.enrollment"
          :summary-loading="lifecycle.loading.summary"
          :busy="lifecycle.isActing"
          :error="lifecycle.errors.enrollment"
          :summary-error="lifecycle.errors.summary"
          :action-error="lifecycle.errors.action"
          :action-course-id="lifecycle.action.courseId"
          :action-type="lifecycle.action.type"
          @open-catalog="router.push({ name: 'courses' })"
          @continue-course="continueCourse"
          @activate-course="activateAndContinue"
          @view-course="viewCourse"
          @leave-course="leaveCourse"
          @open-recent="openRecent"
          @retry="reloadDashboard"
          @retry-summary="lifecycle.loadSummary({ force: true })"
          @dismiss-error="lifecycle.clearActionError"
        />
      </div>
    </section>
  </AppPageFrame>
</template>

<script setup>
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import AppPageFrame from "../components/AppPageFrame.vue";
import CourseManagementView from "../components/CourseManagementView.vue";
import { reportNextTaskReady } from "../services/clientTelemetry";
import { useCourseLifecycleStore } from "../stores/courseLifecycle";

const router = useRouter();
const lifecycle = useCourseLifecycleStore();

const managedCourses = computed(() => [...lifecycle.enrolledCourses].sort((left, right) => {
  if (left.course_id === lifecycle.activeCourse?.course_id) return -1;
  if (right.course_id === lifecycle.activeCourse?.course_id) return 1;
  return String(right.last_activity_at || right.enrolled_at || "")
    .localeCompare(String(left.last_activity_at || left.enrolled_at || ""));
}));

onMounted(async () => {
  await lifecycle.loadDashboard({ force: true });
  if (!lifecycle.errors.enrollment && !lifecycle.enrolledCourses.length) {
    await router.replace({ name: "courses" });
    return;
  }
  if (!lifecycle.errors.enrollment && lifecycle.enrolledCourses.length) {
    void reportNextTaskReady({ surface: "app" });
  }
});

function courseById(courseId) {
  return lifecycle.enrolledCourses.find((course) => course.course_id === courseId) || null;
}

function nodeForCourse(course, requestedNode = "") {
  if (requestedNode) return requestedNode;
  if (lifecycle.continueLearning?.course_id === course?.course_id) {
    return lifecycle.continueLearning.node_id;
  }
  return course?.last_node_id || "setup";
}

function goToLearning(courseId, nodeId = "") {
  const course = courseById(courseId);
  if (!course) return;
  router.push({
    name: "learn",
    params: { courseId, nodeId: nodeForCourse(course, nodeId) },
  });
}

function continueCourse(courseId) {
  if (courseId !== lifecycle.activeCourse?.course_id) return;
  goToLearning(courseId);
}

async function activateAndContinue(courseId, nodeId = "") {
  const succeeded = await lifecycle.activateCourse(courseId);
  if (succeeded) goToLearning(courseId, nodeId);
}

function viewCourse(courseId) {
  router.push({ name: "course-detail", params: { courseId } });
}

async function leaveCourse(courseId) {
  const succeeded = await lifecycle.leaveCourse(courseId);
  if (succeeded && !lifecycle.enrolledCourses.length) {
    await router.replace({ name: "courses" });
  }
}

function openRecent(item) {
  if (item.course_id !== lifecycle.activeCourse?.course_id) return;
  goToLearning(item.course_id, item.node_id);
}

function reloadDashboard() {
  lifecycle.loadDashboard({ force: true });
}
</script>
