# RAG STRATEGY – MVP

## 1. Ziel von RAG im MVP

- Verhindern von Halluzinationen
- Klare Quellenbindung
- Nachvollziehbarkeit für Nutzer
- Juristisch saubere Nutzung

---

## 2. Grundsatz (nicht verhandelbar)

Das Modell darf:
- AUSSCHLIESSLICH aus bereitgestelltem Kontext arbeiten
- KEIN externes Wissen verwenden
- KEINE Annahmen treffen

Wenn Information fehlt:
→ "INSUFFICIENT SOURCE INFORMATION"

---

## 3. MVP-RAG-Ansatz

Kein klassischer Vector-RAG.

Stattdessen:
- Chunk-basierter Kontext
- deterministische Auswahl
- direkte Quellenreferenz

---

## 4. Prompt-Zwang (Pflicht)

Jeder produktive Prompt MUSS enthalten:

"Use ONLY the provided study material.
If the information is not explicitly present,
return 'INSUFFICIENT SOURCE INFORMATION'.
Do NOT rely on prior knowledge."

---

## 5. Vorteile dieses Ansatzes

- keine versteckten Halluzinationen
- keine Embedding-Komplexität
- vollständige Kontrolle
- perfekt für User-Upload-Lernen

---

## 6. Upgrade-Pfad (später)

- Embeddings + Vector Search
- nur für:
  - große öffentliche Knowledge Bases
  - Community Packs
  - Multi-Source Retrieval
