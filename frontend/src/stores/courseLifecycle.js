import { computed, reactive, ref } from "vue";
import { defineStore } from "pinia";
import {
  courseLifecycleErrorMessage,
  enrollInCourse,
  fetchCourseCatalog,
  fetchEnrollmentState,
  fetchLearningSummary,
  leaveCourse as requestLeaveCourse,
  normalizeCourse,
  switchActiveCourse,
} from "../services/courseLifecycleApi";

const EMPTY_ENROLLMENT = Object.freeze({ active_course: "", courses: [] });
const EMPTY_SUMMARY = Object.freeze({ courses: [], recent_learning: [], continue_learning: null });

function mergeDefined(...records) {
  return Object.assign({}, ...records.filter((record) => record && typeof record === "object"));
}

export const useCourseLifecycleStore = defineStore("courseLifecycle", () => {
  const catalog = ref([]);
  const enrollment = ref({ ...EMPTY_ENROLLMENT });
  const learningSummary = ref({ ...EMPTY_SUMMARY });
  const loading = reactive({ catalog: false, enrollment: false, summary: false });
  const errors = reactive({ catalog: "", enrollment: "", summary: "", action: "" });
  const action = reactive({ type: "", courseId: "" });

  const summaryByCourse = computed(() => new Map(
    learningSummary.value.courses.map((course) => [course.course_id, course]),
  ));
  const catalogByCourse = computed(() => new Map(
    catalog.value.map((course) => [course.course_id, course]),
  ));

  const enrolledCourses = computed(() => enrollment.value.courses.map((course) => {
    const summary = summaryByCourse.value.get(course.course_id);
    const catalogCourse = catalogByCourse.value.get(course.course_id);
    const nodeCount = catalogCourse?.node_count || course.node_count || summary?.total_nodes || 0;
    const totalNodes = summary?.total_nodes || nodeCount;
    return {
      ...mergeDefined(catalogCourse, course, summary),
      node_count: nodeCount,
      total_nodes: totalNodes,
    };
  }));

  const enrolledByCourse = computed(() => new Map(
    enrolledCourses.value.map((course) => [course.course_id, course]),
  ));

  const catalogCourses = computed(() => catalog.value.map((course) => {
    const enrollmentCourse = enrolledByCourse.value.get(course.course_id);
    return {
      ...mergeDefined(course, enrollmentCourse),
      enrolled: Boolean(enrollmentCourse),
    };
  }));

  const activeCourse = computed(() => (
    enrolledByCourse.value.get(enrollment.value.active_course) || null
  ));

  const recentLearning = computed(() => learningSummary.value.recent_learning
    .filter((item) => enrolledByCourse.value.has(item.course_id))
    .map((item) => ({
      ...item,
      course_title: item.course_title
        || enrolledByCourse.value.get(item.course_id)?.title_cn
        || catalogByCourse.value.get(item.course_id)?.title_cn
        || item.course_id,
    }))
    .sort((left, right) => String(right.occurred_at).localeCompare(String(left.occurred_at))));

  const continueLearning = computed(() => {
    const declared = learningSummary.value.continue_learning;
    if (declared && enrolledByCourse.value.has(declared.course_id)) return declared;
    const current = activeCourse.value;
    if (!current?.course_id || !current.last_node_id) return null;
    return {
      course_id: current.course_id,
      node_id: current.last_node_id,
      occurred_at: current.last_activity_at || "",
    };
  });

  const isActing = computed(() => Boolean(action.type));

  async function loadCatalog({ force = false } = {}) {
    if (loading.catalog || (catalog.value.length && !force)) return catalog.value;
    loading.catalog = true;
    errors.catalog = "";
    try {
      catalog.value = await fetchCourseCatalog();
      return catalog.value;
    } catch (error) {
      errors.catalog = courseLifecycleErrorMessage(error, "无法加载课程目录。");
      return catalog.value;
    } finally {
      loading.catalog = false;
    }
  }

  async function loadEnrollment({ force = false } = {}) {
    if (loading.enrollment || (enrollment.value.courses.length && !force)) return enrollment.value;
    loading.enrollment = true;
    errors.enrollment = "";
    try {
      enrollment.value = await fetchEnrollmentState();
      return enrollment.value;
    } catch (error) {
      errors.enrollment = courseLifecycleErrorMessage(error, "无法加载已选课程。");
      return enrollment.value;
    } finally {
      loading.enrollment = false;
    }
  }

  async function loadSummary({ force = false } = {}) {
    const hasSummary = learningSummary.value.courses.length || learningSummary.value.recent_learning.length;
    if (loading.summary || (hasSummary && !force)) return learningSummary.value;
    loading.summary = true;
    errors.summary = "";
    try {
      learningSummary.value = await fetchLearningSummary();
      return learningSummary.value;
    } catch (error) {
      errors.summary = courseLifecycleErrorMessage(error, "无法加载学习摘要。");
      return learningSummary.value;
    } finally {
      loading.summary = false;
    }
  }

  async function loadDashboard({ force = false } = {}) {
    await Promise.all([
      loadCatalog({ force }),
      loadEnrollment({ force }),
      loadSummary({ force }),
    ]);
  }

  async function runAction(type, courseId, request) {
    if (isActing.value) return false;
    action.type = type;
    action.courseId = courseId;
    errors.action = "";
    try {
      const response = await request(courseId);
      const currentCourses = enrollment.value.courses;
      if (type === "enroll") {
        const returnedCourse = response?.course
          ? normalizeCourse(response.course)
          : catalog.value.find((course) => course.course_id === courseId);
        if (returnedCourse) {
          const existing = currentCourses.find((course) => course.course_id === courseId);
          enrollment.value = {
            active_course: courseId,
            courses: existing
              ? currentCourses.map((course) => course.course_id === courseId
                ? { ...course, ...returnedCourse }
                : course)
              : [...currentCourses, { ...returnedCourse, progress: 0, completed_nodes: 0 }],
          };
        }
      } else if (type === "switch") {
        enrollment.value = { ...enrollment.value, active_course: courseId };
      } else if (type === "leave") {
        const remaining = currentCourses.filter((course) => course.course_id !== courseId);
        const responseActive = String(response?.active_course || "");
        const activeCourseId = responseActive && remaining.some((course) => course.course_id === responseActive)
          ? responseActive
          : enrollment.value.active_course === courseId
            ? ""
            : enrollment.value.active_course;
        enrollment.value = { active_course: activeCourseId, courses: remaining };
      }
      await Promise.all([
        loadEnrollment({ force: true }),
        loadSummary({ force: true }),
      ]);
      return true;
    } catch (error) {
      const fallback = type === "leave"
        ? "退出课程失败，请重试。"
        : type === "switch"
          ? "切换课程失败，请重试。"
          : "加入课程失败，请重试。";
      errors.action = courseLifecycleErrorMessage(error, fallback);
      return false;
    } finally {
      action.type = "";
      action.courseId = "";
    }
  }

  function enrollCourse(courseId) {
    return runAction("enroll", courseId, enrollInCourse);
  }

  function activateCourse(courseId) {
    if (courseId === enrollment.value.active_course) return Promise.resolve(true);
    return runAction("switch", courseId, switchActiveCourse);
  }

  function leaveCourse(courseId) {
    return runAction("leave", courseId, requestLeaveCourse);
  }

  function clearActionError() {
    errors.action = "";
  }

  return {
    catalog,
    enrollment,
    learningSummary,
    loading,
    errors,
    action,
    catalogCourses,
    enrolledCourses,
    activeCourse,
    recentLearning,
    continueLearning,
    isActing,
    loadCatalog,
    loadEnrollment,
    loadSummary,
    loadDashboard,
    enrollCourse,
    activateCourse,
    leaveCourse,
    clearActionError,
  };
});
