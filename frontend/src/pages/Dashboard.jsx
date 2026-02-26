import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { toast } from 'sonner';
import {
  LayoutDashboard, BookOpen, Plus, Play, TrendingUp, AlertTriangle,
  Clock, CheckCircle, X, Loader2
} from 'lucide-react';
import Navbar from '../components/Navbar';
import { getDashboardOverview, listPacks, createPack } from '../services/api';

function RiskBar({ value }) {
  const pct = Math.round(value * 100);
  const color = pct > 70 ? '#FF2D55' : pct > 40 ? '#FFCC00' : '#00C853';
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-mono" style={{ color }}>{pct}%</span>
    </div>
  );
}

function RiskBadge({ value }) {
  const pct = Math.round(value * 100);
  if (pct > 70) return <span className="risk-badge-high">HIGH</span>;
  if (pct > 40) return <span className="risk-badge-medium">MED</span>;
  return <span className="risk-badge-low">LOW</span>;
}

function CreatePackModal({ onClose, onCreate }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [domain, setDomain] = useState('Cyber Security');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim()) { toast.error('Title required'); return; }
    setLoading(true);
    try {
      const res = await createPack({ title, description, domain });
      onCreate(res.data);
      toast.success('Study Pack created!');
      onClose();
    } catch {
      toast.error('Failed to create pack');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-card w-full max-w-md p-6"
        data-testid="create-pack-modal"
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-heading text-lg font-semibold">New Study Pack</h3>
          <button onClick={onClose} className="text-text-secondary hover:text-white" data-testid="close-modal-btn">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-mono text-text-muted uppercase tracking-widest mb-1">Title *</label>
            <input
              data-testid="pack-title-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Network Security Fundamentals"
              className="terminal-input"
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-text-muted uppercase tracking-widest mb-1">Domain</label>
            <input
              data-testid="pack-domain-input"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="e.g. Cyber Security"
              className="terminal-input"
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-text-muted uppercase tracking-widest mb-1">Description</label>
            <textarea
              data-testid="pack-description-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description..."
              className="terminal-input resize-none h-20"
            />
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Cancel</button>
            <button data-testid="create-pack-submit-btn" type="submit" disabled={loading} className="btn-primary flex-1 justify-center">
              {loading ? <Loader2 size={14} className="animate-spin" /> : 'Create Pack'}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState(null);
  const [packs, setPacks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);

  useEffect(() => {
    Promise.all([getDashboardOverview(), listPacks()])
      .then(([ov, pk]) => {
        setOverview(ov.data);
        setPacks(pk.data);
      })
      .catch(() => toast.error('Failed to load dashboard'))
      .finally(() => setLoading(false));
  }, []);

  const onPackCreated = (pack) => {
    setPacks((prev) => [pack, ...prev]);
    navigate(`/packs/${pack.id}`);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-bg-primary flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-brand-primary" />
      </div>
    );
  }

  const avgRiskPct = overview ? Math.round(overview.avg_risk * 100) : 0;
  const riskColor = avgRiskPct > 70 ? '#FF2D55' : avgRiskPct > 40 ? '#FFCC00' : '#00C853';

  return (
    <div className="min-h-screen bg-bg-primary" data-testid="dashboard-page">
      <Navbar />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-heading text-3xl font-bold text-text-primary">Command Center</h1>
            <p className="text-text-secondary text-sm font-body mt-1">Your learning risk overview</p>
          </div>
          <button
            data-testid="new-pack-btn"
            onClick={() => setShowCreateModal(true)}
            className="btn-primary"
          >
            <Plus size={16} />
            New Pack
          </button>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Avg Risk', value: `${avgRiskPct}%`, icon: AlertTriangle, color: riskColor },
            { label: 'Study Packs', value: overview?.total_packs ?? 0, icon: BookOpen, color: '#00E5FF' },
            { label: 'Concepts', value: overview?.total_concepts ?? 0, icon: LayoutDashboard, color: '#2F81F7' },
            { label: 'Reviewed', value: overview?.reviewed_concepts ?? 0, icon: CheckCircle, color: '#00C853' },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className="glass-card p-4" data-testid={`stat-${label.toLowerCase().replace(' ', '-')}`}>
              <div className="flex items-center gap-2 mb-1">
                <Icon size={14} style={{ color }} />
                <span className="text-xs font-mono text-text-muted uppercase tracking-widest">{label}</span>
              </div>
              <div className="font-heading text-2xl font-bold" style={{ color }}>{value}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
          {/* Weakest Concepts */}
          <div className="md:col-span-5 glass-card p-6" data-testid="weakest-concepts-panel">
            <div className="flex items-center gap-2 mb-4">
              <AlertTriangle size={14} className="text-risk-high" />
              <h3 className="font-heading text-sm font-semibold uppercase tracking-widest text-text-secondary">
                Highest Risk
              </h3>
            </div>
            {overview?.weakest_concepts?.length > 0 ? (
              <div className="space-y-3">
                {overview.weakest_concepts.map((c, i) => (
                  <div key={c.concept_id} data-testid={`weak-concept-${i}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-text-primary truncate max-w-[200px]">{c.concept_title}</span>
                      <RiskBadge value={c.risk} />
                    </div>
                    <RiskBar value={c.risk} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6 text-text-muted text-sm">
                <TrendingUp size={24} className="mx-auto mb-2 opacity-30" />
                <p>No concepts reviewed yet</p>
                <p className="text-xs mt-1">Upload material and start a session</p>
              </div>
            )}
          </div>

          {/* Right column: Study Packs + Session History */}
          <div className="md:col-span-7 space-y-6">
            {/* Study Packs */}
            <div className="glass-card p-6" data-testid="study-packs-panel">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <BookOpen size={14} className="text-brand-primary" />
                  <h3 className="font-heading text-sm font-semibold uppercase tracking-widest text-text-secondary">
                    Study Packs
                  </h3>
                </div>
                <button
                  data-testid="new-pack-btn-2"
                  onClick={() => setShowCreateModal(true)}
                  className="text-xs font-mono text-brand-primary hover:text-brand-secondary flex items-center gap-1"
                >
                  <Plus size={12} /> New
                </button>
              </div>
              {packs.length > 0 ? (
                <div className="space-y-2">
                  {packs.map((p) => (
                    <button
                      key={p.id}
                      data-testid={`pack-card-${p.id}`}
                      onClick={() => navigate(`/packs/${p.id}`)}
                      className="w-full flex items-center justify-between p-3 rounded-md bg-black/30 border border-white/5 hover:border-brand-primary/30 transition-all group"
                    >
                      <div className="text-left">
                        <div className="text-sm font-medium text-text-primary group-hover:text-brand-primary transition-colors">
                          {p.title}
                        </div>
                        <div className="text-xs font-mono text-text-muted mt-0.5">
                          {p.concept_count} concepts · {p.domain || 'General'}
                        </div>
                      </div>
                      <Play size={14} className="text-text-muted group-hover:text-brand-primary transition-colors flex-shrink-0" />
                    </button>
                  ))}
                </div>
              ) : (
                <div className="text-center py-6 text-text-muted text-sm">
                  <BookOpen size={24} className="mx-auto mb-2 opacity-30" />
                  <p>No study packs yet</p>
                  <button
                    data-testid="create-first-pack-btn"
                    onClick={() => setShowCreateModal(true)}
                    className="text-xs font-mono text-brand-primary hover:underline mt-1"
                  >
                    + Create your first pack
                  </button>
                </div>
              )}
            </div>

            {/* Session History */}
            <div className="glass-card p-6" data-testid="session-history-panel">
              <div className="flex items-center gap-2 mb-4">
                <Clock size={14} className="text-brand-secondary" />
                <h3 className="font-heading text-sm font-semibold uppercase tracking-widest text-text-secondary">
                  Recent Sessions
                </h3>
              </div>
              {overview?.recent_sessions?.length > 0 ? (
                <div className="space-y-2">
                  {overview.recent_sessions.map((s) => {
                    const total = s.total || 0;
                    const good = (s.stats?.good || 0) + (s.stats?.easy || 0);
                    const pct = total > 0 ? Math.round((good / total) * 100) : 0;
                    return (
                      <div
                        key={s.id}
                        data-testid={`session-history-${s.id}`}
                        className="flex items-center justify-between p-3 rounded-md bg-black/30 border border-white/5"
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <div className="text-sm text-text-primary">{s.pack_title}</div>
                            {s.is_drill && (
                              <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-risk-high/10 text-risk-high border border-risk-high/20">DRILL</span>
                            )}
                          </div>
                          <div className="text-xs font-mono text-text-muted mt-0.5">
                            {s.duration_minutes}min · {total} items
                          </div>
                        </div>
                        <div className="text-right">
                          <div
                            className="text-sm font-mono font-bold"
                            style={{ color: pct >= 70 ? '#00C853' : pct >= 40 ? '#FFCC00' : '#FF2D55' }}
                          >
                            {pct}%
                          </div>
                          <div className="text-xs font-mono text-text-muted">correct</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-center py-6 text-text-muted text-sm">
                  <Clock size={24} className="mx-auto mb-2 opacity-30" />
                  <p>No sessions completed yet</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {showCreateModal && (
        <CreatePackModal
          onClose={() => setShowCreateModal(false)}
          onCreate={onPackCreated}
        />
      )}
    </div>
  );
}
