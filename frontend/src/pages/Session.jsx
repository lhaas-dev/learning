import React, { useState, useEffect } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import {
  X, ChevronRight, RotateCcw, Zap, CheckCircle2, AlertTriangle,
  Loader2, BookOpen, Brain, TrendingDown, Activity, Swords,
  ChevronDown, ChevronUp, Check, XCircle
} from 'lucide-react';
import { answerSession, getSessionDebrief, startDrillSession, evaluateAnswer } from '../services/api';

// ─── Rating config with new honest labels ────────────────────────────────────
const RATING_CONFIG = {
  again: {
    label: "Didn't know",
    color: '#FF2D55',
    bg: 'rgba(255,45,85,0.1)',
    border: 'rgba(255,45,85,0.3)',
    icon: RotateCcw,
    emphasis: false,
    riskMsg: "Prioritized — this gap causes frequent exam errors.",
  },
  hard: {
    label: 'Partially knew',
    color: '#FFCC00',
    bg: 'rgba(255,204,0,0.12)',
    border: 'rgba(255,204,0,0.35)',
    icon: AlertTriangle,
    emphasis: true, // slight visual emphasis — middle option
    riskMsg: "This concept stays in rotation — key ideas still hazy.",
  },
  good: {
    label: 'Knew it',
    color: '#2F81F7',
    bg: 'rgba(47,129,247,0.12)',
    border: 'rgba(47,129,247,0.35)',
    icon: CheckCircle2,
    emphasis: true, // slight visual emphasis — middle option
    riskMsg: "Solid. Risk reduced — concept deprioritized until it fades.",
  },
  easy: {
    label: 'Instant recall',
    color: '#00C853',
    bg: 'rgba(0,200,83,0.1)',
    border: 'rgba(0,200,83,0.3)',
    icon: Zap,
    emphasis: false,
    riskMsg: "Low risk detected. Interval extended significantly.",
  },
};

