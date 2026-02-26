# PRD – Knowledge Memory Platform (Phase 1)

## 1. Produktvision

Eine adaptive Learning Engine, die Wissen als Concepts modelliert,
Recall-Risiko berechnet und Lernsessions dynamisch priorisiert.

Langfristig:
- Universell für alle Studiengänge
- Community-basierte Study Packs
- Uni-Integrationen via Enrollment Codes
- Risk-basierte Exam-Readiness

Phase 1 fokussiert auf:
Cyber Security Studierende.

---

## 2. Problem Statement

Studierende:
- überschätzen ihr Wissen
- priorisieren falsch
- erkennen Wissenslücken nicht
- lernen passiv statt aktiv

Bestehende Tools:
- sind Karteikasten-basiert
- berücksichtigen keine Konzept-Abhängigkeiten
- modellieren kein Risiko

---

## 3. Lösung

### Concept-first Modell

Statt:
Karten → Wiederholen

Modell:
Content → Concepts → Checks → Risk → Adaptive Sessions

---

## 4. Kernobjekte

### Study Pack
- versioniert
- privat oder geteilt
- Domain optional

### Concept
- Titel
- Definition
- Common Mistake
- Prerequisites
- Exam Weight

### Check
- Recall
- Contrast
- Scenario
- Error-Spotting

### UserConceptState
- stability
- difficulty
- recall_probability
- risk
- review_history

---

## 5. User Journey

1. Signup
2. Upload Material
3. Concept Preview
4. Start Session
5. Risk-Dashboard
6. Wiederkehrende Nutzung

---

## 6. Functional Requirements

### 6.1 Auth
- JWT
- Secure password storage

### 6.2 Study Pack Creation
- Upload PDF/Text
- AI Extraction
- Manual Editing
- Versioning ready

### 6.3 Session Engine
- Risk-Sortierung
- Adaptive Check-Type
- Immediate Feedback
- Micro-Drill bei Fehler

### 6.4 Analytics
- Session Logs
- Recall Tracking
- Weak Area Identification

---

## 7. Non-Functional Requirements

- Skalierbares DB-Design
- Versionierbare Study Packs
- Separation:
  - Content Layer
  - Personal Mastery Layer
- Datenschutz:
  - Private by default

---

## 8. Future-Proofing (nicht MVP)

### Uni Integration
- CourseInstance
- Enrollment Code
- Institution Table
- Official Pack Binding

### Community Packs
- Versioning
- Moderation
- Reputation

### Advanced Engine
- Concept Graph
- Dependency Propagation
- Exam Simulation Mode
- Forgetting Forecast

---

## 9. KPIs (Phase 1)

- 30-Tage aktive Nutzer
- ≥60% D7 Retention
- ≥20% Verbesserung Recall-Rate
- ≥30% Nutzer sagen „besser als Anki“

---

## 10. Long-Term Positionierung

Nicht:
Flashcard App

Sondern:
Knowledge Reliability System
