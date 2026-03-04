import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import {
  ArrowLeft, Upload as UploadIcon, FileText, Link, X, Check,
  Loader2, AlertTriangle, ChevronRight, Trash2, BookOpen, Clock,
  Plus, Tag
} from 'lucide-react';
import Navbar from '../components/Navbar';
import { uploadMaterial, getJobStatus, deleteConcept, uploadChunk, finalizeUpload, uploadFromUrl, streamJobProgress } from '../services/api';

// ─── Helpers ─────────────────────────────────────────────────────────────────
function arrayBufferToBase64(buffer) {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

const CHUNK_SIZE = 200 * 1024; // 200KB

// Doc type badge colours
const DOC_TYPE_COLORS = {
  'Theoriebuch':       { color: '#2F81F7', bg: 'rgba(47,129,247,0.12)' },
  'Theorie & Aufgaben':{ color: '#00E5FF', bg: 'rgba(0,229,255,0.1)' },
  'Abschlussprüfung':  { color: '#FF2D55', bg: 'rgba(255,45,85,0.1)' },
  'Übungstest':        { color: '#FFCC00', bg: 'rgba(255,204,0,0.1)' },
  'Zusammenfassung':   { color: '#00C853', bg: 'rgba(0,200,83,0.1)' },
  'Skript':            { color: '#8B5CF6', bg: 'rgba(139,92,246,0.1)' },
  'Webseite':          { color: '#00E5FF', bg: 'rgba(0,229,255,0.1)' },
  'Sonstiges':         { color: '#8B949E', bg: 'rgba(139,148,158,0.1)' },
};

function DocTypeBadge({ type }) {
  if (!type) return null;
  const cfg = DOC_TYPE_COLORS[type] || DOC_TYPE_COLORS['Sonstiges'];
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-mono px-2 py-0.5 rounded border"
      style={{ color: cfg.color, background: cfg.bg, borderColor: `${cfg.color}40` }}
      data-testid="doc-type-badge"
    >
      <Tag size={9} />
      {type}
    </span>
  );
}

// ─── Concept preview card ─────────────────────────────────────────────────────
function ConceptPreviewCard({ concept, onDelete }) {
  const [deleting, setDeleting] = useState(false);
  const handleDelete = async () => {
    setDeleting(true);
    try { await deleteConcept(concept.id); onDelete(concept.id); }
    catch { toast.error('Failed to remove concept'); }
    finally { setDeleting(false); }
  };
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }}
      className="glass-card p-4 group" data-testid={`preview-concept-${concept.id}`}
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
          onClick={handleDelete} disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1.5 text-text-secondary hover:text-risk-high rounded transition-all flex-shrink-0"
        >
          {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
        </button>
      </div>
    </motion.div>
  );
}

