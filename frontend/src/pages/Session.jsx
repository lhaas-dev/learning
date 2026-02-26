import React, { useState, useEffect } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import {
  X, ChevronRight, RotateCcw, Zap, CheckCircle2, AlertTriangle,
  Loader2, BookOpen, Brain, TrendingDown, Activity, Swords
} from 'lucide-react';
import { answerSession, getSessionDebrief, startDrillSession } from '../services/api';

const RATING_CONFIG = {
  again: {
    label: 'Again',
    sublabel: 'Didn\'t know',
    color: '#FF2D55',
    bg: 'rgba(255,45,85,0.1)',
    border: 'rgba(255,45,85,0.3)',
    icon: RotateCcw,
  },
  hard: {
    label: 'Hard',
    sublabel: 'Struggled',
    color: '#FFCC00',
    bg: 'rgba(255,204,0,0.1)',
    border: 'rgba(255,204,0,0.3)',
    icon: AlertTriangle,
  },
  good: {
    label: 'Good',
    sublabel: 'Recalled',
    color: '#2F81F7',
    bg: 'rgba(47,129,247,0.1)',
    border: 'rgba(47,129,247,0.3)',
    icon: CheckCircle2,
  },
  easy: {
    label: 'Easy',
    sublabel: 'Perfect',
    color: '#00C853',
    bg: 'rgba(0,200,83,0.1)',
    border: 'rgba(0,200,83,0.3)',
    icon: Zap,
  },
};

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

