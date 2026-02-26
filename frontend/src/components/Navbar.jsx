import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { BookOpen, LayoutDashboard, LogOut, Zap } from 'lucide-react';

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const isActive = (path) => location.pathname === path || location.pathname.startsWith(path + '/');

  return (
    <nav
      className="border-b border-white/10 bg-bg-secondary/80 backdrop-blur-md sticky top-0 z-50"
      data-testid="navbar"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center justify-between h-14">
        {/* Logo */}
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center gap-2 group"
          data-testid="navbar-logo"
        >
          <Zap size={18} className="text-brand-primary" />
          <span
            className="font-heading font-bold text-sm tracking-widest uppercase text-text-primary group-hover:text-brand-primary transition-colors"
          >
            KnowledgeMemory
          </span>
        </button>

        {/* Nav Links */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => navigate('/dashboard')}
            data-testid="nav-dashboard"
            className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-mono transition-colors ${
              isActive('/dashboard')
                ? 'text-brand-primary bg-brand-primary/10'
                : 'text-text-secondary hover:text-text-primary hover:bg-white/5'
            }`}
          >
            <LayoutDashboard size={14} />
            <span className="hidden sm:inline">Dashboard</span>
          </button>

          <button
            onClick={() => navigate('/dashboard')}
            data-testid="nav-packs"
            className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-mono transition-colors ${
              isActive('/packs')
                ? 'text-brand-primary bg-brand-primary/10'
                : 'text-text-secondary hover:text-text-primary hover:bg-white/5'
            }`}
          >
            <BookOpen size={14} />
            <span className="hidden sm:inline">Packs</span>
          </button>
        </div>

        {/* User + Logout */}
        <div className="flex items-center gap-3">
          {user && (
            <span className="hidden sm:block text-xs font-mono text-text-muted truncate max-w-[160px]">
              {user.email}
            </span>
          )}
          <button
            onClick={handleLogout}
            data-testid="logout-btn"
            className="flex items-center gap-1 px-3 py-2 rounded-md text-sm font-mono text-text-secondary hover:text-risk-high hover:bg-risk-high/10 transition-colors"
          >
            <LogOut size={14} />
            <span className="hidden sm:inline">Logout</span>
          </button>
        </div>
      </div>
    </nav>
  );
}
