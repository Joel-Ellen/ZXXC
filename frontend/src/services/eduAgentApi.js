import apiClient, { tokenStore } from "./apiClient";

// ── 认证 ──
export async function getCaptcha() {
  const { data } = await apiClient.get("/auth/captcha-json");
  return data;
}

export async function register(payload) {
  const { data } = await apiClient.post("/auth/register", payload);
  if (data.access_token) tokenStore.setTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
  return data;
}

export async function login(payload) {
  const { data } = await apiClient.post("/auth/login", payload);
  if (data.access_token) tokenStore.setTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
  return data;
}

export async function refreshToken() {
  const rt = tokenStore.getRefreshToken();
  if (!rt) return null;
  const { data } = await apiClient.post("/auth/refresh", { refresh_token: rt });
  if (data.access_token) tokenStore.setTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
  return data;
}

export async function fetchMyProfile() {
  const { data } = await apiClient.get("/auth/me");
  return data;
}

// ── 学习流水线 ──
export async function resetSession(userId) {
  const { data } = await apiClient.post("/reset", { user_id: userId });
  return data;
}

export async function fetchState(userId, courseId = "data_structures") {
  const { data } = await apiClient.get("/state", { params: { user_id: userId, course_id: courseId } });
  return data;
}

export async function fetchProbe(userId, courseId = "data_structures") {
  const { data } = await apiClient.get("/cold-start/probe", { params: { user_id: userId, course_id: courseId } });
  return data;
}

export async function submitProbeAnswer(userId, answer, courseId = "data_structures") {
  const { data } = await apiClient.post("/cold-start/answer", { user_id: userId, answer, course_id: courseId });
  return data;
}

export async function initLearningPath(userId, courseId = "data_structures") {
  const { data } = await apiClient.post("/init-path", { user_id: userId, course_id: courseId });
  return data;
}

export async function runPipelineStep(payload) {
  const { data } = await apiClient.post("/pipeline/step", payload);
  return data;
}

export async function askTutor(payload) {
  const { data } = await apiClient.post("/tutor/ask", payload);
  return data;
}

export async function fetchKnowledgeGraph(courseId = "data_structures") {
  const { data } = await apiClient.get("/knowledge-graph", { params: { course_id: courseId } });
  return data;
}

// ── 课程 ──
export async function fetchCourses(search) {
  const { data } = await apiClient.get("/courses", { params: search ? { search } : {} });
  return data;
}

export async function fetchCourseDetail(courseId) {
  const { data } = await apiClient.get(`/courses/${courseId}`);
  return data;
}

export async function fetchUserCourses(userId) {
  const { data } = await apiClient.get("/user/courses", { params: { user_id: userId } });
  return data;
}

export async function enrollCourse(userId, courseId) {
  const { data } = await apiClient.post("/user/courses/enroll", { user_id: userId, course_id: courseId });
  return data;
}

export async function switchCourse(userId, courseId) {
  const { data } = await apiClient.post("/user/courses/switch", { user_id: userId, course_id: courseId });
  return data;
}
