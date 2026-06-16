import apiClient from "./apiClient";

export async function resetSession(userId) {
  const { data } = await apiClient.post("/reset", { user_id: userId });
  return data;
}

export async function fetchState(userId) {
  const { data } = await apiClient.get("/state", { params: { user_id: userId } });
  return data;
}

export async function fetchProbe(userId) {
  const { data } = await apiClient.get("/cold-start/probe", { params: { user_id: userId } });
  return data;
}

export async function submitProbeAnswer(userId, answer) {
  const { data } = await apiClient.post("/cold-start/answer", {
    user_id: userId,
    answer,
  });
  return data;
}

export async function initLearningPath(userId) {
  const { data } = await apiClient.post("/init-path", { user_id: userId });
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

export async function fetchKnowledgeGraph() {
  const { data } = await apiClient.get("/knowledge-graph");
  return data;
}