// ─── Single job tracker — SSE-powered real-time progress ─────────────────────
function JobTracker({ jobId, label, onComplete }) {
  const [status, setStatus] = useState('queued');
  const [chunksProcessed, setChunksProcessed] = useState(0);
  const [chunksTotal, setChunksTotal] = useState(0);
  const [concepts, setConcepts] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [docType, setDocType] = useState('');
  const timerRef = useRef(null);
  const esRef = useRef(null);

  useEffect(() => {
    timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000);

    esRef.current = streamJobProgress(
      jobId,
      (data) => {
        if (data.status) setStatus(data.status);
        if (data.chunks_processed !== undefined) setChunksProcessed(data.chunks_processed);
        if (data.chunks_total) setChunksTotal(data.chunks_total);
        if (data.concepts_extracted !== undefined) setConcepts(data.concepts_extracted);
        if (data.doc_type) setDocType(data.doc_type);
      },
      (finalData) => {
        clearInterval(timerRef.current);
        // Fallback to polling for final job data with concepts array
        getJobStatus(jobId).then(res => onComplete(res.data)).catch(() => onComplete(finalData));
      }
    );

    return () => {
      clearInterval(timerRef.current);
      if (esRef.current) esRef.current.close();
    };
  }, [jobId]);

  const isRunning = status === 'queued' || status === 'processing';
  const pct = chunksTotal > 0 ? Math.round((chunksProcessed / chunksTotal) * 100) : 0;

  // Estimate remaining time: ~45s per chunk with Haiku (vs ~76s before)
  const avgSecsPerChunk = 45;
  const remainingChunks = chunksTotal > 0 ? chunksTotal - chunksProcessed : 0;
  const estMinutes = Math.ceil((remainingChunks * avgSecsPerChunk) / 60);

  return (
    <div className="glass-card p-4 border border-white/5 space-y-3" data-testid={`job-tracker-${jobId}`}>
      {/* Header row */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          {isRunning
            ? <Loader2 size={12} className="animate-spin text-brand-primary flex-shrink-0" />
            : status === 'complete'
            ? <Check size={12} className="text-risk-low flex-shrink-0" />
            : <AlertTriangle size={12} className="text-risk-high flex-shrink-0" />}
          <span className="text-xs font-mono text-text-secondary truncate">{label}</span>
          {docType && <DocTypeBadge type={docType} />}
        </div>
        <div className="flex items-center gap-3 flex-shrink-0 text-xs font-mono">
          {concepts > 0 && (
            <span className="text-brand-primary">{concepts} Konzepte</span>
          )}
          {isRunning && elapsed > 0 && (
            <span className="text-text-muted">{elapsed}s</span>
          )}
        </div>
      </div>

      {/* Progress bar + chunk status */}
      {isRunning && (
        <div className="space-y-1.5">
          {chunksTotal > 0 ? (
            <>
              <div className="flex justify-between text-[10px] font-mono text-text-muted">
                <span>
                  {chunksProcessed === 0
                    ? 'Starte Verarbeitung...'
                    : `Kapitel ${chunksProcessed}/${chunksTotal} verarbeitet`}
                </span>
                <span>
                  {remainingChunks > 0 && estMinutes > 0
                    ? `~${estMinutes} Min verbleibend`
                    : chunksProcessed > 0 ? 'Fast fertig...' : ''}
                </span>
              </div>
              <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-brand-primary rounded-full"
                  animate={{ width: `${Math.max(pct, 3)}%` }}
                  transition={{ duration: 0.5, ease: 'easeOut' }}
                />
              </div>
            </>
          ) : (
            <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-brand-primary rounded-full"
                animate={{ width: ['5%', '60%', '5%'] }}
                transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
              />
            </div>
          )}
        </div>
      )}

      {/* "You can close the app" hint after first chunk */}
      {isRunning && chunksProcessed >= 1 && (
        <p className="text-[10px] font-mono text-text-muted">
          Du kannst die App schliessen — die Verarbeitung läuft im Hintergrund weiter.
        </p>
      )}
    </div>
  );
}

