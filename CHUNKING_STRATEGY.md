# CHUNKING STRATEGY – MVP

## 1. Ziel

Saubere Texteinheiten für:
- Concept Extraction
- Check Generation
- Source Referencing

---

## 2. Chunk-Größe

Empfohlen:
- 300–600 Wörter
- maximal 1–2 Konzepte pro Chunk
- harte Trennung bei:
  - Überschriften
  - Absätzen
  - Themenwechsel

---

## 3. Chunk-Metadaten

Jeder Chunk MUSS enthalten:
- source_id
- page_number (wenn PDF)
- heading_context
- raw_text

---

## 4. Chunking-Regeln

- Tabellen separat behandeln
- Code-Blöcke separat behandeln
- Listen nicht aufsplitten
- Definition + Erklärung zusammenhalten

---

## 5. Anti-Pattern (verboten)

- riesige Chunks (>1000 Wörter)
- semantisch gemischte Inhalte
- automatisches Zusammenfassen vor Extraktion
