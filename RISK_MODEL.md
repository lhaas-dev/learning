# RISK MODEL – MVP

## Recall Probability
Derived from:
- stability
- days_since_last_review

Simple decay model is sufficient for MVP.

## Risk Formula
risk =
(1 - recall_probability)
* exam_weight
* dependency_weight (default 1.0)

## Priority Rule
Higher risk → earlier in session