// ─── Main Upload Page ─────────────────────────────────────────────────────────
export default function Upload() {
  const { packId } = useParams();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const extraFilesRef = useRef(null);

  const [mode, setMode] = useState('pdf'); // 'pdf' | 'text' | 'url'
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  const [primaryFile, setPrimaryFile] = useState(null);
  const [extraFiles, setExtraFiles] = useState([]); // additional PDFs

  // Upload state
  const [uploadProgress, setUploadProgress] = useState(null); // {file, chunk, total}
  const [activeJobs, setActiveJobs] = useState([]); // [{jobId, label}]
  const [completedJobs, setCompletedJobs] = useState([]); // job results
  const [loading, setLoading] = useState(false);

  // Result shown after all jobs done
  const [allConcepts, setAllConcepts] = useState(null);

  const pendingRef = useRef(0);

  const handleJobComplete = useCallback((job) => {
    pendingRef.current -= 1;
    if (job) {
      setCompletedJobs(prev => [...prev, job]);
    }
    if (pendingRef.current === 0) {
      setLoading(false);
      setActiveJobs(prev => {
        // Collect all concepts from all completed jobs
        setCompletedJobs(done => {
          const allC = done.flatMap(j => j.concepts || []);
          setAllConcepts(allC);
          const total = done.reduce((s, j) => s + (j.concepts_extracted || 0), 0);
          toast.success(`${total} Konzepte extrahiert!`);
          return done;
        });
        return prev;
      });
    }
  }, []);

  // ── Chunked PDF upload for one file ──────────────────────────────────────
  const uploadPdfChunked = async (file, packId) => {
    const uploadId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const total = Math.ceil(file.size / CHUNK_SIZE);

    for (let i = 0; i < total; i++) {
      const start = i * CHUNK_SIZE;
      const ab = await file.slice(start, Math.min(start + CHUNK_SIZE, file.size)).arrayBuffer();
      await uploadChunk({ upload_id: uploadId, chunk_index: i, total_chunks: total, data: arrayBufferToBase64(ab) });
      setUploadProgress({ file: file.name, chunk: i + 1, total });
    }
    setUploadProgress(null);
    const res = await finalizeUpload({ upload_id: uploadId, pack_id: packId, filename: file.name });
    return res.data.job_id;
  };

  const handleProcess = async () => {
    if (mode === 'text' && !text.trim()) { toast.error('Bitte Text einfügen'); return; }
    if (mode === 'url' && !url.trim()) { toast.error('Bitte URL eingeben'); return; }
    if (mode === 'pdf' && !primaryFile) { toast.error('Bitte PDF auswählen'); return; }

    setLoading(true);
    setActiveJobs([]);
    setCompletedJobs([]);
    setAllConcepts(null);

    const filesToProcess = mode === 'pdf'
      ? [primaryFile, ...extraFiles]
      : [];

    try {
      const newJobs = [];

      if (mode === 'pdf') {
        pendingRef.current = filesToProcess.length;
        for (const file of filesToProcess) {
          // Upload one at a time to avoid overwhelming server
          const jid = await uploadPdfChunked(file, packId);
          const label = file.name;
          newJobs.push({ jobId: jid, label });
        }
      } else if (mode === 'text') {
        pendingRef.current = 1;
        const formData = new FormData();
        formData.append('text', text);
        const res = await uploadMaterial(packId, formData);
        newJobs.push({ jobId: res.data.job_id, label: 'Text' });
      } else if (mode === 'url') {
        pendingRef.current = 1;
        const res = await uploadFromUrl(packId, url);
        newJobs.push({ jobId: res.data.job_id, label: url });
      }

      setActiveJobs(newJobs);
      toast.info(`${newJobs.length > 1 ? newJobs.length + ' Dateien' : 'Material'} hochgeladen — KI verarbeitet...`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload fehlgeschlagen.');
      setLoading(false);
      setUploadProgress(null);
    }
  };

  const onConceptDelete = (id) => {
    setAllConcepts(prev => prev.filter(c => c.id !== id));
  };

  const showResult = allConcepts !== null;

  return (
    <div className="min-h-screen bg-bg-primary" data-testid="upload-page">
      <Navbar />
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8">

        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <button data-testid="back-to-pack" onClick={() => navigate(`/packs/${packId}`)}
            className="text-text-secondary hover:text-text-primary transition-colors">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="font-heading text-2xl font-bold text-text-primary">Material hinzufügen</h1>
            <p className="text-sm text-text-secondary mt-0.5">KI extrahiert Konzepte und generiert Prüfungsfragen</p>
          </div>
        </div>

        {/* Active jobs while processing */}
        {activeJobs.length > 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2 mb-6">
            <p className="text-xs font-mono text-text-muted uppercase tracking-widest mb-2">Verarbeitung</p>
            {activeJobs.map(j => (
              <JobTracker key={j.jobId} jobId={j.jobId} label={j.label} onComplete={handleJobComplete} />
            ))}
          </motion.div>
        )}

        {!showResult ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">

            {/* Mode selector */}
            <div className="flex border border-white/10 rounded-md p-1 bg-black/20">
              {[
                { id: 'pdf',  icon: UploadIcon, label: 'PDF hochladen' },
                { id: 'text', icon: FileText,   label: 'Text einfügen' },
                { id: 'url',  icon: Link,        label: 'URL / Link' },
              ].map(({ id, icon: Icon, label }) => (
                <button key={id} data-testid={`mode-${id}`} onClick={() => setMode(id)}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 text-sm font-mono rounded transition-all ${
                    mode === id ? 'bg-brand-primary text-black font-bold' : 'text-text-secondary hover:text-text-primary'
                  }`}>
                  <Icon size={13} />{label}
                </button>
              ))}
            </div>

            {/* PDF mode */}
            {mode === 'pdf' && (
              <div className="space-y-4">
                {/* Primary PDF */}
                <div>
                  <label className="block text-xs font-mono text-text-muted uppercase tracking-widest mb-2">
                    Hauptdokument
                  </label>
                  <div
                    data-testid="file-drop-area"
                    onClick={() => fileInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                      primaryFile ? 'border-brand-primary/50 bg-brand-primary/5' : 'border-white/10 hover:border-white/20 bg-black/20'
                    }`}
                  >
                    {primaryFile ? (
                      <div className="flex items-center justify-center gap-3">
                        <FileText size={18} className="text-brand-primary" />
                        <div className="text-left">
                          <div className="text-sm font-mono text-text-primary">{primaryFile.name}</div>
                          <div className="text-xs text-text-muted">{(primaryFile.size / 1024 / 1024).toFixed(1)} MB</div>
                        </div>
                        <button onClick={e => { e.stopPropagation(); setPrimaryFile(null); }}
                          className="ml-2 text-text-secondary hover:text-risk-high" data-testid="clear-file-btn">
                          <X size={15} />
                        </button>
                      </div>
                    ) : (
                      <>
                        <UploadIcon size={26} className="mx-auto mb-2 text-text-muted opacity-40" />
                        <p className="text-sm text-text-secondary mb-1">PDF auswählen</p>
                        <p className="text-xs text-text-muted font-mono">Beliebige Grösse · Bücher, Skripte, etc.</p>
                      </>
                    )}
                  </div>
                  <input ref={fileInputRef} type="file" accept=".pdf,.txt"
                    onChange={e => e.target.files[0] && setPrimaryFile(e.target.files[0])}
                    className="hidden" data-testid="file-input" />
                </div>

                {/* Extra PDFs (optional) */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-mono text-text-muted uppercase tracking-widest">
                      Weitere PDFs <span className="text-text-muted/50 normal-case">(optional)</span>
                    </label>
                    <button
                      data-testid="add-extra-files-btn"
                      onClick={() => extraFilesRef.current?.click()}
                      className="flex items-center gap-1.5 text-xs font-mono text-brand-primary hover:text-brand-primary/80 transition-colors"
                    >
                      <Plus size={12} /> Hinzufügen
                    </button>
                    <input ref={extraFilesRef} type="file" accept=".pdf" multiple
                      onChange={e => {
                        const files = Array.from(e.target.files);
                        setExtraFiles(prev => [...prev, ...files]);
                        e.target.value = '';
                      }}
                      className="hidden" data-testid="extra-files-input" />
                  </div>

                  {extraFiles.length > 0 && (
                    <div className="space-y-1.5">
                      {extraFiles.map((f, i) => (
                        <div key={i} className="flex items-center gap-2 p-2.5 rounded-md bg-white/5 border border-white/8">
                          <FileText size={12} className="text-text-muted flex-shrink-0" />
                          <span className="text-xs font-mono text-text-secondary flex-1 truncate">{f.name}</span>
                          <span className="text-xs text-text-muted font-mono flex-shrink-0">{(f.size/1024/1024).toFixed(1)}MB</span>
                          <button onClick={() => setExtraFiles(prev => prev.filter((_, j) => j !== i))}
                            className="text-text-secondary hover:text-risk-high flex-shrink-0">
                            <X size={12} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  {extraFiles.length === 0 && (
                    <p className="text-xs text-text-muted font-mono">
                      z.B. Abschlussprüfungen, Übungsblätter — werden als separate Quelle erkannt
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Text mode */}
            {mode === 'text' && (
              <div>
                <label className="block text-xs font-mono text-text-muted uppercase tracking-widest mb-2">
                  Lernmaterial
                </label>
                <textarea
                  data-testid="text-input" value={text}
                  onChange={e => setText(e.target.value)}
                  placeholder="Vorlesungsnotizen, Lehrbuchauszüge oder beliebiges Lernmaterial einfügen..."
                  className="terminal-input resize-none h-56 text-sm"
                />
                <p className="text-xs text-text-muted font-mono mt-1">
                  {text.split(/\s+/).filter(Boolean).length} Wörter
                </p>
              </div>
            )}

            {/* URL mode */}
            {mode === 'url' && (
              <div>
                <label className="block text-xs font-mono text-text-muted uppercase tracking-widest mb-2">
                  URL / Link
                </label>
                <input
                  data-testid="url-input"
                  type="url"
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  placeholder="https://de.wikipedia.org/wiki/..."
                  className="terminal-input text-sm w-full"
                />
                <p className="text-xs text-text-muted font-mono mt-2">
                  Funktioniert mit Wikipedia, Lehrmaterial-Seiten und allen öffentlichen URLs.
                </p>
              </div>
            )}

            {/* RAG info */}
            <div className="flex items-start gap-3 p-3 rounded-md bg-brand-primary/5 border border-brand-primary/15">
              <BookOpen size={13} className="text-brand-primary flex-shrink-0 mt-0.5" />
              <p className="text-xs text-text-secondary">
                Konzepte werden <em>ausschliesslich</em> aus deinem Material extrahiert — kein externes Wissen verwendet.
                Die KI erkennt automatisch den Dokumenttyp (Theoriebuch, Prüfung, etc.).
              </p>
            </div>

            {/* Upload progress bar */}
            {uploadProgress && (
              <div>
                <div className="flex justify-between text-xs font-mono text-text-muted mb-1">
                  <span className="truncate max-w-xs">{uploadProgress.file}</span>
                  <span>{uploadProgress.chunk}/{uploadProgress.total} Teile</span>
                </div>
                <div className="h-1 bg-white/10 rounded-full overflow-hidden">
                  <div className="h-full bg-brand-primary rounded-full transition-all duration-300"
                    style={{ width: `${Math.round((uploadProgress.chunk / uploadProgress.total) * 100)}%` }} />
                </div>
              </div>
            )}

            <button data-testid="process-upload-btn" onClick={handleProcess} disabled={loading}
              className="btn-primary w-full justify-center">
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  {uploadProgress
                    ? `Hochladen ${uploadProgress.chunk}/${uploadProgress.total}...`
                    : 'Wird verarbeitet...'}
                </>
              ) : (
                <>
                  <UploadIcon size={14} />
                  Konzepte extrahieren{(mode === 'pdf' && extraFiles.length > 0) ? ` (${1 + extraFiles.length} PDFs)` : ''}
                </>
              )}
            </button>
          </motion.div>

        ) : (
          /* ── Result view ── */
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">

            {/* Stats bar with doc type badges */}
            <div className="glass-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Check size={16} className="text-risk-low" />
                  <div>
                    <div className="text-sm font-medium text-text-primary">
                      {allConcepts?.length || 0} Konzepte extrahiert
                    </div>
                    <div className="text-xs text-text-muted font-mono">aus {completedJobs.length} Quelle{completedJobs.length !== 1 ? 'n' : ''}</div>
                  </div>
                </div>
                <button data-testid="upload-more-btn" onClick={() => { setAllConcepts(null); setActiveJobs([]); setCompletedJobs([]); setPrimaryFile(null); setExtraFiles([]); setText(''); setUrl(''); }}
                  className="btn-secondary text-xs py-1.5">
                  Weiteres hinzufügen
                </button>
              </div>

              {/* Quality report (shown when available) */}
              {completedJobs[0]?.quality_report && (() => {
                const qr = completedJobs[0].quality_report;
                return (
                  <div className="pt-2 border-t border-white/5 grid grid-cols-3 gap-3" data-testid="quality-report">
                    <div className="text-center">
                      <div className="text-xs font-mono text-brand-primary font-bold">{qr.chunks_total}</div>
                      <div className="text-[10px] font-mono text-text-muted">Chunks</div>
                    </div>
                    <div className="text-center">
                      <div className="text-xs font-mono text-brand-primary font-bold">{qr.avg_concepts_per_chunk}</div>
                      <div className="text-[10px] font-mono text-text-muted">Konzepte/Chunk</div>
                    </div>
                    <div className="text-center">
                      <div className="text-xs font-mono font-bold" style={{ color: qr.duplicates_merged > 0 ? '#00C853' : '#8B949E' }}>
                        {qr.duplicates_merged}
                      </div>
                      <div className="text-[10px] font-mono text-text-muted">Duplikate entfernt</div>
                    </div>
                  </div>
                );
              })()}

              {/* Doc type badges per source */}
              {completedJobs.length > 0 && (
                <div className="flex flex-wrap gap-2 pt-1 border-t border-white/5">
                  {completedJobs.map((j, i) => (
                    <div key={i} className="flex items-center gap-1.5 text-xs text-text-muted font-mono">
                      <span className="truncate max-w-32">{j.source_name || j.pack_id}</span>
                      {j.doc_type && <DocTypeBadge type={j.doc_type} />}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Risk summary */}
            {completedJobs[0]?.risk_summary?.length > 0 && (
              <div className="glass-card p-5 border border-risk-high/15" data-testid="risk-summary-panel">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle size={13} className="text-risk-high" />
                  <span className="text-xs font-mono text-text-muted uppercase tracking-widest">Top erkannte Risiken</span>
                </div>
                <div className="space-y-3">
                  {completedJobs[0].risk_summary.map((item, i) => (
                    <div key={i} className="border-l-2 border-risk-high/30 pl-3" data-testid={`risk-summary-item-${i}`}>
                      <div className="text-xs font-mono font-semibold text-text-primary mb-0.5">{item.concept}</div>
                      <div className="text-xs text-risk-high/70 leading-snug">{item.misconception}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Concepts list */}
            <div className="space-y-2">
              <p className="text-xs font-mono text-text-muted uppercase tracking-widest">
                Konzepte ({allConcepts?.length || 0})
              </p>
              <AnimatePresence>
                {allConcepts?.map(c => (
                  <ConceptPreviewCard key={c.id} concept={c} onDelete={onConceptDelete} />
                ))}
              </AnimatePresence>
              {(!allConcepts || allConcepts.length === 0) && (
                <p className="text-center text-sm text-text-muted py-8">Alle Konzepte entfernt</p>
              )}
            </div>

            <button data-testid="go-to-pack-btn" onClick={() => navigate(`/packs/${packId}`)}
              className="btn-primary w-full justify-center">
              <ChevronRight size={14} /> Zum Lernpaket
            </button>
          </motion.div>
        )}
      </div>
    </div>
  );
}
