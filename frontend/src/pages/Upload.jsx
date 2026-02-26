import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import {
  ArrowLeft, Upload as UploadIcon, FileText, X, Check,
  Loader2, AlertTriangle, ChevronRight, Trash2, BookOpen, Clock
} from 'lucide-react';
import Navbar from '../components/Navbar';
import { uploadMaterial, getJobStatus, deleteConcept } from '../services/api';

function ConceptPreviewCard({ concept, onDelete }) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteConcept(concept.id);
      onDelete(concept.id);
    } catch {
      toast.error('Failed to remove concept');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 10 }}
      className="glass-card p-4 group"
      data-testid={`preview-concept-${concept.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h4 className="font-heading text-sm font-semibold text-text-primary mb-1">{concept.title}</h4>
          <p className="text-xs text-text-secondary leading-relaxed">{concept.short_definition}</p>
          {concept.common_mistake && (
            <div className="flex items-start gap-1.5 mt-2 text-xs text-risk-high/70">
              <AlertTriangle size={10} className="flex-shrink-0 mt-0.5" />
              <span>{concept.common_mistake}</span>
            </div>
          )}
        </div>
        <button
          data-testid={`remove-preview-concept-${concept.id}`}
          onClick={handleDelete}
          disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1.5 text-text-secondary hover:text-risk-high rounded transition-all flex-shrink-0"
        >
          {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
        </button>
      </div>
    </motion.div>
  );
}

export default function Upload() {
  const { packId } = useParams();
  const navigate = useNavigate();
  const [mode, setMode] = useState('text'); // 'text' | 'file'
  const [text, setText] = useState('');
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null); // 'queued' | 'processing' | 'complete' | 'failed'
  const [result, setResult] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const fileInputRef = useRef(null);
  const pollRef = useRef(null);
  const elapsedRef = useRef(null);

  // Polling logic
  const startPolling = useCallback((jid) => {
    setElapsed(0);
    elapsedRef.current = setInterval(() => setElapsed((e) => e + 1), 1000);

    pollRef.current = setInterval(async () => {
      try {
        const res = await getJobStatus(jid);
        const job = res.data;
        setJobStatus(job.status);

        if (job.status === 'complete') {
          clearInterval(pollRef.current);
          clearInterval(elapsedRef.current);
          setResult(job);
          setLoading(false);
          toast.success(`Extracted ${job.concepts_extracted} concepts!`);
        } else if (job.status === 'failed') {
          clearInterval(pollRef.current);
          clearInterval(elapsedRef.current);
          setLoading(false);
          setJobId(null);
          setJobStatus(null);
          toast.error(job.error || 'Processing failed. Try different content.');
        }
      } catch {
        // Polling error - keep trying
      }
    }, 4000); // Poll every 4s
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (elapsedRef.current) clearInterval(elapsedRef.current);
    };
  }, []);

  const handleProcess = async () => {
    if (mode === 'text' && !text.trim()) {
      toast.error('Please paste some study material');
      return;
    }
    if (mode === 'file' && !file) {
      toast.error('Please select a file');
      return;
    }

    setLoading(true);
    setJobId(null);
    setJobStatus(null);

    try {
      const formData = new FormData();
      if (mode === 'file') {
        formData.append('file', file);
      } else {
        formData.append('text', text);
      }

      const res = await uploadMaterial(packId, formData);
      const jid = res.data.job_id;
      setJobId(jid);
      setJobStatus('queued');
      toast.info('Material queued — AI is extracting concepts...');
      startPolling(jid);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Upload failed.';
      toast.error(msg);
      setLoading(false);
    }
  };

  const onConceptDelete = (id) => {
    setResult((prev) => ({
      ...prev,
      concepts: prev.concepts.filter((c) => c.id !== id),
    }));
  };

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    if (f) {
      if (f.size > 10 * 1024 * 1024) {
        toast.error('File too large (max 10MB)');
        return;
      }
      setFile(f);
    }
  };

  return (
    <div className="min-h-screen bg-bg-primary" data-testid="upload-page">
      <Navbar />
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <button
            data-testid="back-to-pack"
            onClick={() => navigate(`/packs/${packId}`)}
            className="text-text-secondary hover:text-text-primary transition-colors"
          >
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="font-heading text-2xl font-bold text-text-primary">Upload Material</h1>
            <p className="text-sm text-text-secondary mt-0.5">
              AI will extract concepts and generate knowledge checks
            </p>
          </div>
        </div>

        {!result ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
            {/* Mode selector */}
            <div className="flex border border-white/10 rounded-md p-1 bg-black/20">
              <button
                data-testid="mode-text"
                onClick={() => setMode('text')}
                className={`flex-1 flex items-center justify-center gap-2 py-2 text-sm font-mono rounded transition-all ${
                  mode === 'text'
                    ? 'bg-brand-primary text-black font-bold'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                <FileText size={14} />
                Paste Text
              </button>
              <button
                data-testid="mode-file"
                onClick={() => setMode('file')}
                className={`flex-1 flex items-center justify-center gap-2 py-2 text-sm font-mono rounded transition-all ${
                  mode === 'file'
                    ? 'bg-brand-primary text-black font-bold'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                <UploadIcon size={14} />
                Upload PDF
              </button>
            </div>

            {mode === 'text' ? (
              <div>
                <label className="block text-xs font-mono text-text-muted uppercase tracking-widest mb-2">
                  Study Material
                </label>
                <textarea
                  data-testid="text-input"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Paste your lecture notes, textbook excerpts, or any study material here..."
                  className="terminal-input resize-none h-64 text-sm"
                />
                <p className="text-xs text-text-muted font-mono mt-1">
                  {text.split(/\s+/).filter(Boolean).length} words
                  {' · '}
                  Recommended: 300-3000 words per upload
                </p>
              </div>
            ) : (
              <div>
                <label className="block text-xs font-mono text-text-muted uppercase tracking-widest mb-2">
                  PDF File
                </label>
                <div
                  data-testid="file-drop-area"
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors ${
                    file
                      ? 'border-brand-primary/50 bg-brand-primary/5'
                      : 'border-white/10 hover:border-white/20 bg-black/20'
                  }`}
                >
                  {file ? (
                    <div className="flex items-center justify-center gap-3">
                      <FileText size={20} className="text-brand-primary" />
                      <div className="text-left">
                        <div className="text-sm font-mono text-text-primary">{file.name}</div>
                        <div className="text-xs text-text-muted">
                          {(file.size / 1024).toFixed(1)} KB
                        </div>
                      </div>
                      <button
                        onClick={(e) => { e.stopPropagation(); setFile(null); }}
                        className="ml-2 text-text-secondary hover:text-risk-high"
                        data-testid="clear-file-btn"
                      >
                        <X size={16} />
                      </button>
                    </div>
                  ) : (
                    <>
                      <UploadIcon size={28} className="mx-auto mb-3 text-text-muted opacity-50" />
                      <p className="text-sm text-text-secondary mb-1">Click to select PDF</p>
                      <p className="text-xs text-text-muted font-mono">Max 10MB · PDF only</p>
                    </>
                  )}
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.txt"
                  onChange={handleFileChange}
                  className="hidden"
                  data-testid="file-input"
                />
              </div>
            )}

            {/* RAG info */}
            <div className="flex items-start gap-3 p-3 rounded-md bg-brand-primary/5 border border-brand-primary/15">
              <BookOpen size={14} className="text-brand-primary flex-shrink-0 mt-0.5" />
              <p className="text-xs text-text-secondary">
                Concepts are extracted <em>only</em> from your material — no external knowledge used.
                If information is insufficient, it will be skipped rather than hallucinated.
              </p>
            </div>

            <button
              data-testid="process-upload-btn"
              onClick={handleProcess}
              disabled={loading}
              className="btn-primary w-full justify-center"
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  {jobStatus === 'queued' ? 'Queued...' : `Processing... ${elapsed}s`}
                </>
              ) : (
                <>
                  <UploadIcon size={14} />
                  Extract Concepts
                </>
              )}
            </button>

            {loading && (
              <div className="text-center">
                <div className="flex items-center justify-center gap-2 text-xs text-text-muted font-mono">
                  <Clock size={11} />
                  <span>AI is reading your material — typically 30–90 seconds</span>
                </div>
                <div className="mt-2 flex justify-center gap-1">
                  {['Chunking text', 'Extracting concepts', 'Generating checks', 'Quality filtering'].map((step, i) => (
                    <span
                      key={step}
                      className={`text-xs px-2 py-0.5 rounded font-mono ${
                        elapsed > i * 15
                          ? 'text-brand-primary bg-brand-primary/10'
                          : 'text-text-muted bg-white/5'
                      }`}
                    >
                      {step}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        ) : (
          /* Result preview */
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">
            {/* Stats bar */}
            <div className="glass-card p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Check size={16} className="text-risk-low" />
                <div>
                  <div className="text-sm font-medium text-text-primary">
                    {result.concepts?.length || 0} concepts extracted
                  </div>
                  <div className="text-xs text-text-muted font-mono">
                    From {result.chunks_processed} text chunks
                  </div>
                </div>
              </div>
              <button
                data-testid="upload-more-btn"
                onClick={() => setResult(null)}
                className="btn-secondary text-xs py-1.5"
              >
                Upload More
              </button>
            </div>

            {/* ── Post-Upload Risk Summary ── */}
            {result.risk_summary?.length > 0 && (
              <div className="glass-card p-5 border border-risk-high/15" data-testid="risk-summary-panel">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle size={13} className="text-risk-high" />
                  <span className="text-xs font-mono text-text-muted uppercase tracking-widest">
                    Top Detected Risks
                  </span>
                  <span className="text-xs text-text-muted ml-auto font-mono">
                    from your material
                  </span>
                </div>
                <div className="space-y-3">
                  {result.risk_summary.map((item, i) => (
                    <div
                      key={i}
                      className="border-l-2 border-risk-high/30 pl-3"
                      data-testid={`risk-summary-item-${i}`}
                    >
                      <div className="text-xs font-mono font-semibold text-text-primary mb-0.5">
                        {item.concept}
                      </div>
                      <div className="text-xs text-risk-high/70 leading-snug">
                        {item.misconception}
                      </div>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-text-muted font-mono mt-3 border-t border-white/5 pt-3">
                  These are the most common misconceptions identified in your material.
                  Focus on these first during your session.
                </p>
              </div>
            )}

            {/* Concept review list */}
            <div className="space-y-2">
              <p className="text-xs font-mono text-text-muted uppercase tracking-widest">
                Review Concepts ({result.concepts?.length || 0})
              </p>
              <AnimatePresence>
                {result.concepts?.map((c) => (
                  <ConceptPreviewCard key={c.id} concept={c} onDelete={onConceptDelete} />
                ))}
              </AnimatePresence>
              {(!result.concepts || result.concepts.length === 0) && (
                <p className="text-center text-sm text-text-muted py-8">All concepts removed</p>
              )}
            </div>

            <button
              data-testid="go-to-pack-btn"
              onClick={() => navigate(`/packs/${packId}`)}
              className="btn-primary w-full justify-center"
            >
              <ChevronRight size={14} />
              Go to Study Pack
            </button>
          </motion.div>
        )}
      </div>
    </div>
  );
}