// ─── Progress bar ─────────────────────────────────────────────────────────────
function ProgressBar({ current, total }) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  return (
    <div className="w-full">
      <div className="flex justify-between text-xs font-mono text-text-muted mb-1">
        <span>{current}/{total}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-1 bg-white/10 rounded-full overflow-hidden">
        <motion.div
          className="h-full bg-brand-primary rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}

// ─── Check type badge ─────────────────────────────────────────────────────────
function CheckTypeBadge({ type }) {
  const map = {
    recall: { label: 'Recall', color: '#2F81F7' },
    contrast: { label: 'Contrast', color: '#FFCC00' },
    scenario: { label: 'Scenario', color: '#00E5FF' },
    error: { label: 'Error-Spotting', color: '#FF2D55' },
  };
  const cfg = map[type] || { label: type, color: '#8B949E' };
  return (
    <span
      className="text-xs font-mono px-2 py-0.5 rounded border uppercase tracking-widest"
      style={{ color: cfg.color, borderColor: `${cfg.color}30`, background: `${cfg.color}10` }}
    >
      {cfg.label}
    </span>
  );
}

// ─── Evaluation result panel ──────────────────────────────────────────────────
function EvaluationPanel({ evaluation, evaluating }) {
  if (evaluating) {
    return (
      <div
        className="flex items-center gap-2 text-xs text-text-muted font-mono py-2"
        data-testid="evaluation-loading"
      >
        <Loader2 size={12} className="animate-spin text-brand-primary" />
        <span>Analysing your answer...</span>
      </div>
    );
  }
  if (!evaluation) return null;

  const { result, summary, covered_ideas = [], missing_ideas = [], wrong_ideas_stated = [] } = evaluation;

  if (result === 'no_answer' || result === 'no_requirements') {
    return null; // No evaluation to show
  }

  const resultColors = {
    correct: '#00C853',
    partially_correct: '#FFCC00',
    incorrect: '#FF2D55',
  };
  const summaryColor = resultColors[result] || '#8B949E';

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-2"
      data-testid="evaluation-panel"
    >
      {/* Summary sentence */}
      <p
        className="text-xs font-mono font-semibold"
        style={{ color: summaryColor }}
        data-testid="evaluation-summary"
      >
        {summary}
      </p>

      {/* Covered ideas */}
      {covered_ideas.length > 0 && (
        <div className="space-y-1" data-testid="covered-ideas">
          {covered_ideas.map((idea, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <Check size={11} className="text-risk-low flex-shrink-0 mt-0.5" />
              <span className="text-text-secondary">{idea}</span>
            </div>
          ))}
        </div>
      )}

      {/* Missing ideas */}
      {missing_ideas.length > 0 && (
        <div className="space-y-1" data-testid="missing-ideas">
          {missing_ideas.map((idea, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <XCircle size={11} className="text-risk-high flex-shrink-0 mt-0.5" />
              <span className="text-text-secondary">
                <span className="text-risk-high/70">Missing: </span>{idea}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Wrong statements */}
      {wrong_ideas_stated.length > 0 && (
        <div className="space-y-1" data-testid="wrong-statements">
          {wrong_ideas_stated.map((idea, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <XCircle size={11} className="text-risk-high flex-shrink-0 mt-0.5" />
              <span className="text-text-secondary">
                <span className="text-risk-high/70">Incorrect: </span>{idea}
              </span>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

// ─── Session Complete + Debrief ────────────────────────────────────────────────
function SessionComplete({ stats, packTitle, onBack, sessionId, navigate }) {
  const total = Object.values(stats).reduce((a, b) => a + b, 0);
  const good = (stats.good || 0) + (stats.easy || 0);
  const pct = total > 0 ? Math.round((good / total) * 100) : 0;
  const scoreColor = pct >= 70 ? '#00C853' : pct >= 40 ? '#FFCC00' : '#FF2D55';

  const [debrief, setDebrief] = useState(null);
  const [debriefLoading, setDebriefLoading] = useState(true);
  const [drillingLoading, setDrillingLoading] = useState(false);

  useEffect(() => {
    getSessionDebrief(sessionId)
      .then((res) => setDebrief(res.data))
      .catch(() => setDebrief({ top_gaps: [], pattern: null, can_drill: false }))
      .finally(() => setDebriefLoading(false));
  }, [sessionId]);

  const handleStartDrill = async () => {
    if (!debrief?.drill_concept_ids?.length) return;
    setDrillingLoading(true);
    try {
      const res = await startDrillSession(debrief.drill_concept_ids);
      navigate(`/session/${res.data.session_id}`, {
        state: {
          currentItem: res.data.current_item,
          total: res.data.total,
          packTitle: '5-Min Fix Drill',
          isDrill: true,
        },
      });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to start drill');
      setDrillingLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg-primary" data-testid="session-complete-screen">
      <div className="max-w-2xl mx-auto px-4 py-8 space-y-5">

        {/* Score card */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-6">
          <div className="flex items-start justify-between mb-5">
            <div>
              <div className="text-xs font-mono text-text-muted uppercase tracking-widest mb-1">Session Complete</div>
              <div className="font-heading text-xl font-bold text-text-primary">{packTitle}</div>
            </div>
            <div className="text-right">
              <div className="font-heading text-5xl font-bold leading-none" style={{ color: scoreColor }} data-testid="session-score">
                {pct}%
              </div>
              <div className="text-xs text-text-muted font-mono mt-1">correct</div>
            </div>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {Object.entries(RATING_CONFIG).map(([key, cfg]) => {
              const Icon = cfg.icon;
              return (
                <div key={key} data-testid={`stat-${key}`} className="rounded-md p-2.5 border text-center" style={{ background: cfg.bg, borderColor: cfg.border }}>
                  <Icon size={13} className="mx-auto mb-1" style={{ color: cfg.color }} />
                  <div className="font-mono font-bold text-base" style={{ color: cfg.color }}>{stats[key] || 0}</div>
                  <div className="text-xs text-text-muted truncate">{cfg.label}</div>
                </div>
              );
            })}
          </div>
        </motion.div>

        {/* Session Debrief */}
        {debriefLoading ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass-card p-5 flex items-center gap-3" data-testid="debrief-loading">
            <Loader2 size={16} className="animate-spin text-brand-primary flex-shrink-0" />
            <div>
              <div className="text-sm text-text-primary font-medium">Analysing session...</div>
              <div className="text-xs text-text-muted font-mono">Building your debrief</div>
            </div>
          </motion.div>
        ) : (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            {debrief?.top_gaps?.length > 0 ? (
              <div className="space-y-3" data-testid="debrief-gaps-panel">
                <div className="flex items-center gap-2">
                  <TrendingDown size={13} className="text-risk-high" />
                  <span className="text-xs font-mono text-text-muted uppercase tracking-widest">Top Knowledge Risks</span>
                </div>
                {debrief.top_gaps.map((gap, i) => (
                  <div key={i} className="glass-card p-4 border-l-2" style={{ borderLeftColor: i === 0 ? '#FF2D55' : i === 1 ? '#FFCC00' : '#8B949E' }} data-testid={`gap-item-${i}`}>
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <span className="font-heading text-sm font-semibold text-text-primary">{i + 1}. {gap.concept_name}</span>
                      <span className="text-xs font-mono px-1.5 py-0.5 rounded flex-shrink-0" style={{ color: i === 0 ? '#FF2D55' : i === 1 ? '#FFCC00' : '#8B949E', background: i === 0 ? 'rgba(255,45,85,0.1)' : i === 1 ? 'rgba(255,204,0,0.1)' : 'rgba(139,148,158,0.1)' }}>
                        #{i + 1} risk
                      </span>
                    </div>
                    <p className="text-xs text-text-secondary mb-1">{gap.risk_reason}</p>
                    {gap.detected_issue && <p className="text-xs text-text-muted font-mono">Issue: {gap.detected_issue}</p>}
                  </div>
                ))}
                {debrief.pattern && (
                  <div className="glass-card p-4 border border-brand-primary/20 bg-brand-primary/5" data-testid="debrief-pattern">
                    <div className="flex items-center gap-2 mb-1">
                      <Activity size={13} className="text-brand-primary" />
                      <span className="text-xs font-mono text-brand-primary uppercase tracking-widest">Dominant Pattern</span>
                    </div>
                    <p className="text-sm text-text-primary">{debrief.pattern}</p>
                  </div>
                )}
                {debrief.can_drill && (
                  <button data-testid="start-drill-btn" onClick={handleStartDrill} disabled={drillingLoading} className="w-full flex items-center justify-between p-4 rounded-md border border-risk-high/30 bg-risk-high/5 hover:bg-risk-high/10 hover:border-risk-high/50 transition-all group">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-sm bg-risk-high/20 flex items-center justify-center flex-shrink-0">
                        {drillingLoading ? <Loader2 size={14} className="animate-spin text-risk-high" /> : <Swords size={14} className="text-risk-high" />}
                      </div>
                      <div className="text-left">
                        <div className="text-sm font-heading font-semibold text-text-primary group-hover:text-risk-high transition-colors">Run 5-Min Fix Drill</div>
                        <div className="text-xs text-text-muted font-mono">Targets your top {debrief.drill_concept_ids?.length === 1 ? 'gap' : '2 gaps'} · recall + contrast only</div>
                      </div>
                    </div>
                    <ChevronRight size={16} className="text-risk-high/60 group-hover:text-risk-high transition-colors flex-shrink-0" />
                  </button>
                )}
              </div>
            ) : (
              <div className="glass-card p-5 flex items-center gap-4 border border-risk-low/20" data-testid="no-gaps-panel">
                <CheckCircle2 size={20} className="text-risk-low flex-shrink-0" />
                <div>
                  <div className="text-sm font-medium text-text-primary">{debrief?.wrong_count === 0 ? 'Clean session' : 'No dominant gaps'}</div>
                  <div className="text-xs text-text-muted font-mono">{debrief?.wrong_count === 0 ? 'All concepts rated Hard or better' : 'Not enough errors to identify a clear pattern'}</div>
                </div>
              </div>
            )}
          </motion.div>
        )}

        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
          <button data-testid="back-to-pack-btn" onClick={onBack} className="btn-secondary w-full justify-center">
            Back to Dashboard
          </button>
        </motion.div>
      </div>
    </div>
  );
}

// ─── Main Session Page ────────────────────────────────────────────────────────
export default function Session() {
  const { sessionId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  const locationState = location.state || {};
  const [currentItem, setCurrentItem] = useState(locationState.currentItem || null);
  const [total, setTotal] = useState(locationState.total || 0);
  const [position, setPosition] = useState(1);
  const [packTitle] = useState(locationState.packTitle || 'Study Session');

  const [revealed, setRevealed] = useState(false);
  const [userAnswer, setUserAnswer] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Evaluation state
  const [evaluating, setEvaluating] = useState(false);
  const [evaluation, setEvaluation] = useState(null);
  const [explanationOpen, setExplanationOpen] = useState(false);

  // Post-rating risk message
  const [riskMessage, setRiskMessage] = useState(null);
  const [riskRating, setRiskRating] = useState(null); // for color

  // Session complete
  const [sessionComplete, setSessionComplete] = useState(false);
  const [finalStats, setFinalStats] = useState({});

  useEffect(() => {
    if (!currentItem) {
      toast.error('Session data not found');
      navigate('/dashboard');
    }
  }, [currentItem, navigate]);

  const handleReveal = async () => {
    setRevealed(true);
    setExplanationOpen(false);

    // Trigger evaluation if user wrote something
    if (userAnswer.trim() && currentItem?.check?.id) {
      setEvaluating(true);
      try {
        const res = await evaluateAnswer(currentItem.check.id, userAnswer);
        setEvaluation(res.data);
      } catch {
        // Silent failure — evaluation is optional
      } finally {
        setEvaluating(false);
      }
    }
  };

  const handleRate = async (rating) => {
    if (!currentItem) return;

    // Show risk-oriented message first
    const cfg = RATING_CONFIG[rating];
    setRiskMessage(cfg.riskMsg);
    setRiskRating(rating);
    setSubmitting(true);

    try {
      const res = await answerSession({
        session_id: sessionId,
        concept_id: currentItem.concept?.id || '',
        check_id: currentItem.check?.id || '',
        rating,
        user_answer: userAnswer,
      });

      if (res.data.session_complete) {
        setFinalStats(res.data.stats || {});
        setTimeout(() => {
          setSessionComplete(true);
        }, 1400); // Let user read risk message
        return;
      }

      // Advance to next item after message display
      setTimeout(() => {
        const next = res.data.next_item;
        setCurrentItem(next);
        setPosition(next.position);
        setRevealed(false);
        setUserAnswer('');
        setEvaluation(null);
        setEvaluating(false);
        setExplanationOpen(false);
        setRiskMessage(null);
        setRiskRating(null);
        setSubmitting(false);
      }, 1400);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to submit');
      setRiskMessage(null);
      setSubmitting(false);
    }
  };

  if (sessionComplete) {
    return (
      <SessionComplete
        stats={finalStats}
        packTitle={packTitle}
        sessionId={sessionId}
        navigate={navigate}
        onBack={() => navigate('/dashboard')}
      />
    );
  }

  if (!currentItem) return null;

  const concept = currentItem.concept || {};
  const check = currentItem.check || {};

  return (
    <div className="min-h-screen bg-bg-primary flex flex-col" data-testid="session-page">
      {/* Top bar */}
      <div className="border-b border-white/10 bg-bg-secondary/80 sticky top-0 z-40">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2 flex-shrink-0">
            <Brain size={14} className="text-brand-primary" />
            <span className="text-xs font-mono text-text-muted uppercase tracking-widest hidden sm:block">{packTitle}</span>
          </div>
          <div className="flex-1">
            <ProgressBar current={position - 1} total={total} />
          </div>
          <button
            data-testid="exit-session-btn"
            onClick={() => { if (window.confirm('Exit session? Progress so far will be saved.')) navigate('/dashboard'); }}
            className="text-text-secondary hover:text-text-primary flex-shrink-0"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 max-w-3xl w-full mx-auto px-4 py-8">
        <AnimatePresence mode="wait">
          <motion.div
            key={`${check.id}-${revealed}`}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.25 }}
            className="space-y-4"
          >
            {/* Concept info */}
            <div className="glass-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <BookOpen size={13} className="text-brand-primary" />
                <span className="text-xs font-mono text-brand-primary uppercase tracking-widest">{concept.title || 'Concept'}</span>
                {check.type && <CheckTypeBadge type={check.type} />}
              </div>
              {concept.short_definition && (
                <p className="text-sm text-text-secondary leading-relaxed">{concept.short_definition}</p>
              )}
            </div>

            {/* Check question */}
            <div className="glass-card p-5">
              <p className="text-base text-text-primary font-medium leading-relaxed" data-testid="check-question">
                {check.prompt || 'No question available'}
              </p>
            </div>

            {/* Answer input (pre-reveal) */}
            {!revealed && (
              <div className="space-y-3">
                <textarea
                  data-testid="answer-input"
                  value={userAnswer}
                  onChange={(e) => setUserAnswer(e.target.value)}
                  placeholder="Write your answer here (optional) — then reveal"
                  className="terminal-input resize-none h-24 text-sm w-full"
                />
                <button data-testid="reveal-answer-btn" onClick={handleReveal} className="btn-primary w-full justify-center">
                  <ChevronRight size={14} />
                  Reveal Answer
                </button>
              </div>
            )}

            {/* Revealed section */}
            {revealed && (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">

                {/* Core answer — prominent, single sentence */}
                <div className="glass-card p-5 border border-risk-low/20" data-testid="correct-answer-panel">
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle2 size={13} className="text-risk-low" />
                    <span className="text-xs font-mono text-risk-low uppercase tracking-widest">Core Answer</span>
                  </div>
                  <p className="text-text-primary text-sm font-medium leading-relaxed" data-testid="correct-answer-text">
                    {check.expected_answer || 'No expected answer defined'}
                  </p>

                  {/* Collapsible explanation */}
                  {check.explanation && (
                    <div className="mt-3 border-t border-white/5 pt-3">
                      <button
                        data-testid="toggle-explanation-btn"
                        onClick={() => setExplanationOpen(!explanationOpen)}
                        className="flex items-center gap-1.5 text-xs font-mono text-text-muted hover:text-text-secondary transition-colors"
                      >
                        {explanationOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                        {explanationOpen ? 'Hide explanation' : 'Show explanation'}
                      </button>
                      {explanationOpen && (
                        <motion.p
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          className="text-xs text-text-secondary mt-2 leading-relaxed"
                          data-testid="explanation-text"
                        >
                          {check.explanation}
                        </motion.p>
                      )}
                    </div>
                  )}
                </div>

                {/* Evaluation: covered / missing / wrong */}
                {(evaluating || evaluation) && (
                  <div className="glass-card p-4 border border-white/5">
                    <EvaluationPanel evaluation={evaluation} evaluating={evaluating} />
                  </div>
                )}

                {/* User's written answer (if any) */}
                {userAnswer.trim() && (
                  <div className="glass-card p-4 border border-white/5">
                    <div className="text-xs font-mono text-text-muted mb-1 uppercase tracking-widest">Your Answer</div>
                    <p className="text-sm text-text-secondary">{userAnswer}</p>
                  </div>
                )}

                {/* Risk message after rating */}
                <AnimatePresence>
                  {riskMessage && (
                    <motion.div
                      key="risk-msg"
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      className="text-xs font-mono py-2 px-3 rounded border"
                      style={{
                        color: RATING_CONFIG[riskRating]?.color,
                        borderColor: RATING_CONFIG[riskRating]?.border,
                        background: RATING_CONFIG[riskRating]?.bg,
                      }}
                      data-testid="risk-message"
                    >
                      {riskMessage}
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Rating buttons — new honest labels, middle options slightly emphasized */}
                {!riskMessage && (
                  <div className="grid grid-cols-4 gap-2" data-testid="rating-buttons">
                    {Object.entries(RATING_CONFIG).map(([key, cfg]) => {
                      const Icon = cfg.icon;
                      return (
                        <button
                          key={key}
                          data-testid={`rate-${key}`}
                          onClick={() => handleRate(key)}
                          disabled={submitting}
                          className={`flex flex-col items-center gap-1 rounded-md border transition-all disabled:opacity-50 disabled:cursor-not-allowed
                            ${cfg.emphasis
                              ? 'p-3.5 hover:scale-105 active:scale-95'
                              : 'p-3 hover:scale-103 active:scale-95 opacity-90 hover:opacity-100'
                            }`}
                          style={{ background: cfg.bg, borderColor: cfg.border, color: cfg.color }}
                        >
                          <Icon size={cfg.emphasis ? 15 : 13} />
                          <span className={`font-mono font-bold ${cfg.emphasis ? 'text-xs' : 'text-xs'} text-center leading-tight`}>
                            {cfg.label}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </motion.div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
