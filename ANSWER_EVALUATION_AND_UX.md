# Answer Evaluation & UX Improvements – MVP

This document defines how user answers are evaluated and which UX changes are required to make the learning experience feel clearly superior to traditional flashcard-based systems such as Anki. The focus is on conservative, trust-first evaluation that avoids hallucinations, avoids unfair auto-grading, and strengthens the feeling that the system understands how the user thinks rather than merely what the user answers.

## Core Principle: Assisted Self-Assessment

The core principle of answer evaluation in the MVP is assisted self-assessment. The system must not blindly auto-grade free-text answers, must not rely on semantic similarity scores, and must not allow the language model to decide correctness. Instead, the system checks whether required core ideas are present in the user's answer, highlights what is missing or incorrect, and leaves the final self-assessment decision to the user via the existing rating buttons. This preserves trust and avoids false negatives or false positives that would immediately undermine credibility.

## Answer Requirements

Each generated knowledge check must include explicit answer requirements. These requirements define which core ideas must be present in a correct answer and which statements are explicitly wrong. For example, a check about multi-factor authentication must require that authentication is strengthened and must explicitly reject the idea that permissions or authorization are granted by MFA. These requirements are generated together with the check and stored as part of the check object. They are never inferred dynamically at answer time.

## Conservative Analysis Flow

When a user submits a free-text answer, the backend performs a conservative analysis flow. First, the system extracts the explicit claims made in the user's answer. This extraction step may use an LLM, but only to identify what the user explicitly stated. The model is strictly forbidden from judging correctness, adding missing information, or rewriting the answer. It simply returns a list of claims found in the text. All correctness decisions are then performed deterministically by matching these extracted claims against the stored answer requirements. Based on this comparison, the result is categorized as correct, partially correct, or incorrect or missing a key idea. The system never outputs a numeric score and never overrides the user's final rating.

## Feedback Design

The feedback shown to the user must be redesigned to surface the core learning insight immediately. Long explanation paragraphs dilute the learning effect and should be avoided by default. Each check must display a single, concise, exam-grade core answer that clearly captures the essential distinction or rule being tested. For example, the core answer for an MFA question should be presented as a single sentence emphasizing that MFA strengthens authentication but does not define authorization. Additional explanation may be available in a collapsible section, but the default view must prioritize immediacy and clarity.

Directly below the core answer, the system must show user-specific feedback derived from requirement matching. This feedback explicitly lists which required ideas were covered and which were missing or incorrect. The result is summarized in one short sentence, such as "Partially correct — key distinction missing." This feedback must be derived from rule-based comparison, not from model judgment. Its purpose is to make the gap between the user's thinking and the expected exam-level answer visible and actionable.

## Rating Button Labels

The rating buttons must be adjusted to reduce ego-biased self-assessment. Button labels should be rewritten to reflect recall quality rather than perceived success:

| Old Label | New Label       |
|-----------|-----------------|
| Again     | Didn't know     |
| Hard      | Partially knew  |
| Good      | Knew it         |
| Easy      | Instant recall  |

The visual emphasis should slightly favor the middle option to encourage honest ratings. The underlying spaced repetition algorithm remains unchanged.

## Post-Rating Risk Message

After the user selects a rating, the system must display one short risk-oriented message to reinforce the feeling that the system is actively managing learning priorities. For lower ratings, the message should communicate that this mistake frequently causes exam errors and that the concept will be prioritized. For higher ratings, the message should communicate that low risk was detected and that the concept will be deprioritized. This message is critical for differentiating the system from passive flashcard tools.

## Concept Card UX

At the concept level, the UX must clearly communicate exam relevance. Every concept card must include a simple visual indicator of exam risk, such as high, medium, or low, expressed as icons or short labels rather than numbers or percentages. Additionally, each concept card should include a single short action hint, such as "Frequently tested," "Common exam mistake," or "Often confused with another concept." This prevents flat concept lists and helps users allocate attention effectively.

## Post-Upload Risk Summary

Immediately after material upload and concept extraction, and before the user enters the study pack, the system must present a short summary of top detected learning risks. This summary highlights the most common or critical misconceptions identified in the uploaded material. It is not generated from external knowledge and does not introduce new concepts; it is simply an aggregation of extracted common mistakes. Its purpose is to create an immediate "aha" moment that demonstrates the system's diagnostic value before the first learning session even begins.

## Explicit Non-Goals

Certain features are explicitly out of scope and must not be implemented in the MVP. These include:

- Automatic pass or fail grading
- Numeric confidence scores
- Generative explanations beyond the extracted content
- Motivational or coaching language
- Any form of AI-driven judgment that cannot be clearly justified by stored rules and data

Trust and transparency are more important than automation.

## Success Criteria

The answer evaluation and UX improvements described here are considered successfully implemented when user answers are visibly analyzed, missing ideas are clearly highlighted, rating behavior becomes more honest, and early testers report that the system understands how they think rather than merely checking whether they remembered a phrase.

## Out of Scope (Post-MVP)

Long-term extensions such as cross-session pattern detection, session debriefs, and focused fix drills are explicitly post-MVP and must not influence the initial implementation.
