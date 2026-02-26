import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { toast } from 'sonner';
import {
  ArrowLeft, Upload, Play, Pencil, Trash2, Check, X,
  BookOpen, AlertTriangle, Loader2, ChevronDown,
  AlertCircle, CheckCircle, Flame, GitBranch, Target
} from 'lucide-react';
import Navbar from '../components/Navbar';
import { getPack, listConcepts, updateConcept, deleteConcept, startSession } from '../services/api';

function RiskLabel({ value }) {
  const pct = Math.round((value || 0) * 100);
  if (pct > 70) return (
    <span className="flex items-center gap-1 text-xs font-mono text-risk-high">
      <AlertTriangle size={11} /> High risk
    </span>
  );
  if (pct > 40) return (
    <span className="flex items-center gap-1 text-xs font-mono text-risk-medium">
      <AlertCircle size={11} /> Medium risk
    </span>
  );
  return (
    <span className="flex items-center gap-1 text-xs font-mono text-risk-low">
      <CheckCircle size={11} /> Low risk
    </span>
  );
}

function getActionHint(concept) {
  const mistake = (concept.common_mistake || '').toLowerCase();
  const weight = concept.exam_weight_label || concept.exam_weight;
  if (mistake.includes('confus') || mistake.includes('mix')) {
    return { label: 'Often confused', icon: GitBranch, color: '#FFCC00' };
  }
  if (weight === 'high' || concept.exam_weight >= 1.5) {
    return { label: 'Frequently tested', icon: Flame, color: '#FF2D55' };
  }
  return { label: 'Common exam mistake', icon: Target, color: '#8B949E' };
}

function ExamWeightSelect({ value, onChange }) {
  return (
    <div className="relative inline-block">
      <select
        value={value || 'medium'}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none bg-black/40 border border-white/10 text-xs font-mono text-text-secondary px-3 py-1 pr-6 rounded cursor-pointer hover:border-brand-primary/40 transition-colors"
        data-testid="exam-weight-select"
      >
        <option value="low">LOW</option>
        <option value="medium">MEDIUM</option>
        <option value="high">HIGH</option>
      </select>
      <ChevronDown size={10} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
    </div>
  );
}

