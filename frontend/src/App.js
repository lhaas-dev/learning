import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { AuthProvider, useAuth } from './context/AuthContext';
import Auth from './pages/Auth';
import Dashboard from './pages/Dashboard';
import StudyPackDetail from './pages/StudyPackDetail';
import Upload from './pages/Upload';
import Session from './pages/Session';

function ProtectedRoute({ children }) {
  const { token } = useAuth();
  return token ? children : <Navigate to="/" replace />;
}

function AppRoutes() {
  const { token } = useAuth();
  return (
    <Routes>
      <Route path="/" element={token ? <Navigate to="/dashboard" replace /> : <Auth />} />
      <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/packs/:packId" element={<ProtectedRoute><StudyPackDetail /></ProtectedRoute>} />
      <Route path="/packs/:packId/upload" element={<ProtectedRoute><Upload /></ProtectedRoute>} />
      <Route path="/session/:sessionId" element={<ProtectedRoute><Session /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="scanlines" />
        <Toaster
          theme="dark"
          toastOptions={{
            style: {
              background: '#161b22',
              border: '1px solid rgba(255,255,255,0.1)',
              color: '#E6EDF3',
              fontFamily: 'Manrope, sans-serif',
            },
          }}
        />
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
