# DATABASE SCHEMA – MVP

## users
- id (uuid)
- email
- password_hash
- created_at

## study_packs
- id
- owner_id
- title
- description
- domain
- visibility (private/shared)
- version
- created_at

## concepts
- id
- study_pack_id
- title
- short_definition
- common_mistake
- exam_weight
- created_at

## checks
- id
- concept_id
- type
- prompt
- expected_answer
- explanation
- difficulty_hint

## user_concept_state
- id
- user_id
- concept_id
- stability
- difficulty
- recall_probability
- risk
- last_reviewed_at

## review_events
- id
- user_id
- concept_id
- check_id
- rating (again/hard/good/easy)
- response_time
- created_at

## course_instances (future)
- id
- name
- semester
- exam_date
- institution_id (nullable)
- enrollment_code