function SessionComplete({ stats, packTitle, onBack }) {
  const total = Object.values(stats).reduce((a, b) => a + b, 0);
  const good = (stats.good || 0) + (stats.easy || 0);
  const pct = total > 0 ? Math.round((good / total) * 100) : 0;
  const color = pct >= 70 ? '#00C853' : pct >= 40 ? '#FFCC00' : '#FF2D55';

  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-card p-8 max-w-md w-full text-center"
        data-testid="session-complete-screen"
      >
        <div
          className="text-6xl font-heading font-bold mb-2"
          style={{ color }}
          data-testid="session-score"
        >
          {pct}%
        </div>
        <div className="text-text-secondary text-sm mb-2">correct this session</div>
        <div className="text-text-muted text-xs font-mono mb-6">{packTitle}</div>

        <div className="grid grid-cols-4 gap-3 mb-8">
          {Object.entries(RATING_CONFIG).map(([key, cfg]) => {
            const Icon = cfg.icon;
            return (
              <div
                key={key}
                data-testid={`stat-${key}`}
                className="rounded-md p-3 border"
                style={{ background: cfg.bg, borderColor: cfg.border }}
              >
                <Icon size={14} className="mx-auto mb-1" style={{ color: cfg.color }} />
                <div className="font-mono font-bold text-lg" style={{ color: cfg.color }}>
                  {stats[key] || 0}
                </div>
                <div className="text-xs text-text-muted">{cfg.label}</div>
              </div>
            );
          })}
        </div>

        <div className="space-y-3">
          <button
            data-testid="back-to-pack-btn"
            onClick={onBack}
            className="btn-primary w-full justify-center"
          >
            <CheckCircle2 size={14} />
            Done
          </button>
        </div>
      </motion.div>
    </div>
  );
}

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
  const [microFix, setMicroFix] = useState(null);
  const [correctAnswer, setCorrectAnswer] = useState('');
  const [explanation, setExplanation] = useState('');
  const [sessionComplete, setSessionComplete] = useState(false);
  const [finalStats, setFinalStats] = useState({});

  useEffect(() => {
    if (!currentItem) {
      toast.error('Session data not found');
      navigate('/dashboard');
    }
  }, [currentItem, navigate]);

  const handleReveal = () => {
    setRevealed(true);
  };

  const handleRate = async (rating) => {
    if (!currentItem) return;
    setSubmitting(true);
    setMicroFix(null);

    try {
      const res = await answerSession({
        session_id: sessionId,
        concept_id: currentItem.concept?.id || '',
        check_id: currentItem.check?.id || '',
        rating,
        user_answer: userAnswer,
      });

      setCorrectAnswer(res.data.correct_answer || '');
      setExplanation(res.data.explanation || '');

      if (res.data.micro_fix) {
        setMicroFix(res.data.micro_fix);
      }

      if (res.data.session_complete) {
        setFinalStats(res.data.stats || {});
        setSessionComplete(true);
        return;
      }

      // Move to next item after short delay
      setTimeout(() => {
        const next = res.data.next_item;
        setCurrentItem(next);
        setPosition(next.position);
        setRevealed(false);
        setUserAnswer('');
        setMicroFix(null);
        setCorrectAnswer('');
        setExplanation('');
        setSubmitting(false);
      }, microFix ? 2500 : 500);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to submit answer');
      setSubmitting(false);
    }
  };

  if (sessionComplete) {
    return (
      <SessionComplete
        stats={finalStats}
        packTitle={packTitle}
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
            <span className="text-xs font-mono text-text-muted uppercase tracking-widest hidden sm:block">
              {packTitle}
            </span>
          </div>
          <div className="flex-1">
            <ProgressBar current={position - 1} total={total} />
          </div>
          <button
            data-testid="exit-session-btn"
            onClick={() => {
              if (window.confirm('Exit session? Progress so far will be saved.')) {
                navigate('/dashboard');
              }
            }}
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
            key={`${currentItem.check?.id}-${revealed}`}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.25 }}
            className="space-y-5"
          >
            {/* Concept info */}
            <div className="glass-card p-5">
              <div className="flex items-center gap-2 mb-3">
                <BookOpen size={14} className="text-brand-primary" />
                <span className="text-xs font-mono text-brand-primary uppercase tracking-widest">
                  {concept.title || 'Concept'}
                </span>
                {check.type && <CheckTypeBadge type={check.type} />}
              </div>
              {concept.short_definition && (
                <p className="text-sm text-text-secondary leading-relaxed">
                  {concept.short_definition}
                </p>
              )}
            </div>

            {/* Check question */}
            <div className="glass-card p-6">
              <p
                className="text-base text-text-primary font-medium leading-relaxed"
                data-testid="check-question"
              >
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
                  placeholder="Write your answer here (optional)... then reveal"
                  className="terminal-input resize-none h-28 text-sm w-full"
                />
                <button
                  data-testid="reveal-answer-btn"
                  onClick={handleReveal}
                  className="btn-primary w-full justify-center"
                >
                  <ChevronRight size={14} />
                  Reveal Answer
                </button>
              </div>
            )}

            {/* Revealed answer */}
            {revealed && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="space-y-4"
              >
                {/* Correct answer */}
                <div
                  className="glass-card p-5 border border-risk-low/20"
                  data-testid="correct-answer-panel"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle2 size={13} className="text-risk-low" />
                    <span className="text-xs font-mono text-risk-low uppercase tracking-widest">
                      Correct Answer
                    </span>
                  </div>
                  <p className="text-text-primary text-sm leading-relaxed" data-testid="correct-answer-text">
                    {check.expected_answer || 'No expected answer defined'}
                  </p>
                  {check.explanation && (
                    <p className="text-text-secondary text-xs mt-2 leading-relaxed">
                      {check.explanation}
                    </p>
                  )}
                </div>

                {/* User's answer (if written) */}
                {userAnswer.trim() && (
                  <div className="glass-card p-4 border border-white/5">
                    <div className="text-xs font-mono text-text-muted mb-1 uppercase tracking-widest">Your Answer</div>
                    <p className="text-sm text-text-secondary">{userAnswer}</p>
                  </div>
                )}

                {/* Micro-fix (if wrong) */}
                {microFix && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="glass-card p-4 border border-risk-high/20 bg-risk-high/5"
                    data-testid="micro-fix-panel"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle size={13} className="text-risk-high" />
                      <span className="text-xs font-mono text-risk-high uppercase tracking-widest">
                        Correction
                      </span>
                    </div>
                    {microFix.misunderstanding && (
                      <p className="text-xs text-text-secondary mb-2">
                        <strong className="text-risk-high/80">Gap:</strong> {microFix.misunderstanding}
                      </p>
                    )}
                    {microFix.corrective_check && (
                      <p className="text-xs text-text-secondary mb-2">
                        <strong className="text-brand-primary">Quick Check:</strong> {microFix.corrective_check}
                      </p>
                    )}
                    {microFix.memory_anchor && (
                      <p className="text-xs text-brand-primary/80 font-mono bg-brand-primary/5 p-2 rounded mt-1">
                        Anchor: {microFix.memory_anchor}
                      </p>
                    )}
                  </motion.div>
                )}

                {/* Rating buttons */}
                <div className="grid grid-cols-4 gap-2" data-testid="rating-buttons">
                  {Object.entries(RATING_CONFIG).map(([key, cfg]) => {
                    const Icon = cfg.icon;
                    return (
                      <button
                        key={key}
                        data-testid={`rate-${key}`}
                        onClick={() => handleRate(key)}
                        disabled={submitting}
                        className="flex flex-col items-center gap-1 p-3 rounded-md border transition-all hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
                        style={{
                          background: cfg.bg,
                          borderColor: cfg.border,
                          color: cfg.color,
                        }}
                      >
                        {submitting ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <Icon size={14} />
                        )}
                        <span className="text-xs font-mono font-bold">{cfg.label}</span>
                        <span className="text-xs opacity-60 hidden sm:block">{cfg.sublabel}</span>
                      </button>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
