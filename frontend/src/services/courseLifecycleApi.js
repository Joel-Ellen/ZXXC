import apiClient from "./apiClient";

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function asString(value) {
  return value === undefined || value === null ? "" : String(value);
}

function asNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function normalizeCourseProgress(value) {
  const numeric = asNumber(value, 0);
  const ratio = numeric > 1 && numeric <= 100 ? numeric / 100 : numeric;
  return Math.min(1, Math.max(0, ratio));
}

export function normalizeCourseDifficulty(value) {
  const numeric = asNumber(value, 0);
  const ratio = numeric > 1 && numeric <= 100 ? numeric / 100 : numeric;
  return Math.min(1, Math.max(0, ratio));
}

export function normalizeCourse(record) {
  const source = asObject(record);
  const courseId = asString(source.course_id || source.id).trim();
  return {
    ...source,
    course_id: courseId,
    title: asString(source.title),
    title_cn: asString(source.title_cn || source.title || courseId),
    description: asString(source.description),
    description_cn: asString(source.description_cn || source.description),
    category: asString(source.category || "未分类"),
    difficulty: normalizeCourseDifficulty(source.difficulty),
    estimated_hours: Math.max(0, asNumber(source.estimated_hours, 0)),
    node_count: Math.max(0, Math.trunc(asNumber(source.node_count ?? source.total_nodes, 0))),
    tags: Array.isArray(source.tags) ? source.tags.map(asString).filter(Boolean) : [],
    prerequisites: Array.isArray(source.prerequisites)
      ? source.prerequisites.map(asString).filter(Boolean)
      : [],
    icon: asString(source.icon || "📘"),
    progress: normalizeCourseProgress(source.progress),
    completed_nodes: Math.max(0, Math.trunc(asNumber(source.completed_nodes, 0))),
    enrolled_at: asString(source.enrolled_at),
  };
}

export function normalizeCourseList(payload) {
  const source = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.courses)
      ? payload.courses
      : Array.isArray(payload?.items)
        ? payload.items
        : [];
  return source.map(normalizeCourse).filter((course) => course.course_id);
}

export function normalizeEnrollmentState(payload) {
  const source = asObject(payload);
  const courses = normalizeCourseList(source);
  const declaredActive = asString(source.active_course || source.active_course_id).trim();
  const inferredActive = courses.find((course) => course.is_active === true)?.course_id || "";
  const activeCourseId = declaredActive || inferredActive;
  return {
    active_course: courses.some((course) => course.course_id === activeCourseId) ? activeCourseId : "",
    courses,
  };
}

function normalizeCourseSummary(record) {
  const source = asObject(record);
  return {
    course_id: asString(source.course_id).trim(),
    progress: normalizeCourseProgress(source.progress),
    completed_nodes: Math.max(0, Math.trunc(asNumber(source.completed_nodes, 0))),
    total_nodes: Math.max(0, Math.trunc(asNumber(source.total_nodes ?? source.node_count, 0))),
    last_node_id: asString(source.last_node_id).trim(),
    last_node_title: asString(source.last_node_title),
    last_activity_at: asString(source.last_activity_at),
    last_event_type: asString(source.last_event_type),
  };
}

function normalizeRecentLearning(record) {
  const source = asObject(record);
  return {
    course_id: asString(source.course_id).trim(),
    course_title: asString(source.course_title),
    node_id: asString(source.node_id).trim(),
    node_title: asString(source.node_title),
    event_type: asString(source.event_type),
    occurred_at: asString(source.occurred_at),
    resource_id: asString(source.resource_id),
  };
}

function normalizeContinueLearning(record) {
  if (!record || typeof record !== "object" || Array.isArray(record)) return null;
  const courseId = asString(record.course_id).trim();
  const nodeId = asString(record.node_id).trim();
  if (!courseId || !nodeId) return null;
  return {
    course_id: courseId,
    node_id: nodeId,
    occurred_at: asString(record.occurred_at),
  };
}

export function normalizeLearningSummary(payload) {
  const source = asObject(payload);
  const courseSummaries = Array.isArray(source.courses)
    ? source.courses.map(normalizeCourseSummary).filter((course) => course.course_id)
    : [];
  const recentLearning = Array.isArray(source.recent_learning)
    ? source.recent_learning.map(normalizeRecentLearning).filter((item) => item.course_id && item.node_id)
    : [];

  return {
    courses: courseSummaries,
    recent_learning: recentLearning,
    continue_learning: normalizeContinueLearning(source.continue_learning),
  };
}

export function courseLifecycleErrorMessage(error, fallback = "请求失败，请稍后重试。") {
  const detail = error?.response?.data?.detail || error?.response?.data?.reason;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (typeof error?.message === "string" && error.message.trim()) return error.message;
  return fallback;
}

export async function fetchCourseCatalog({ search = "" } = {}) {
  const normalizedSearch = String(search || "").trim();
  const { data } = await apiClient.get("/courses", {
    params: normalizedSearch ? { search: normalizedSearch } : {},
  });
  return normalizeCourseList(data);
}

export async function fetchCourseById(courseId) {
  const { data } = await apiClient.get(`/courses/${encodeURIComponent(courseId)}`);
  return normalizeCourse(data);
}

export async function fetchEnrollmentState() {
  const { data } = await apiClient.get("/user/courses");
  return normalizeEnrollmentState(data);
}

export async function fetchLearningSummary() {
  const { data } = await apiClient.get("/user/learning-summary");
  return normalizeLearningSummary(data);
}

export async function enrollInCourse(courseId) {
  const { data } = await apiClient.post("/user/courses/enroll", { course_id: courseId });
  return data;
}

export async function switchActiveCourse(courseId) {
  const { data } = await apiClient.post("/user/courses/switch", { course_id: courseId });
  return data;
}

export async function leaveCourse(courseId) {
  const { data } = await apiClient.delete(`/user/courses/${encodeURIComponent(courseId)}`);
  return data;
}
