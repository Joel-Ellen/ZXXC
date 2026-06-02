import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor: attach token
api.interceptors.request.use((config) => {
  const stored = localStorage.getItem('ai_learning_user')
  if (stored) {
    try {
      const { token } = JSON.parse(stored)
      if (token) config.headers.Authorization = `Bearer ${token}`
    } catch (e) {}
  }
  return config
})

// Response interceptor: handle 401 globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token invalid or expired — clear stored auth and redirect to home
      localStorage.removeItem('ai_learning_user')
      // Only redirect if not already on the home page
      if (window.location.pathname !== '/') {
        window.location.href = '/'
      }
    }
    return Promise.reject(error)
  }
)

// Auth API
export const authAPI = {
  login: (username, password) => api.post('/auth/login', { username, password }).then(r => r.data),
  register: (username, email, password) => api.post('/auth/register', { username, email, password }).then(r => r.data),
}

// Profile API
export const profileAPI = {
  build: (message, sessionId) => api.post('/profile/build', { message, session_id: sessionId }).then(r => r.data),
  getMyProfile: () => api.get('/profile/me').then(r => r.data),
}

// Learning Path API
export const learningAPI = {
  generatePath: (params) => api.post('/learning/generate-path', params).then(r => r.data),
  getMyPaths: () => api.get('/learning/my-paths').then(r => r.data),
}

// Resources API
export const resourcesAPI = {
  generate: (params) => api.post('/resources/generate', params).then(r => r.data),
  generateAll: (params) => api.post('/resources/generate-all', null, { params }).then(r => r.data),
  getMyResources: (params) => api.get('/resources/my-resources', { params }).then(r => r.data),
}

// Tutoring API
export const tutoringAPI = {
  ask: (params) => api.post('/tutoring/ask', params).then(r => r.data),
}

// Evaluation API
export const evaluationAPI = {
  generateReport: (params) => api.post('/evaluation/generate-report', params).then(r => r.data),
}

// Agent Status API
export const agentsAPI = {
  getStatus: () => api.get('/agents/status').then(r => r.data),
  getWorkflowDiagram: () => api.get('/agents/workflow-diagram').then(r => r.data),
}

// Knowledge Base API
export const knowledgeAPI = {
  search: (params) => api.post('/knowledge/search', null, { params }).then(r => r.data),
}

// Health Check
export const healthCheck = () => api.get('/health').then(r => r.data)

export default api
