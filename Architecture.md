# ARCHITECTURE – MVP System Design

## 1. Architektur-Ziel

- Schnell baubar
- Klar getrennte Verantwortlichkeiten
- Später erweiterbar (Uni, Community, Analytics)
- Kein Rebuild nötig

---

## 2. High-Level Komponenten

Frontend (Web)
- Next.js / React
- Session UI
- Concept Preview
- Dashboard

Backend (API)
- FastAPI
- Auth
- Session Engine
- Risk Engine
- AI Orchestration

Database
- PostgreSQL
- Single DB, keine Microservices

AI Layer
- External LLM API
- Stateless
- Prompt-gesteuert

---

## 3. Datenfluss (Learning Session)

1. User startet Session
2. Backend:
   - liest UserConceptState
   - berechnet Risk
   - wählt Concept + Check
3. Frontend zeigt Check
4. User antwortet
5. Backend:
   - bewertet Antwort
   - updated Stability / Recall
   - loggt Event
6. Nächster Check

---

## 4. Schichten-Trennung

- Content Layer:
  - StudyPack
  - Concept
  - Check

- Personal Layer:
  - UserConceptState
  - ReviewHistory

Diese Schichten dürfen **nie** vermischt werden.

---

## 5. Erweiterbarkeit (Future)

- CourseInstance → Uni
- Enrollment → Einladungscode
- Analytics → Aggregation
- Templates → Domain-Spezifika
