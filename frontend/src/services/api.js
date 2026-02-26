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
    timeout: 120000, // 2 min timeout for AI processing
  });

// Concepts
export const listConcepts = (packId) => api.get(`/api/packs/${packId}/concepts`);
export const updateConcept = (conceptId, data) => api.patch(`/api/concepts/${conceptId}`, data);
export const deleteConcept = (conceptId) => api.delete(`/api/concepts/${conceptId}`);

// Sessions
export const startSession = (packId, durationMinutes) =>
  api.post('/api/sessions/start', { pack_id: packId, duration_minutes: durationMinutes });

export const answerSession = (data) => api.post('/api/sessions/answer', data);
export const getSession = (sessionId) => api.get(`/api/sessions/${sessionId}`);

// Dashboard
export const getDashboardOverview = () => api.get('/api/dashboard/overview');

export default api;
