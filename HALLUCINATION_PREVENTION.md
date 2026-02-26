# HALLUCINATION PREVENTION – MVP

## 1. Kernproblem

LLMs halluzinieren, wenn sie:
- Lücken füllen dürfen
- implizites Wissen nutzen
- unklare Prompts erhalten

---

## 2. Präventionsmaßnahmen (Pflicht)

- RAG mit Source-Only-Zwang
- harte Prompt-Regeln
- Quality Filter Prompt
- Drop bei Unsicherheit

---

## 3. Systemverhalten bei Unsicherheit

Wenn Modell:
- keine klare Antwort findet
- widersprüchliche Aussagen erkennt

Dann:
- Concept / Check wird verworfen
- nicht gespeichert
- nicht angezeigt

---

## 4. Logging

Jede verworfene Generierung:
- wird geloggt
- mit Grund markiert
- später analysierbar

---

## 5. Grundsatz

Lieber:
- weniger Content
- höhere Qualität

als:
- viel Content
- falsches Wissen
