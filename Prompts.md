# PROMPTS – Concept & Check Generation (MVP)

Diese Prompts werden im MVP für:
- Concept-Extraktion
- Check-Generierung
- Qualitätsfilter
- Fehlerkorrektur (Micro-Fix)

verwendet.

Ziel:
- Lernbare, prüfbare Concepts
- kurze, klare Checks
- Fokus auf typische Denkfehler
- kein generischer AI-Müll

---

## 1. Concept Extraction Prompt

**Verwendung:**  
Nach Upload eines PDF-/Text-Chunks (z. B. 1–3 Seiten Skript)

```text
You are an expert university-level educator.

Your task is to extract LEARNABLE CONCEPTS from the following study material.

Rules:
- A concept must be testable.
- One concept = one core idea.
- Avoid vague or overly broad topics.
- Prefer concepts that are commonly misunderstood by students.
- If two ideas are tightly related but distinct, split them.
- Do NOT include meta-topics (e.g. "introduction", "overview").

For each concept, return:
1. concept_title (max 6 words)
2. short_definition (1–2 sentences)
3. common_mistake (typical student misconception)
4. prerequisite_concepts (list, empty if none are obvious)

Study material:
<<<
{TEXT_CHUNK}
>>>

Return the result as a JSON array.

2. Check Generation Prompt (per Concept)
Verwendung:
Für jedes extrahierte Concept

You are generating exam-oriented knowledge checks for a university student.

Concept:
Title: {concept_title}
Definition: {short_definition}
Common mistake: {common_mistake}

Generate EXACTLY 4 checks:

1. Recall check (direct factual recall)
2. Contrast check (distinguish from a commonly confused concept)
3. Scenario check (practical or exam-style situation)
4. Error-spotting check (identify why a statement is wrong)

Rules:
- Each check must test ONE idea only.
- Avoid vague verbs ("explain", "discuss").
- Answers must be short, precise and objectively verifiable.
- Do not include trick questions.
- Assume exam pressure and time constraints.

For each check, return:
- type (recall | contrast | scenario | error)
- prompt
- expected_answer
- short_explanation

Return the result as JSON.

3. Quality Filter Prompt (Auto-Review)
Verwendung:
Nach automatischer Check-Generierung, vor Speicherung

You are reviewing automatically generated study questions.

For each question, decide one of:
- KEEP
- EDIT
- DROP

Evaluation criteria:
- Is the question unambiguous?
- Does it test exactly one idea?
- Is the expected answer concise?
- Would this realistically appear in a university exam?
- Does it avoid unnecessary complexity?

For each question, return:
- decision (KEEP | EDIT | DROP)
- short_reason
- edited_version (only if decision = EDIT)

Questions:
<<<
{GENERATED_CHECKS_JSON}
>>>

Return the result as JSON.

4. Micro-Fix Prompt (After Wrong Answer)
Verwendung:
Wenn ein User eine Frage falsch beantwortet

A student answered a question incorrectly.

Concept:
Title: {concept_title}
Definition: {short_definition}
Common mistake: {common_mistake}

Question:
{prompt}

Student answer:
{user_answer}

Correct answer:
{expected_answer}

Your task:
1. Identify the most likely misunderstanding.
2. Generate ONE ultra-short corrective check (max 1 sentence).
3. Generate ONE memory anchor (short rule of thumb).

Rules:
- Be concise.
- Do not introduce new concepts.
- Focus on correcting the misunderstanding, not re-teaching everything.

Return as JSON with:
- misunderstanding
- corrective_check
- memory_anchor

5. Optional: Concept Importance Suggestion (MVP+)
Verwendung:
Optional, zur Vorbelegung von exam_weight

You are estimating exam relevance for university-level study material.

Concept:
{concept_title}
Definition:
{short_definition}

Based on typical university exams, estimate importance.

Return one of:
- LOW
- MEDIUM
- HIGH

Return only the label.

6. Prompt Design Principles (Fix)
Concept-first, not card-first
One idea per check
Short answers > long explanations
Error detection > passive recall
Human-editable at every step
These prompts are intentionally simple and robust.
They are designed to work with basic LLM capabilities
and improve over time through user feedback and data.
