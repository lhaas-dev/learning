# Knowledge Memory MVP — PRD

## Original Problem Statement
Build a Knowledge Memory MVP based on GitHub specs at https://github.com/lhaas-dev/learning.git.
An adaptive learning engine for Cyber Security students. Users upload PDF/text study material,
AI extracts concepts and generates knowledge checks, risk-based learning sessions help students retain knowledge.

**Spec source:** GitHub repository with 18+ Markdown documents defining architecture, database schema, AI prompts, RAG strategy, chunking strategy, hallucination prevention rules, session engine, risk model, and API endpoints.

---

## Architecture

- **Backend:** FastAPI (Python) + MongoDB (via Motor async driver)
- **Frontend:** React 18 + React Router v6 + Tailwind CSS + Framer Motion
- **AI:** Claude Sonnet 4-6 (claude-sonnet-4-6) via Emergent LLM Key
- **Design:** "Tactical Minimal" dark theme (Electric Cyan #00E5FF + Deep Obsidian #050505)

---

## User Personas

- **Primary:** Cyber Security students (Bachelor/early Master level)
- **Use Case:** Private adaptive study tool, not exam prep service

---

## Core Requirements (Static)

1. User registration + login (JWT auth)
2. Study Pack creation (title, domain, description)
3. PDF/text upload → AI concept extraction → check generation → quality filtering
4. Concept preview and editing (title, definition, mistake, exam weight)
5. Risk-based learning sessions (10/20/30 min)
6. Rating system (Again/Hard/Good/Easy) → stability/recall updates
7. Micro-fix for wrong answers (Claude-powered correction)
8. Dashboard: avg risk, weakest concepts, session history

---

## Data Model (MongoDB)

- **users:** id, email, password_hash, created_at
- **study_packs:** id, owner_id, title, description, domain, visibility, version, concept_count, created_at
- **concepts:** id, study_pack_id, title, short_definition, common_mistake, exam_weight, exam_weight_label, prerequisite_concepts, created_at
- **checks:** id, concept_id, type(recall/contrast/scenario/error), prompt, expected_answer, explanation, difficulty_hint
- **user_concept_states:** id, user_id, concept_id, stability, difficulty, recall_probability, risk, last_reviewed_at
- **review_events:** id, user_id, concept_id, check_id, rating, response_time, created_at
- **sessions:** id, user_id, pack_id, duration_minutes, queue, current_index, started_at, completed_at, stats, total
- **upload_jobs:** id, pack_id, user_id, status, created_at, started_at, completed_at, concepts_extracted, concepts, error

---

## Session Engine

- Risk = (1 - recall_probability) * exam_weight * dependency_weight(1.0)
- Recall = exp(-days_since_review / stability) (forgetting curve)
- Stability multipliers: Again×0.7, Hard×1.1, Good×1.3, Easy×2.0
- Check type by recall: <0.6→recall, 0.6-0.8→contrast, >0.8→scenario
- Session sizes: 10min=8, 20min=15, 30min=22 concepts

---

## What's Been Implemented (Feb 26, 2026)

### Backend (server.py)
- [x] POST /api/auth/register + POST /api/auth/login (JWT)
- [x] POST /api/packs, GET /api/packs, GET /api/packs/:id
- [x] POST /api/packs/:id/upload → background task → returns job_id
- [x] GET /api/jobs/:id → poll for processing status
- [x] GET /api/packs/:id/concepts, PATCH /api/concepts/:id, DELETE /api/concepts/:id
- [x] POST /api/sessions/start (risk-sorted queue)
- [x] POST /api/sessions/answer (stability/recall updates + micro-fix + session_id tracking in review events)
- [x] GET /api/sessions/:id
- [x] GET /api/sessions/:id/debrief (Claude, session-data-only, graceful fallback)
- [x] POST /api/sessions/drill (5-min fix drill, recall+contrast only, max 2 concepts)
- [x] POST /api/checks/evaluate (claim extraction + deterministic matching, never overrides user rating)
- [x] GET /api/dashboard/overview (includes drill session labeling)
- [x] AI Pipeline: concept extraction, check generation (4 types), quality filtering, micro-fix, session debrief
- [x] RAG: source-only constraints, no hallucination, returns INSUFFICIENT_SOURCE_INFORMATION
- [x] Chunking: 300-600 word chunks at paragraph boundaries

### Frontend
- [x] Auth page (login/register, split-screen design)
- [x] Dashboard (command center grid, stats, weakest concepts, session history + DRILL badge)
- [x] Study Pack Detail (concept cards with risk badges, inline editing, exam weight)
- [x] Upload page (text paste + PDF, async polling, progress indicator)
- [x] Session page (question reveal, rating buttons, micro-fix panel)
- [x] Session Debrief screen (Top Knowledge Risks, Dominant Pattern, 5-Min Fix Drill CTA)
- [x] Drill session flow (navigates to active session targeting weak concepts)
- [x] PDF upload via chunked upload (POST /api/upload/chunk + /api/upload/finalize) — no proxy size limit, progress bar
- [x] No concept limit — all chunks processed, all concepts extracted
- [x] Pipeline parallelized: 2 chunks concurrently with asyncio.Semaphore
- [x] asyncio.to_thread for LLM calls — server stays responsive during AI processing
- [x] URL/Link source upload (POST /api/upload/url) — fetches public pages, Wikipedia, etc.
- [x] Multiple PDFs per pack — primary + optional extras, each gets own job tracker
- [x] AI document type detection — classifies each upload as Theoriebuch, Abschlussprüfung, Übungstest, etc.
- [x] DocTypeBadge component — displayed in upload result + job tracker
- [x] German language generation — all AI output in source material language
- [x] Upload page fully German UI ("Material hinzufügen", "Konzepte extrahieren", etc.)
  - Block 1: "Correct answer (core idea)" — bold core answer + collapsible explanation
  - Block 2: "What we understood from your answer" — extracted_claims bullet list, always visible for non-scenario
  - Block 3: "Missing or incorrect ideas" — "Missing key ideas:" list or "All required core ideas were addressed."
  - Block 4: "Incorrect assumption detected" — quoted wrong statement + "This assumption commonly causes exam mistakes."
  - Scenario checks skip blocks 2/3/4 (open-ended, no false analysis)
  - Rating buttons: Didn't know / Partially knew / Knew it / Instant recall
  - System risk feedback: "High exam risk detected." / "Low risk detected." (plain text, no animation)

---

## Prioritized Backlog

### P0 (Blocking for Production)
- [ ] Rate limiting on AI endpoints (prevent abuse)
- [ ] Error boundary in React (catch render errors)
- [ ] Concept count sync (update when deleting from upload preview)

### P1 (Core UX)
- [ ] Backfill `answer_requirements` for old Checks (admin endpoint to retroactively generate for checks created before evaluation feature)
- [ ] PDF upload frontend testing (currently text-only tested)
- [ ] Session resume (if user exits mid-session)
- [ ] Exam date setting for risk urgency boost
- [ ] Concept import from existing JSON

### P2 (Enhancement)
- [ ] Search/filter concepts within a pack
- [ ] Multiple uploads per pack (additive, not replace)
- [ ] Export session statistics to CSV
- [ ] Replace Emergent LLM key with user's own Anthropic API key

---

## MVP Limitations (Known)
1. **No file upload test from UI** — upload works with text paste, PDF extraction via PyPDF2 (not tested end-to-end)
2. **AI processing time** — 30-90 seconds for extraction (handled by background jobs + polling)
3. **Single MongoDB instance** — no backup or replication
4. **No pagination** — concept lists and sessions not paginated
5. **Dependency weight = 1.0** — prerequisite propagation not yet implemented (future)
6. **course_instances table** — future-proof placeholder, not implemented per spec
