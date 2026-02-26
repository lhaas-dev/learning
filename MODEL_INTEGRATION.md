# MODEL INTEGRATION – MVP

## 1. Architektur

- Backend orchestriert alle AI-Calls
- Frontend hat keinen direkten Modellzugang
- AI ist stateless

---

## 2. Request Flow

1. User lädt Material hoch
2. Backend chunked Content
3. Backend ruft:
   - Concept Prompt
   - Check Prompt
   - Quality Filter Prompt
4. Validierte Ergebnisse speichern
5. Session Engine nutzt gespeicherte Daten

---

## 3. Fehlerbehandlung

- Timeout → Retry max. 1x
- Invalid JSON → Drop
- Unsichere Antwort → Drop

---

## 4. Kostenkontrolle

- Chunk-Größe begrenzen
- Max Checks pro Concept
- Keine Wiederholungsaufrufe ohne Änderung
