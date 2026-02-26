# SESSION ENGINE – MVP LOGIC

## Session Start
- Load all UserConceptStates
- Calculate risk per concept
- Sort descending
- Select top N based on time budget

## Check Selection
- If recall_probability < 0.6 → Recall
- If recall_probability 0.6–0.8 → Contrast
- If > 0.8 → Scenario / Error

## Answer Handling
- Again → stability ↓
- Hard → small stability ↑
- Good → normal ↑
- Easy → strong ↑

## Micro-Fix
If incorrect:
- Generate corrective check
- Insert immediately
