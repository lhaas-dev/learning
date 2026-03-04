import axios from 'axios';

const BASE_URL = process.env.REACT_APP_BACKEND_URL;

const api = axios.create({
  baseURL: BASE_URL,
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('km_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auth
export const register = (email, password) =>
  api.post('/api/auth/register', { email, password });

export const login = (email, password) =>
  api.post('/api/auth/login', { email, password });

// Study Packs
export const createPack = (data) => api.post('/api/packs', data);
export const listPacks = () => api.get('/api/packs');
export const getPack = (id) => api.get(`/api/packs/${id}`);

// Upload
export const uploadMaterial = (packId, formData) =>
  api.post(`/api/packs/${packId}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });

export const getJobStatus = (jobId) => api.get(`/api/jobs/${jobId}`);

export const streamJobProgress = (jobId, onProgress, onDone) => {
  const token = localStorage.getItem('km_token');
  const url = `${BASE_URL}/api/jobs/${jobId}/stream?token=${encodeURIComponent(token)}`;
  const es = new EventSource(url);
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.status === 'stream_end') { es.close(); onDone(null); return; }
      if (data.status === 'complete' || data.status === 'failed') {
        onProgress(data);
        es.close();
        onDone(data);
      } else {
        onProgress(data);
      }
    } catch { /* ignore parse errors */ }
  };
  es.onerror = () => { es.close(); onDone(null); };
  return es; // caller can close it
};

// Concepts
export const listConcepts = (packId) => api.get(`/api/packs/${packId}/concepts`);
export const updateConcept = (conceptId, data) => api.patch(`/api/concepts/${conceptId}`, data);
export const deleteConcept = (conceptId) => api.delete(`/api/concepts/${conceptId}`);
export const reportConcept = (conceptId) => api.post(`/api/concepts/${conceptId}/report`);

// Sessions
export const startSession = (packId, durationMinutes, docTypeFilter = null) =>
  api.post('/api/sessions/start', {
    pack_id: packId,
    duration_minutes: durationMinutes,
    ...(docTypeFilter && docTypeFilter !== 'all' ? { doc_type_filter: docTypeFilter } : {}),
  });

export const answerSession = (data) => api.post('/api/sessions/answer', data);
export const getSession = (sessionId) => api.get(`/api/sessions/${sessionId}`);
export const getSessionDebrief = (sessionId) => api.get(`/api/sessions/${sessionId}/debrief`);
export const startDrillSession = (conceptIds) =>
  api.post('/api/sessions/drill', { concept_ids: conceptIds });

// Answer Evaluation
export const evaluateAnswer = (checkId, userAnswer) =>
  api.post('/api/checks/evaluate', { check_id: checkId, user_answer: userAnswer });

// Chunked PDF Upload
export const uploadChunk = (data) =>
  api.post('/api/upload/chunk', data);

export const finalizeUpload = (data) =>
  api.post('/api/upload/finalize', data);

export const uploadFromUrl = (packId, url) =>
  api.post('/api/upload/url', { pack_id: packId, url });

// Dashboard
export const getDashboardOverview = () => api.get('/api/dashboard/overview');

export default api;
