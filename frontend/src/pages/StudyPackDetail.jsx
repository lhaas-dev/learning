import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import {
  ArrowLeft, Upload, Play, Pencil, Trash2, Check, X,
  BookOpen, AlertTriangle, Loader2, ChevronDown,
  AlertCircle, CheckCircle, Flame, GitBranch, Target, Tag, Filter,
  Flag, Square, CheckSquare, Minus,
} from 'lucide-react';
import Navbar from '../components/Navbar';
import {
  getPack, listConcepts, updateConcept, deleteConcept, startSession,
  listReportedConcepts, bulkDeleteConcepts, bulkDismissReports,
} from '../services/api';

// ─── Doc type badge ───────────────────────────────────────────────────────────
const DOC_TYPE_COLORS = {
  'Theoriebuch':        { color: '#2F81F7', bg: 'rgba(47,129,247,0.1)' },
  'Theorie & Aufgaben': { color: '#00E5FF', bg: 'rgba(0,229,255,0.08)' },
  'Abschlussprüfung':   { color: '#FF2D55', bg: 'rgba(255,45,85,0.1)' },
  'Übungstest':         { color: '#FFCC00', bg: 'rgba(255,204,0,0.1)' },
  'Zusammenfassung':    { color: '#00C853', bg: 'rgba(0,200,83,0.1)' },
  'Skript':             { color: '#8B5CF6', bg: 'rgba(139,92,246,0.1)' },
  'Webseite':           { color: '#00E5FF', bg: 'rgba(0,229,255,0.08)' },
  'Sonstiges':          { color: '#8B949E', bg: 'rgba(139,148,158,0.1)' },
};
function DocTypeBadge({ type, small = false }) {
  if (!type) return null;
  const cfg = DOC_TYPE_COLORS[type] || DOC_TYPE_COLORS['Sonstiges'];
  return (
    <span
      className={`inline-flex items-center gap-1 font-mono rounded border ${small ? 'text-[10px] px-1.5 py-0.5' : 'text-xs px-2 py-0.5'}`}
      style={{ color: cfg.color, background: cfg.bg, borderColor: `${cfg.color}35` }}
    >
      <Tag size={small ? 8 : 9} />
      {type}
    </span>
  );
}

function RiskLabel({ value }) {
  const pct = Math.round((value || 0) * 100);
  if (pct > 70) return <span className="flex items-center gap-1 text-xs font-mono text-risk-high"><AlertTriangle size={11} /> High risk</span>;
  if (pct > 40) return <span className="flex items-center gap-1 text-xs font-mono text-risk-medium"><AlertCircle size={11} /> Medium risk</span>;
  return <span className="flex items-center gap-1 text-xs font-mono text-risk-low"><CheckCircle size={11} /> Low risk</span>;
}

