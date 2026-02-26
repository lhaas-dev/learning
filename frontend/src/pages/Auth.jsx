import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { toast } from 'sonner';
import { Zap, Lock, Mail, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { login as apiLogin, register as apiRegister } from '../services/api';

export default function Auth() {
  const [tab, setTab] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error('Please fill all fields');
      return;
    }
    setLoading(true);
    try {
      let res;
      if (tab === 'login') {
        res = await apiLogin(email, password);
      } else {
        res = await apiRegister(email, password);
      }
      login(res.data.token, { email: res.data.email, user_id: res.data.user_id });
      toast.success(tab === 'login' ? 'Welcome back!' : 'Account created!');
      navigate('/dashboard');
    } catch (err) {
      const msg = err.response?.data?.detail || 'Something went wrong';
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full">
      {/* Left panel – cyber image */}
      <div
        className="hidden md:flex w-1/2 relative overflow-hidden items-end p-10"
        style={{
          backgroundImage: `url('https://images.unsplash.com/photo-1660836814985-8523a0d713b5?w=900&q=80')`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/60 to-transparent" />
        <div className="relative z-10">
          <div className="flex items-center gap-2 mb-4">
            <Zap size={20} className="text-brand-primary" />
            <span className="font-heading font-bold text-xs tracking-widest uppercase text-brand-primary">
              KnowledgeMemory
            </span>
          </div>
          <h1 className="font-heading text-4xl font-bold text-white leading-tight mb-3">
            Learn What<br />
            <span className="text-brand-primary">Actually Matters</span>
          </h1>
          <p className="text-text-secondary text-sm font-body max-w-xs leading-relaxed">
            AI-powered adaptive learning engine. Upload your study material.
            Get risk-based sessions that target your actual knowledge gaps.
          </p>
        </div>
      </div>

      {/* Right panel – form */}
      <div className="w-full md:w-1/2 flex items-center justify-center bg-bg-secondary p-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-sm"
        >
          {/* Mobile logo */}
          <div className="flex items-center gap-2 mb-8 md:hidden">
            <Zap size={18} className="text-brand-primary" />
            <span className="font-heading font-bold text-sm tracking-widest uppercase">
              KnowledgeMemory
            </span>
          </div>

          {/* Tab switcher */}
          <div className="flex border border-white/10 rounded-md mb-8 p-1 bg-black/30">
            <button
              data-testid="tab-login"
              onClick={() => setTab('login')}
              className={`flex-1 py-2 text-sm font-mono rounded transition-all ${
                tab === 'login'
                  ? 'bg-brand-primary text-black font-bold'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              Login
            </button>
            <button
              data-testid="tab-register"
              onClick={() => setTab('register')}
              className={`flex-1 py-2 text-sm font-mono rounded transition-all ${
                tab === 'register'
                  ? 'bg-brand-primary text-black font-bold'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              Register
            </button>
          </div>

          <h2 className="font-heading text-2xl font-semibold mb-1 text-text-primary">
            {tab === 'login' ? 'Access System' : 'Create Account'}
          </h2>
          <p className="text-text-secondary text-sm font-body mb-6">
            {tab === 'login'
              ? 'Enter your credentials to continue'
              : 'Start your adaptive learning journey'}
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-mono text-text-muted uppercase tracking-widest mb-1">
                Email
              </label>
              <div className="relative">
                <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
                <input
                  data-testid="input-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="operator@domain.com"
                  className="terminal-input pl-9"
                  autoComplete="email"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-mono text-text-muted uppercase tracking-widest mb-1">
                Password
              </label>
              <div className="relative">
                <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
                <input
                  data-testid="input-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="terminal-input pl-9 pr-10"
                  autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <button
              data-testid="auth-submit-btn"
              type="submit"
              disabled={loading}
              className="btn-primary w-full justify-center mt-2"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                  Processing...
                </span>
              ) : tab === 'login' ? (
                'Login'
              ) : (
                'Create Account'
              )}
            </button>
          </form>

          <p className="mt-6 text-xs text-text-muted font-mono text-center">
            {tab === 'login' ? (
              <>
                No account?{' '}
                <button
                  data-testid="switch-to-register"
                  onClick={() => setTab('register')}
                  className="text-brand-primary hover:underline"
                >
                  Register
                </button>
              </>
            ) : (
              <>
                Already registered?{' '}
                <button
                  data-testid="switch-to-login"
                  onClick={() => setTab('login')}
                  className="text-brand-primary hover:underline"
                >
                  Login
                </button>
              </>
            )}
          </p>
        </motion.div>
      </div>
    </div>
  );
}
