# AI MODEL STRATEGY – MVP

## 1. Ziel

Auswahl und Einsatz von KI-Modellen für den MVP mit Fokus auf:
- minimale Halluzinationen
- stabile, strukturierte Outputs
- didaktische Qualität
- einfache Wartbarkeit

---

## 2. Primary Model

### Claude 4.6 (Anthropic)

Verwendung:
- Concept Extraction
- Check Generation
- Quality Filtering
- Micro-Fix / Error Diagnosis

Begründung:
- sehr starkes Textverständnis
- konservatives Verhalten bei Unsicherheit
- stabile JSON-Ausgaben
- gut geeignet für akademische Inhalte

Claude ist das Standardmodell für **alle produktiven Lerninhalte**.

---

## 3. Secondary Model (optional)

### GPT-5.2 (OpenAI)

Verwendung (optional, nicht MVP-kritisch):
- Vergleichsgenerierung
- alternative Szenariofragen
- spätere Exam-Simulation

GPT-5.2 ist **kein Pflichtbestandteil** des MVP.

---

## 4. Modellprinzipien (fix)

- Ein Modell ist besser als viele
- Konsistenz > Vielfalt
- Struktur > Kreativität
- Zurückhaltung > Halluzination

---

## 5. Explizite Nicht-Ziele

- Kein Fine-Tuning im MVP
- Kein Multi-Agent-System
- Kein Modell-Mixing im Kernworkflow
- Keine autonomen Ketten