function ConceptCard({ concept, onUpdate, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(concept.title);
  const [definition, setDefinition] = useState(concept.short_definition);
  const [mistake, setMistake] = useState(concept.common_mistake);
  const [weight, setWeight] = useState(concept.exam_weight_label || 'medium');
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await updateConcept(concept.id, {
        title,
        short_definition: definition,
        common_mistake: mistake,
        exam_weight: weight,
      });
      onUpdate(res.data);
      setEditing(false);
      toast.success('Concept updated');
    } catch {
      toast.error('Failed to update concept');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Delete this concept and all its checks?')) return;
    setDeleting(true);
    try {
      await deleteConcept(concept.id);
      onDelete(concept.id);
      toast.success('Concept deleted');
    } catch {
      toast.error('Failed to delete');
    } finally {
      setDeleting(false);
    }
  };

  const handleWeightChange = async (newWeight) => {
    setWeight(newWeight);
    try {
      const res = await updateConcept(concept.id, { exam_weight: newWeight });
      onUpdate(res.data);
    } catch {
      toast.error('Failed to update weight');
    }
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5 group"
      data-testid={`concept-card-${concept.id}`}
    >
      {editing ? (
        <div className="space-y-3">
          <input
            data-testid="concept-title-edit"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="terminal-input text-sm font-medium"
            placeholder="Concept title"
          />
          <textarea
            data-testid="concept-definition-edit"
            value={definition}
            onChange={(e) => setDefinition(e.target.value)}
            className="terminal-input text-sm resize-none h-20"
            placeholder="Short definition"
          />
          <textarea
            data-testid="concept-mistake-edit"
            value={mistake}
            onChange={(e) => setMistake(e.target.value)}
            className="terminal-input text-sm resize-none h-16"
            placeholder="Common mistake"
          />
          <div className="flex items-center gap-3 pt-1">
            <ExamWeightSelect value={weight} onChange={setWeight} />
            <div className="ml-auto flex gap-2">
              <button onClick={() => setEditing(false)} className="btn-secondary py-1.5 px-3 text-xs">
                <X size={12} /> Cancel
              </button>
              <button
                data-testid="save-concept-btn"
                onClick={handleSave}
                disabled={saving}
                className="btn-primary py-1.5 px-3 text-xs"
              >
                {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                Save
              </button>
            </div>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex items-center gap-2 flex-wrap min-w-0">
              <h4 className="font-heading text-sm font-semibold text-text-primary">{concept.title}</h4>
              <RiskLabel value={concept.risk} />
            </div>
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
              <ExamWeightSelect value={weight} onChange={handleWeightChange} />
              <button
                data-testid={`edit-concept-btn-${concept.id}`}
                onClick={() => setEditing(true)}
                className="p-1.5 text-text-secondary hover:text-brand-primary rounded"
              >
                <Pencil size={13} />
              </button>
              <button
                data-testid={`delete-concept-btn-${concept.id}`}
                onClick={handleDelete}
                disabled={deleting}
                className="p-1.5 text-text-secondary hover:text-risk-high rounded"
              >
                {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              </button>
            </div>
          </div>

          <p className="text-sm text-text-secondary mb-3 leading-relaxed">{concept.short_definition}</p>

          <div className="flex items-center justify-between gap-3 flex-wrap">
            {/* Action hint */}
            {(() => {
              const hint = getActionHint(concept);
              const HintIcon = hint.icon;
              return (
                <span className="flex items-center gap-1.5 text-xs font-mono" style={{ color: hint.color }}>
                  <HintIcon size={11} />
                  {hint.label}
                </span>
              );
            })()}

            {concept.common_mistake && (
              <div className="flex items-start gap-1.5 bg-risk-high/5 border border-risk-high/10 rounded px-2 py-1 max-w-xs">
                <AlertTriangle size={10} className="text-risk-high flex-shrink-0 mt-0.5" />
                <span className="text-xs text-risk-high/80 leading-tight">{concept.common_mistake}</span>
              </div>
            )}
          </div>
        </>
      )}
    </motion.div>
  );
}

function StartSessionModal({ packId, onClose, onStart }) {
  const [duration, setDuration] = useState(10);
  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    setLoading(true);
    try {
      const res = await startSession(packId, duration);
      onStart(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to start session');
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-card w-full max-w-sm p-6"
        data-testid="start-session-modal"
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-heading text-lg font-semibold">Start Session</h3>
          <button onClick={onClose} className="text-text-secondary hover:text-white" data-testid="close-session-modal">
            <X size={18} />
          </button>
        </div>
        <p className="text-sm text-text-secondary mb-5">
          Concepts are selected by risk — your weakest areas come first.
        </p>
        <div className="space-y-2 mb-6">
          {[
            { mins: 10, label: '10 min', sublabel: '~8 concepts' },
            { mins: 20, label: '20 min', sublabel: '~15 concepts' },
            { mins: 30, label: '30 min', sublabel: '~22 concepts' },
          ].map(({ mins, label, sublabel }) => (
            <button
              key={mins}
              data-testid={`duration-${mins}`}
              onClick={() => setDuration(mins)}
              className={`w-full flex items-center justify-between p-3 rounded-md border transition-all ${
                duration === mins
                  ? 'border-brand-primary bg-brand-primary/10 text-brand-primary'
                  : 'border-white/10 text-text-secondary hover:border-white/20'
              }`}
            >
              <span className="font-mono text-sm">{label}</span>
              <span className="text-xs">{sublabel}</span>
            </button>
          ))}
        </div>
        <button
          data-testid="confirm-start-session-btn"
          onClick={handleStart}
          disabled={loading}
          className="btn-primary w-full justify-center"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          {loading ? 'Loading...' : 'Start Session'}
        </button>
      </motion.div>
    </div>
  );
}

export default function StudyPackDetail() {
  const { packId } = useParams();
  const navigate = useNavigate();
  const [pack, setPack] = useState(null);
  const [concepts, setConcepts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showSessionModal, setShowSessionModal] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [packRes, conceptsRes] = await Promise.all([
        getPack(packId),
        listConcepts(packId),
      ]);
      setPack(packRes.data);
      setConcepts(conceptsRes.data);
    } catch (err) {
      toast.error('Failed to load pack');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  }, [packId, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const onConceptUpdate = (updated) => {
    setConcepts((prev) => prev.map((c) => (c.id === updated.id ? { ...c, ...updated } : c)));
  };

  const onConceptDelete = (id) => {
    setConcepts((prev) => prev.filter((c) => c.id !== id));
  };

  const onSessionStart = (sessionData) => {
    navigate(`/session/${sessionData.session_id}`, {
      state: {
        currentItem: sessionData.current_item,
        total: sessionData.total,
        packTitle: pack?.title,
      },
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-bg-primary flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-brand-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-primary" data-testid="pack-detail-page">
      <Navbar />
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        {/* Header */}
        <div className="flex items-start justify-between mb-8 gap-4">
          <div className="flex items-start gap-4">
            <button
              data-testid="back-to-dashboard"
              onClick={() => navigate('/dashboard')}
              className="mt-1 text-text-secondary hover:text-text-primary transition-colors"
            >
              <ArrowLeft size={18} />
            </button>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-mono text-text-muted uppercase tracking-widest">
                  {pack?.domain || 'General'}
                </span>
              </div>
              <h1 className="font-heading text-2xl font-bold text-text-primary">{pack?.title}</h1>
              {pack?.description && (
                <p className="text-sm text-text-secondary mt-1">{pack.description}</p>
              )}
              <p className="text-xs font-mono text-text-muted mt-1">
                {concepts.length} concepts
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <button
              data-testid="upload-material-btn"
              onClick={() => navigate(`/packs/${packId}/upload`)}
              className="btn-secondary"
            >
              <Upload size={14} />
              Upload
            </button>
            <button
              data-testid="start-session-btn"
              onClick={() => setShowSessionModal(true)}
              disabled={concepts.length === 0}
              className="btn-primary"
            >
              <Play size={14} />
              Study
            </button>
          </div>
        </div>

        {/* Concepts */}
        {concepts.length === 0 ? (
          <div className="glass-card p-12 text-center">
            <BookOpen size={40} className="mx-auto mb-4 text-text-muted opacity-40" />
            <h3 className="font-heading text-lg font-semibold text-text-secondary mb-2">No concepts yet</h3>
            <p className="text-sm text-text-muted mb-5">
              Upload PDF or text material to extract concepts automatically
            </p>
            <button
              data-testid="upload-first-material-btn"
              onClick={() => navigate(`/packs/${packId}/upload`)}
              className="btn-primary"
            >
              <Upload size={14} />
              Upload Material
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {concepts.map((c) => (
              <ConceptCard
                key={c.id}
                concept={c}
                onUpdate={onConceptUpdate}
                onDelete={onConceptDelete}
              />
            ))}
          </div>
        )}
      </div>

      {showSessionModal && (
        <StartSessionModal
          packId={packId}
          onClose={() => setShowSessionModal(false)}
          onStart={onSessionStart}
        />
      )}
    </div>
  );
}