function getActionHint(concept) {
  const mistake = (concept.common_mistake || '').toLowerCase();
  const weight = concept.exam_weight_label || concept.exam_weight;
  if (mistake.includes('confus') || mistake.includes('mix')) return { label: 'Often confused', icon: GitBranch, color: '#FFCC00' };
  if (weight === 'high' || concept.exam_weight >= 1.5) return { label: 'Frequently tested', icon: Flame, color: '#FF2D55' };
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

// ─── ConceptCard ─────────────────────────────────────────────────────────────
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
      const res = await updateConcept(concept.id, { title, short_definition: definition, common_mistake: mistake, exam_weight: weight });
      onUpdate(res.data);
      setEditing(false);
      toast.success('Concept updated');
    } catch { toast.error('Failed to update concept'); }
    finally { setSaving(false); }
  };

  const handleDelete = async () => {
    if (!window.confirm('Delete this concept and all its checks?')) return;
    setDeleting(true);
    try {
      await deleteConcept(concept.id);
      onDelete(concept.id);
      toast.success('Concept deleted');
    } catch { toast.error('Failed to delete'); }
    finally { setDeleting(false); }
  };

  const handleWeightChange = async (newWeight) => {
    setWeight(newWeight);
    try {
      const res = await updateConcept(concept.id, { exam_weight: newWeight });
      onUpdate(res.data);
    } catch { toast.error('Failed to update weight'); }
  };

  return (
    <motion.div layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5 group" data-testid={`concept-card-${concept.id}`}>
      {editing ? (
        <div className="space-y-3">
          <input data-testid="concept-title-edit" value={title} onChange={(e) => setTitle(e.target.value)}
            className="terminal-input text-sm font-medium" placeholder="Concept title" />
          <textarea data-testid="concept-definition-edit" value={definition} onChange={(e) => setDefinition(e.target.value)}
            className="terminal-input text-sm resize-none h-20" placeholder="Short definition" />
          <textarea data-testid="concept-mistake-edit" value={mistake} onChange={(e) => setMistake(e.target.value)}
            className="terminal-input text-sm resize-none h-16" placeholder="Common mistake" />
          <div className="flex items-center gap-3 pt-1">
            <ExamWeightSelect value={weight} onChange={setWeight} />
            <div className="ml-auto flex gap-2">
              <button onClick={() => setEditing(false)} className="btn-secondary py-1.5 px-3 text-xs"><X size={12} /> Cancel</button>
              <button data-testid="save-concept-btn" onClick={handleSave} disabled={saving} className="btn-primary py-1.5 px-3 text-xs">
                {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Save
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
              {concept.doc_type && <DocTypeBadge type={concept.doc_type} small />}
            </div>
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
              <ExamWeightSelect value={weight} onChange={handleWeightChange} />
              <button data-testid={`edit-concept-btn-${concept.id}`} onClick={() => setEditing(true)}
                className="p-1.5 text-text-secondary hover:text-brand-primary rounded"><Pencil size={13} /></button>
              <button data-testid={`delete-concept-btn-${concept.id}`} onClick={handleDelete} disabled={deleting}
                className="p-1.5 text-text-secondary hover:text-risk-high rounded">
                {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              </button>
            </div>
          </div>
          <p className="text-sm text-text-secondary mb-3 leading-relaxed">{concept.short_definition}</p>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            {(() => {
              const hint = getActionHint(concept);
              const HintIcon = hint.icon;
              return <span className="flex items-center gap-1.5 text-xs font-mono" style={{ color: hint.color }}><HintIcon size={11} />{hint.label}</span>;
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

// ─── Reported Concept Row ─────────────────────────────────────────────────────
function ReportedConceptRow({ concept, selected, onToggle, onDelete, onDismiss }) {
  const [deleting, setDeleting] = useState(false);
  const [dismissing, setDismissing] = useState(false);

  const handleDelete = async (e) => {
    e.stopPropagation();
    setDeleting(true);
    await onDelete(concept.id);
    setDeleting(false);
  };

  const handleDismiss = async (e) => {
    e.stopPropagation();
    setDismissing(true);
    await onDismiss(concept.id);
    setDismissing(false);
  };

  const reportedDate = concept.reported_at
    ? new Date(concept.reported_at).toLocaleDateString('de-CH', { day: '2-digit', month: '2-digit', year: '2-digit' })
    : '–';

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 10 }}
      onClick={() => onToggle(concept.id)}
      data-testid={`reported-row-${concept.id}`}
      className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-all group ${
        selected
          ? 'border-risk-high/50 bg-risk-high/5'
          : 'border-white/5 bg-white/[0.02] hover:border-white/10'
      }`}
    >
      {/* Checkbox */}
      <div className="mt-0.5 flex-shrink-0 text-risk-high">
        {selected ? <CheckSquare size={16} /> : <Square size={16} className="text-text-muted" />}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <span className="text-sm font-semibold text-text-primary">{concept.title}</span>
          {concept.doc_type && <DocTypeBadge type={concept.doc_type} small />}
          <span className="text-[10px] font-mono text-text-muted ml-auto">gemeldet {reportedDate}</span>
        </div>
        <p className="text-xs text-text-secondary line-clamp-2 mb-1">{concept.short_definition}</p>
        {concept.common_mistake && (
          <p className="text-[11px] text-risk-high/70 italic">Typischer Fehler: {concept.common_mistake}</p>
        )}
      </div>

      {/* Per-row actions */}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" onClick={(e) => e.stopPropagation()}>
        <button
          data-testid={`dismiss-reported-${concept.id}`}
          onClick={handleDismiss}
          disabled={dismissing}
          title="Meldung verwerfen – Konzept behalten"
          className="flex items-center gap-1 px-2 py-1 text-[11px] font-mono text-text-muted hover:text-brand-primary border border-white/10 hover:border-brand-primary/40 rounded transition-all"
        >
          {dismissing ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
          Dismiss
        </button>
        <button
          data-testid={`delete-reported-${concept.id}`}
          onClick={handleDelete}
          disabled={deleting}
          title="Konzept löschen"
          className="flex items-center gap-1 px-2 py-1 text-[11px] font-mono text-text-muted hover:text-risk-high border border-white/10 hover:border-risk-high/40 rounded transition-all"
        >
          {deleting ? <Loader2 size={10} className="animate-spin" /> : <Trash2 size={10} />}
          Löschen
        </button>
      </div>
    </motion.div>
  );
}

// ─── Reported Tab ─────────────────────────────────────────────────────────────
function ReportedTab({ packId, onCountChange }) {
  const [reported, setReported] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [bulkActing, setBulkActing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listReportedConcepts(packId);
      setReported(res.data);
      onCountChange(res.data.length);
    } catch { toast.error('Fehler beim Laden der gemeldeten Konzepte'); }
    finally { setLoading(false); }
  }, [packId, onCountChange]);

  useEffect(() => { load(); }, [load]);

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(reported.map(r => r.id)));
  const selectNone = () => setSelected(new Set());
  const allSelected = reported.length > 0 && selected.size === reported.length;
  const someSelected = selected.size > 0 && selected.size < reported.length;

  const handleBulkDelete = async () => {
    const ids = selected.size > 0 ? [...selected] : reported.map(r => r.id);
    if (!window.confirm(`${ids.length} Konzept${ids.length !== 1 ? 'e' : ''} endgültig löschen?`)) return;
    setBulkActing(true);
    try {
      await bulkDeleteConcepts(packId, ids);
      toast.success(`${ids.length} Konzept${ids.length !== 1 ? 'e' : ''} gelöscht`);
      setSelected(new Set());
      await load();
    } catch { toast.error('Löschen fehlgeschlagen'); }
    finally { setBulkActing(false); }
  };

  const handleBulkDismiss = async () => {
    const ids = selected.size > 0 ? [...selected] : reported.map(r => r.id);
    setBulkActing(true);
    try {
      await bulkDismissReports(packId, ids);
      toast.success(`${ids.length} Meldung${ids.length !== 1 ? 'en' : ''} verworfen`);
      setSelected(new Set());
      await load();
    } catch { toast.error('Dismiss fehlgeschlagen'); }
    finally { setBulkActing(false); }
  };

  const handleSingleDelete = async (id) => {
    await bulkDeleteConcepts(packId, [id]);
    toast.success('Konzept gelöscht');
    setSelected(prev => { const next = new Set(prev); next.delete(id); return next; });
    await load();
  };

  const handleSingleDismiss = async (id) => {
    await bulkDismissReports(packId, [id]);
    toast.success('Meldung verworfen');
    setSelected(prev => { const next = new Set(prev); next.delete(id); return next; });
    await load();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={24} className="animate-spin text-brand-primary" />
      </div>
    );
  }

  if (reported.length === 0) {
    return (
      <div className="glass-card p-12 text-center" data-testid="no-reported-concepts">
        <CheckCircle size={36} className="mx-auto mb-4 text-risk-low opacity-60" />
        <h3 className="font-heading text-lg font-semibold text-text-secondary mb-1">Keine gemeldeten Konzepte</h3>
        <p className="text-sm text-text-muted">Sobald Nutzer Konzepte als irrelevant melden, erscheinen sie hier.</p>
      </div>
    );
  }

  const actionTarget = selected.size > 0 ? `${selected.size} ausgewählt` : `Alle ${reported.length}`;

  return (
    <div data-testid="reported-concepts-tab">
      {/* Toolbar */}
      <div className="glass-card p-3 mb-4 flex items-center gap-3 flex-wrap">
        {/* Select all toggle */}
        <button
          data-testid="select-all-reported"
          onClick={allSelected ? selectNone : selectAll}
          className="flex items-center gap-2 text-xs font-mono text-text-secondary hover:text-text-primary transition-colors"
        >
          {allSelected
            ? <CheckSquare size={14} className="text-risk-high" />
            : someSelected
              ? <Minus size={14} className="text-text-muted" />
              : <Square size={14} />}
          {allSelected ? 'Auswahl aufheben' : 'Alle auswählen'}
        </button>

        <div className="h-4 w-px bg-white/10" />

        {/* Info */}
        <span className="text-xs font-mono text-text-muted">
          {selected.size > 0
            ? <><span className="text-risk-high font-semibold">{selected.size}</span> ausgewählt</>
            : <>{reported.length} gemeldete Konzept{reported.length !== 1 ? 'e' : ''}</>}
        </span>

        <div className="ml-auto flex items-center gap-2">
          <button
            data-testid="bulk-dismiss-btn"
            onClick={handleBulkDismiss}
            disabled={bulkActing}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono border border-brand-primary/30 text-brand-primary hover:bg-brand-primary/10 rounded transition-all disabled:opacity-40"
          >
            {bulkActing ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
            {actionTarget} · Dismiss
          </button>
          <button
            data-testid="bulk-delete-btn"
            onClick={handleBulkDelete}
            disabled={bulkActing}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono border border-risk-high/30 text-risk-high hover:bg-risk-high/10 rounded transition-all disabled:opacity-40"
          >
            {bulkActing ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
            {actionTarget} · Löschen
          </button>
        </div>
      </div>

      {/* List */}
      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {reported.map((c) => (
            <ReportedConceptRow
              key={c.id}
              concept={c}
              selected={selected.has(c.id)}
              onToggle={toggleSelect}
              onDelete={handleSingleDelete}
              onDismiss={handleSingleDismiss}
            />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ─── Session modal ────────────────────────────────────────────────────────────
function StartSessionModal({ packId, concepts, onClose, onStart }) {
  const [duration, setDuration] = useState(10);
  const [docTypeFilter, setDocTypeFilter] = useState(null);
  const [loading, setLoading] = useState(false);

  const availableTypes = [...new Set(concepts.map(c => c.doc_type).filter(Boolean))].sort();
  const filteredCount = docTypeFilter ? concepts.filter(c => c.doc_type === docTypeFilter).length : concepts.length;

  const handleStart = async () => {
    setLoading(true);
    try {
      const res = await startSession(packId, duration, docTypeFilter);
      onStart(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Starten der Session');
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
        className="glass-card w-full max-w-sm p-6" data-testid="start-session-modal">
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-heading text-lg font-semibold">Session starten</h3>
          <button onClick={onClose} className="text-text-secondary hover:text-white" data-testid="close-session-modal"><X size={18} /></button>
        </div>

        {availableTypes.length > 1 && (
          <div className="mb-5">
            <div className="flex items-center gap-1.5 mb-2">
              <Filter size={11} className="text-text-muted" />
              <span className="text-xs font-mono text-text-muted uppercase tracking-widest">Quelle filtern</span>
            </div>
            <div className="flex flex-wrap gap-1.5" data-testid="doc-type-filter-group">
              <button data-testid="filter-all" onClick={() => setDocTypeFilter(null)}
                className={`text-xs font-mono px-2.5 py-1.5 rounded-md border transition-all ${docTypeFilter === null ? 'border-brand-primary bg-brand-primary/10 text-brand-primary' : 'border-white/10 text-text-secondary hover:border-white/20'}`}>
                Alle ({concepts.length})
              </button>
              {availableTypes.map(type => {
                const count = concepts.filter(c => c.doc_type === type).length;
                const cfg = DOC_TYPE_COLORS[type] || DOC_TYPE_COLORS['Sonstiges'];
                const isActive = docTypeFilter === type;
                return (
                  <button key={type}
                    data-testid={`filter-${type.toLowerCase().replace(/\s+/g, '-').replace(/ü/g, 'ue')}`}
                    onClick={() => setDocTypeFilter(isActive ? null : type)}
                    className="text-xs font-mono px-2.5 py-1.5 rounded-md border transition-all"
                    style={isActive ? { borderColor: cfg.color, background: cfg.bg, color: cfg.color } : { borderColor: 'rgba(255,255,255,0.1)', color: 'var(--color-text-secondary)' }}>
                    {type} ({count})
                  </button>
                );
              })}
            </div>
            {docTypeFilter && <p className="text-xs font-mono text-text-muted mt-2">{filteredCount} Konzepte aus dieser Quelle</p>}
          </div>
        )}

        <div className="space-y-2 mb-6">
          <div className="flex items-center gap-1.5 mb-2">
            <span className="text-xs font-mono text-text-muted uppercase tracking-widest">Dauer</span>
          </div>
          {[{ mins: 10, label: '10 Min', sublabel: '~8 Konzepte' }, { mins: 20, label: '20 Min', sublabel: '~15 Konzepte' }, { mins: 30, label: '30 Min', sublabel: '~22 Konzepte' }].map(({ mins, label, sublabel }) => (
            <button key={mins} data-testid={`duration-${mins}`} onClick={() => setDuration(mins)}
              className={`w-full flex items-center justify-between p-3 rounded-md border transition-all ${duration === mins ? 'border-brand-primary bg-brand-primary/10 text-brand-primary' : 'border-white/10 text-text-secondary hover:border-white/20'}`}>
              <span className="font-mono text-sm">{label}</span>
              <span className="text-xs">{sublabel}</span>
            </button>
          ))}
        </div>

        <button data-testid="confirm-start-session-btn" onClick={handleStart} disabled={loading} className="btn-primary w-full justify-center">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          {loading ? 'Laden...' : `SESSION STARTEN${docTypeFilter ? ` · ${docTypeFilter}` : ''}`}
        </button>
      </motion.div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function StudyPackDetail() {
  const { packId } = useParams();
  const navigate = useNavigate();
  const [pack, setPack] = useState(null);
  const [concepts, setConcepts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showSessionModal, setShowSessionModal] = useState(false);
  const [activeTab, setActiveTab] = useState('concepts'); // 'concepts' | 'reported'
  const [reportedCount, setReportedCount] = useState(0);

  const fetchData = useCallback(async () => {
    try {
      const [packRes, conceptsRes] = await Promise.all([getPack(packId), listConcepts(packId)]);
      setPack(packRes.data);
      setConcepts(conceptsRes.data);
    } catch {
      toast.error('Failed to load pack');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  }, [packId, navigate]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const onConceptUpdate = (updated) => setConcepts(prev => prev.map(c => c.id === updated.id ? { ...c, ...updated } : c));
  const onConceptDelete = (id) => setConcepts(prev => prev.filter(c => c.id !== id));
  const onSessionStart = (sessionData) => navigate(`/session/${sessionData.session_id}`, {
    state: { currentItem: sessionData.current_item, total: sessionData.total, packTitle: pack?.title },
  });

  if (loading) {
    return <div className="min-h-screen bg-bg-primary flex items-center justify-center"><Loader2 size={24} className="animate-spin text-brand-primary" /></div>;
  }

  return (
    <div className="min-h-screen bg-bg-primary" data-testid="pack-detail-page">
      <Navbar />
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">

        {/* Header */}
        <div className="flex items-start justify-between mb-6 gap-4">
          <div className="flex items-start gap-4">
            <button data-testid="back-to-dashboard" onClick={() => navigate('/dashboard')}
              className="mt-1 text-text-secondary hover:text-text-primary transition-colors">
              <ArrowLeft size={18} />
            </button>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-mono text-text-muted uppercase tracking-widest">{pack?.domain || 'General'}</span>
              </div>
              <h1 className="font-heading text-2xl font-bold text-text-primary">{pack?.title}</h1>
              {pack?.description && <p className="text-sm text-text-secondary mt-1">{pack.description}</p>}
              <p className="text-xs font-mono text-text-muted mt-1">{concepts.length} Konzepte</p>
            </div>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <button data-testid="upload-material-btn" onClick={() => navigate(`/packs/${packId}/upload`)} className="btn-secondary">
              <Upload size={14} /> Upload
            </button>
            <button data-testid="start-session-btn" onClick={() => setShowSessionModal(true)}
              disabled={concepts.length === 0} className="btn-primary">
              <Play size={14} /> Study
            </button>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex items-center gap-1 mb-5 border-b border-white/5">
          <button
            data-testid="tab-concepts"
            onClick={() => setActiveTab('concepts')}
            className={`px-4 py-2.5 text-xs font-mono font-semibold rounded-t-md transition-all border-b-2 -mb-px ${
              activeTab === 'concepts'
                ? 'border-brand-primary text-brand-primary bg-brand-primary/5'
                : 'border-transparent text-text-muted hover:text-text-secondary'
            }`}
          >
            KONZEPTE ({concepts.length})
          </button>
          <button
            data-testid="tab-reported"
            onClick={() => setActiveTab('reported')}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-mono font-semibold rounded-t-md transition-all border-b-2 -mb-px ${
              activeTab === 'reported'
                ? 'border-risk-high text-risk-high bg-risk-high/5'
                : 'border-transparent text-text-muted hover:text-text-secondary'
            }`}
          >
            <Flag size={11} />
            GEMELDET
            {reportedCount > 0 && (
              <span className="bg-risk-high text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full leading-none">
                {reportedCount}
              </span>
            )}
          </button>
        </div>

        {/* Tab content */}
        <AnimatePresence mode="wait">
          {activeTab === 'concepts' ? (
            <motion.div key="concepts" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              {concepts.length === 0 ? (
                <div className="glass-card p-12 text-center">
                  <BookOpen size={40} className="mx-auto mb-4 text-text-muted opacity-40" />
                  <h3 className="font-heading text-lg font-semibold text-text-secondary mb-2">Noch keine Konzepte</h3>
                  <p className="text-sm text-text-muted mb-5">Material hochladen, um Konzepte automatisch zu extrahieren</p>
                  <button data-testid="upload-first-material-btn" onClick={() => navigate(`/packs/${packId}/upload`)} className="btn-primary">
                    <Upload size={14} /> Upload Material
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {concepts.map(c => (
                    <ConceptCard key={c.id} concept={c} onUpdate={onConceptUpdate} onDelete={onConceptDelete} />
                  ))}
                </div>
              )}
            </motion.div>
          ) : (
            <motion.div key="reported" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <ReportedTab packId={packId} onCountChange={setReportedCount} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {showSessionModal && (
        <StartSessionModal packId={packId} concepts={concepts} onClose={() => setShowSessionModal(false)} onStart={onSessionStart} />
      )}
    </div>
  );
}
