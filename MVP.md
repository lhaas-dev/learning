# MVP – Cyber Security Knowledge Trainer

## 1. Ziel des MVP

Ziel ist es zu beweisen, dass:
- Studierende Cyber-Security-Konzepte zuverlässiger behalten
- typische Denkfehler reduziert werden
- das System gegenüber klassischem Lernen (Anki/Notizen) einen klaren Vorteil bietet

Der MVP ist erfolgreich, wenn:
- 5–10 aktive Tester 30 Tage lang nutzen
- tägliche Sessions stattfinden
- ein messbarer Recall-Vorteil entsteht
- mindestens 3 Tester freiwillig weiternutzen wollen

---

## 2. Zielgruppe

- Cyber Security Studierende (Bachelor / frühes Master-Level)
- Fokus: Uni-ähnlicher Lernstoff
- Private Nutzung, kein offizieller Uni-Partner

---

## 3. Nicht-Ziele

- Kein öffentlicher Pack-Marktplatz
- Keine Uni-Partnerschaften
- Keine Mobile Apps
- Keine Social-Features
- Keine Gamification
- Keine Multi-Domain-Optimierung

---

## 4. Kernfunktionalitäten

### 4.1 User
- Registrierung (E-Mail + Passwort)
- Login
- JWT Auth

### 4.2 Study Pack
- Study Pack erstellen
- PDF/Text hochladen
- Concept-Extraktion via AI
- Check-Generierung (4 Typen)
- Concepts editieren/löschen
- Wichtigkeit setzen (Low/Medium/High)

### 4.3 Lern-Session
- Start 10/20/30 min Session
- Risk-basierte Concept-Auswahl
- Check anzeigen
- Bewertung (Again / Hard / Good / Easy)
- Stability & Recall-Update
- Micro-Fix bei Fehlern

### 4.4 Dashboard
- Risk-Score
- Weakest Concepts
- Session-Historie
- Exam-Date (optional)

---

## 5. Datenstruktur (Konzeptionell)

User  
StudyPack  
Concept  
Check  
UserConceptState  
CourseInstance (future-proof, optional)  
Enrollment (future-proof, optional)

---

## 6. Risk-Formel (MVP-Version)

risk = (1 - recall_probability)  
       * exam_weight  
       * dependency_weight

---

## 7. Erfolgsmessung

Metriken:
- D1 / D7 / D14 Retention
- Recall-Rate nach ≥7 Tagen
- Session-Frequenz
- Durchschnittliche Sessiondauer
- Subjektives Sicherheitsgefühl vs tatsächliche Trefferquote

---

## 8. Technischer Stack

Backend:
- Python
- FastAPI
- Postgres

Frontend:
- Next.js oder React

AI:
- LLM API (Concept + Check Generation)

Hosting:
- Lokal → später VPS

---

## 9. Timeline (1 Woche Build Sprint)

Tag 1: Repo + DB Setup  
Tag 2: Models + Auth + CRUD  
Tag 3: AI Concept + Check Generation  
Tag 4: Session Engine  
Tag 5: Risk + Dashboard  
Tag 6: Self-Test  
Tag 7: Tester vorbereiten
