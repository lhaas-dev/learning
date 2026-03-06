from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, Any, List
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import os
import json
import math
import uuid
import re
import io
import base64
import shutil
import asyncio
import logging
import tomllib
import requests as http_requests

from passlib.context import CryptContext
from jose import jwt, JWTError
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Knowledge Memory MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Database ────────────────────────────────────────────────────────────────
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

users_col = db["users"]
packs_col = db["study_packs"]
concepts_col = db["concepts"]
checks_col = db["checks"]
ucs_col = db["user_concept_states"]
review_col = db["review_events"]
sessions_col = db["sessions"]
jobs_col = db["upload_jobs"]

# ─── Auth ─────────────────────────────────────────────────────────────────────
JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode({"sub": user_id, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await users_col.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def doc_id(doc: dict) -> dict:
    """Convert MongoDB _id to id string."""
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    # Stringify any nested ObjectIds
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
        elif isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


# ─── Chunking ─────────────────────────────────────────────────────────────────
def chunk_text(text: str, target_words: int = 800, overlap_words: int = 100) -> list:
    """
    Split text into ~800-word chunks at paragraph boundaries.
    Adds a 100-word overlap window from the previous chunk so concepts
    that span a chunk boundary are fully visible in at least one chunk.
    """
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text.strip()) if p.strip()]
    chunks = []
    current: list[str] = []
    current_words = 0
    overlap_tail: list[str] = []  # last overlap_words words from the previous chunk

    def finalize_chunk():
        nonlocal overlap_tail
        text_body = "\n\n".join(current)
        # Prepend overlap from previous chunk for context
        if overlap_tail:
            full = " ".join(overlap_tail) + "\n\n" + text_body
        else:
            full = text_body
        chunks.append(full)
        # Save the tail of the current body (not the overlap prefix) for next chunk
        body_words = text_body.split()
        overlap_tail = body_words[-overlap_words:] if len(body_words) >= overlap_words else body_words

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        words = len(para.split())
        if current_words + words > target_words and current:
            finalize_chunk()
            current = [para]
            current_words = words
        else:
            current.append(para)
            current_words += words

    if current:
        finalize_chunk()

    return [c for c in chunks if len(c.split()) > 50]


def _extract_text_from_pdf_sync(pdf_bytes: bytes) -> str:
    """Sync PDF text extraction — safe to call via asyncio.to_thread."""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        texts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                texts.append(t)
        return "\n\n".join(texts)
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        raise RuntimeError(f"PDF extraction failed: {str(e)}")


# Legacy sync wrapper kept for backward compat
def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    return _extract_text_from_pdf_sync(pdf_bytes)


def _fetch_url_text_sync(url: str) -> str:
    """Fetch a public URL and extract readable text (Wikipedia, articles, etc.)."""
    from bs4 import BeautifulSoup
    headers = {"User-Agent": "Mozilla/5.0 (compatible; KnowledgeMemory/1.0; +https://knowledgememory.app)"}
    resp = http_requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    # Remove boilerplate elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "figure"]):
        tag.decompose()
    # Prefer main content containers
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="content")
        or soup.find(id="mw-content-text")   # Wikipedia
        or soup.find(class_="mw-parser-output")  # Wikipedia
        or soup.body
    )
    text = (main or soup).get_text(separator="\n", strip=True)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def detect_document_type(text_sample: str) -> str:
    """Classify the uploaded document into a German-language type label."""
    system = "You are a document type classifier. Respond only with valid JSON."
    prompt = f"""Classify this document based on its content and structure.

Choose exactly one type:
- Theoriebuch (pure theory, definitions, structured explanations)
- Theorie & Aufgaben (theory combined with practice exercises)
- Abschlussprüfung (final exam / Abschlussprüfung / Maturaprüfung)
- Übungstest (practice test or mock exam)
- Zusammenfassung (summary or condensed notes)
- Skript (lecture script or handout)
- Webseite (web page, Wikipedia, online article)
- Sonstiges (other)

Document sample:
<<<
{text_sample[:2500]}
>>>

Return ONLY valid JSON: {{"type": "Theoriebuch"}}"""
    try:
        response = await call_haiku(system, prompt)
        return extract_json(response).get("type", "Sonstiges")
    except Exception:
        return "Sonstiges"


# Temp directory for chunked uploads
UPLOAD_TEMP_DIR = "/tmp/km_uploads"
os.makedirs(UPLOAD_TEMP_DIR, exist_ok=True)


# ─── AI Service ───────────────────────────────────────────────────────────────
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
RAG_CONSTRAINT = (
    "Use ONLY the provided study material. "
    "If the information is not explicitly present, "
    "return 'INSUFFICIENT SOURCE INFORMATION'. "
    "Do NOT rely on prior knowledge."
)


def _make_blocking_call(model_provider: str, model_name: str, system_message: str, user_text: str):
    """Sync LLM call — safe to run via asyncio.to_thread."""
    def _call():
        loop = asyncio.new_event_loop()
        try:
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=str(uuid.uuid4()),
                system_message=system_message,
            ).with_model(model_provider, model_name)
            return loop.run_until_complete(chat.send_message(UserMessage(text=user_text)))
        finally:
            loop.close()
    return _call


async def call_claude(system_message: str, user_text: str) -> str:
    """Sonnet 4.6 — used for quality-critical tasks (check generation, merging, debrief)."""
    return await asyncio.to_thread(
        _make_blocking_call("anthropic", "claude-sonnet-4-6", system_message, user_text)
    )


async def call_haiku(system_message: str, user_text: str) -> str:
    """Haiku 4.5 — used for fast extraction tasks (concept extraction, quality filter, doc type)."""
    return await asyncio.to_thread(
        _make_blocking_call("anthropic", "claude-haiku-4-5-20251001", system_message, user_text)
    )


def extract_json(text: str) -> Any:
    """Extract JSON from LLM response (may contain markdown code fences)."""
    try:
        from json_repair import repair_json as _repair
        _HAS_REPAIR = True
    except ImportError:
        _HAS_REPAIR = False

    text = text.strip()
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```$', '', text, flags=re.MULTILINE)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if _HAS_REPAIR:
        try:
            return json.loads(_repair(text))
        except Exception:
            pass

    m = re.search(r'\[\s*\{.+?\}\s*\]', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            if _HAS_REPAIR:
                try:
                    return json.loads(_repair(m.group()))
                except Exception:
                    pass
    raise ValueError("Could not parse JSON from LLM response")


def parse_toml_list(text: str, root_key: str) -> list:
    """
    Parse a TOML [[array-of-tables]] response from the LLM.
    Falls back to JSON parsing if TOML fails.
    """
    text = text.strip()
    # Strip markdown fences
    text = re.sub(r'^```toml\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()

    try:
        data = tomllib.loads(text)
        return data.get(root_key, [])
    except Exception as toml_err:
        logger.debug(f"TOML parse failed for key '{root_key}': {toml_err} — trying JSON fallback")
        try:
            result = extract_json(text)
            return result if isinstance(result, list) else []
        except Exception:
            return []


async def extract_concepts_from_chunk(chunk: str, domain_context: str = "") -> list:
    system = f"You are an expert educator. {RAG_CONSTRAINT}"
    domain_line = f"\nStudy Pack Domain: {domain_context}\nCRITICAL: Extract ONLY concepts relevant to this domain. Skip concepts about unrelated tools, software navigation, or off-topic material.\n" if domain_context else ""
    prompt = f"""You are an expert educator extracting LEARNABLE CONCEPTS from study material.

CRITICAL: Respond in the SAME LANGUAGE as the study material below. If German, all output must be in German.
{domain_line}
Rules:
- A concept must be testable.
- One concept = one core idea.
- Avoid vague or overly broad topics.
- Prefer concepts that are commonly misunderstood by students.
- If two ideas are tightly related but distinct, split them.
- Do NOT include meta-topics (e.g. "introduction", "overview").
- Skip concepts that are not relevant to the study pack domain.

For each concept, return TOML fields:
- concept_title (max 6 words)
- short_definition (1-2 sentences)
- common_mistake (typical student misconception)
- prerequisite_concepts (list, empty if none)

Study material:
<<<
{chunk}
>>>

Return ONLY valid TOML using [[concept]] array-of-tables. Example:

[[concept]]
concept_title = "Deckungsbeitrag"
short_definition = "Die Differenz zwischen Erlösen und variablen Kosten."
common_mistake = "Schüler verwechseln Deckungsbeitrag mit Gewinn."
prerequisite_concepts = []

Return ONLY valid TOML, no other text."""

    try:
        response = await call_haiku(system, prompt)
        if "INSUFFICIENT SOURCE INFORMATION" in response:
            return []
        data = parse_toml_list(response, 'concept')
        return data if data else []
    except Exception as e:
        logger.warning(f"Concept extraction failed: {e}")
        return []


async def generate_checks_for_concept(concept: dict) -> list:
    system = f"You are generating exam-oriented knowledge checks for a student. {RAG_CONSTRAINT}"
    concept_title = concept.get('concept_title', concept.get('title', ''))
    concept_def = concept.get('short_definition', '')
    prompt = f"""You are generating exam-oriented knowledge checks for a student.

CRITICAL: Respond in the SAME LANGUAGE as the concept below. If German, all output must be in German.

Concept:
Title: {concept_title}
Definition: {concept_def}
Common mistake: {concept.get('common_mistake', '')}

Generate EXACTLY 4 checks:
1. Recall check (direct factual recall)
2. Contrast check (distinguish from a commonly confused concept)
3. Scenario check (practical or exam-style situation)
4. Error-spotting check (identify why a statement is wrong)

Rules:
- Each check must test ONE idea only.
- Avoid vague verbs ("explain", "discuss").
- expected_answer must be a single exam-grade sentence.
- short_explanation is 1-2 sentences of additional context only.
- Do not include trick questions.
- All text must be in the same language as the concept.

Return ONLY valid TOML using [[check]] array-of-tables. Example:

[[check]]
type = "recall"
prompt = "Was ist der Deckungsbeitrag?"
expected_answer = "Die Differenz zwischen Erlösen und variablen Kosten."
short_explanation = "Er zeigt den Beitrag zur Deckung der Fixkosten."
required_ideas = ["Differenz Erlöse variable Kosten", "Fixkostendeckung"]
wrong_statements = ["Deckungsbeitrag = Gewinn"]

Return ONLY valid TOML, no other text."""

    try:
        response = await call_haiku(system, prompt)   # Haiku is now standard for all check types
        if "INSUFFICIENT SOURCE INFORMATION" in response:
            return []
        raw_checks = parse_toml_list(response, 'check')
        # Reconstruct answer_requirements from flat TOML fields
        checks = []
        for chk in raw_checks[:4]:
            chk['answer_requirements'] = {
                'required_ideas': chk.pop('required_ideas', []),
                'wrong_statements': chk.pop('wrong_statements', []),
            }
            checks.append(chk)
        return checks
    except Exception as e:
        logger.warning(f"Check generation failed: {e}")
        return []


async def quality_filter_checks(checks: list) -> list:
    if not checks:
        return []

    system = "You are reviewing automatically generated study questions."

    # Serialize checks summary for the prompt (compact, language-agnostic)
    checks_summary = "\n".join([
        f"[{i+1}] type={c.get('type','?')} | prompt: {c.get('prompt','')[:120]}"
        for i, c in enumerate(checks)
    ])

    prompt = f"""Review these automatically generated study questions.

IMPORTANT: Respond in the same language as the questions.

For each question decide: KEEP, EDIT, or DROP.
- KEEP: Clear, tests one idea, realistic exam question.
- EDIT: Fix it — provide improved prompt/answer only if needed.
- DROP: Ambiguous, untestable, or off-topic.

Questions:
{checks_summary}

Return ONLY valid TOML using [[r]] array-of-tables. Example:

[[r]]
decision = "KEEP"
short_reason = "Klar und präzise."

[[r]]
decision = "EDIT"
short_reason = "Zu vage."
prompt = "Überarbeitete Frage?"
expected_answer = "Überarbeitete Antwort."

[[r]]
decision = "DROP"
short_reason = "Nicht testbar."

Return ONLY valid TOML, no other text."""

    try:
        response = await call_haiku(system, prompt)
        results = parse_toml_list(response, 'r')
        approved = []
        for i, result in enumerate(results):
            if i >= len(checks):
                break
            decision = result.get("decision", "DROP").upper()
            if decision == "KEEP":
                approved.append(checks[i])
            elif decision == "EDIT":
                edited = dict(checks[i])
                if result.get("prompt"):
                    edited["prompt"] = result["prompt"]
                if result.get("expected_answer"):
                    edited["expected_answer"] = result["expected_answer"]
                if result.get("short_explanation"):
                    edited["short_explanation"] = result["short_explanation"]
                approved.append(edited)
            # DROP: discard
        return approved
    except Exception as e:
        logger.warning(f"Quality filter failed, keeping all: {e}")
        return checks


async def generate_micro_fix(concept: dict, check: dict, user_answer: str) -> dict:
    system = "You are a concise expert tutor diagnosing student misunderstandings."
    prompt = f"""A student answered a question incorrectly.

Concept:
Title: {concept.get('title', '')}
Definition: {concept.get('short_definition', '')}
Common mistake: {concept.get('common_mistake', '')}

Question:
{check.get('prompt', '')}

Student answer:
{user_answer}

Correct answer:
{check.get('expected_answer', '')}

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

Return ONLY valid JSON, no other text."""

    try:
        response = await call_claude(system, prompt)
        return extract_json(response)
    except Exception as e:
        logger.warning(f"Micro-fix failed: {e}")
        return {
            "misunderstanding": "Review the concept carefully.",
            "corrective_check": f"Recall: {check.get('expected_answer', '')}",
            "memory_anchor": check.get('explanation', ''),
        }


async def generate_session_debrief(wrong_items: list) -> dict:
    """Generate Session Debrief from actual wrong-answer data only. No hallucination."""
    if not wrong_items:
        return {"top_gaps": [], "pattern": None}

    system = (
        "You are analyzing a student's learning session performance. "
        "Use ONLY the session data provided below. "
        "Do NOT introduce new concepts. "
        "Do NOT rely on prior knowledge. "
        "If no clear pattern exists, return null for pattern."
    )
    prompt = f"""You are analyzing a student's learning session.

Use ONLY the session data provided below.
Do NOT introduce new concepts.
Do NOT rely on prior knowledge.
If no clear pattern exists, return null for pattern.

Session wrong answers:
{json.dumps(wrong_items, ensure_ascii=False, indent=2)}

Each item contains:
- concept_name: the concept being tested
- check_type: type of check failed (recall/contrast/scenario/error)
- expected_answer: the correct answer
- user_answer: what the student wrote (may be empty)
- common_mistake: the known typical misconception for this concept

Your task:
1. Identify top knowledge gaps (max 3), ranked by severity. For each gap write:
   - concept_name
   - risk_reason: one sentence explaining why this gap is dangerous
   - detected_issue: what specifically went wrong, derived from the data

2. If there is ONE clear dominant error pattern across multiple mistakes, describe it in one sentence.
   If no clear pattern: return null.
   Do NOT invent a pattern from a single mistake.

Return ONLY valid JSON:
{{
  "top_gaps": [
    {{
      "concept_name": "...",
      "risk_reason": "...",
      "detected_issue": "..."
    }}
  ],
  "pattern": "one sentence or null"
}}"""

    try:
        response = await call_claude(system, prompt)
        result = extract_json(response)
        # Validate structure
        if not isinstance(result, dict):
            return {"top_gaps": [], "pattern": None}
        result["top_gaps"] = result.get("top_gaps", [])[:3]
        # Normalize pattern: null string → None
        if result.get("pattern") in ("null", "None", ""):
            result["pattern"] = None
        return result
    except Exception as e:
        logger.warning(f"Debrief generation failed: {e}")
        # Graceful fallback: build from raw data, no AI
        gaps = []
        seen = set()
        for item in wrong_items[:3]:
            cname = item.get("concept_name", "")
            if cname and cname not in seen:
                seen.add(cname)
                gaps.append({
                    "concept_name": cname,
                    "risk_reason": item.get("common_mistake") or "Review this concept.",
                    "detected_issue": f"Failed {item.get('check_type', 'recall')} check.",
                })
        return {"top_gaps": gaps, "pattern": None}


async def _extract_claims(question: str, expected_answer: str, user_answer: str) -> list:
    """
    Step 1 of answer evaluation.
    Extracts ONLY explicit claims from the student's answer.
    Uses verbatim prompt per ANSWER_CLAIM_EXTRACTION prompt spec.
    The model is strictly forbidden from judging correctness or adding information.
    Output: {"claims": [...]} — no other fields allowed.
    """
    system = (
        "You are a neutral text analysis assistant.\n"
        "Your task is to extract explicit factual claims from a student's answer exactly as written.\n"
        "You are NOT a grader.\n"
        "You are NOT a teacher.\n"
        "You are NOT allowed to correct or improve the answer."
    )
    prompt = f"""INSTRUCTIONS (STRICT):
Extract ONLY statements that are explicitly present in the student's answer.
Do NOT infer unstated meaning.
Do NOT judge correctness.
Do NOT add missing information.
Do NOT rephrase or improve the wording.
Do NOT reference external knowledge.
If the answer contains no clear claims, return an empty list.
If the answer is vague, extract the vague claim as written.
You must remain conservative.
If something is unclear, do NOT guess.

OUTPUT FORMAT (REQUIRED):
Return a JSON object with ONLY this structure:
{{"claims": ["claim 1", "claim 2"]}}
No additional fields are allowed.

---

Question:
{question}

Expected core answer (for context only — do NOT use this to fill in missing claims):
{expected_answer}

Student's answer:
{user_answer}"""

    try:
        response = await call_claude(system, prompt)
        result = extract_json(response)
        claims = result.get("claims", [])
        # Strict: only accept a list of strings, reject any extra fields
        if not isinstance(claims, list):
            return []
        return [str(c) for c in claims if c]
    except Exception as e:
        logger.warning(f"Claim extraction failed: {e}")
        return []


async def _match_claims_to_requirements(
    claims: list,
    required_ideas: list,
    wrong_statements: list,
) -> dict:
    """
    Step 2 of answer evaluation — deterministic requirement matching.
    Given the extracted claims, checks which required ideas are covered
    and whether any wrong statements were made.
    Binary YES/NO per requirement — not an overall judgment.
    """
    if not claims:
        return {
            "covered_ideas": [],
            "missing_ideas": required_ideas,
            "wrong_ideas_stated": [],
        }

    system = (
        "You are performing a mechanical requirement-matching task. "
        "You are given a list of extracted claims and a list of requirements. "
        "For each requirement, determine if any claim in the list covers it semantically. "
        "You are NOT judging the quality of the answer overall. "
        "You are ONLY checking if specific ideas are present or absent. "
        "Return binary results only — no explanations, no scores."
    )
    prompt = f"""Given these extracted claims and requirements, perform binary matching.

Extracted claims (what the student explicitly stated):
{json.dumps(claims)}

Required ideas (must be present for a correct answer):
{json.dumps(required_ideas)}

Wrong statements to detect (must NOT appear in a correct answer):
{json.dumps(wrong_statements)}

For each required idea: is any claim semantically covering it? (semantically, not just literally)
For each wrong statement: does any claim express this incorrect idea?

Return ONLY valid JSON:
{{
  "covered_ideas": ["required ideas that were covered by at least one claim"],
  "missing_ideas": ["required ideas that were NOT covered by any claim"],
  "wrong_ideas_stated": ["wrong statements that appeared in the claims"]
}}"""

    try:
        response = await call_claude(system, prompt)
        result = extract_json(response)
        return {
            "covered_ideas": result.get("covered_ideas", []),
            "missing_ideas": result.get("missing_ideas", required_ideas),
            "wrong_ideas_stated": result.get("wrong_ideas_stated", []),
        }
    except Exception as e:
        logger.warning(f"Requirement matching failed: {e}")
        return {
            "covered_ideas": [],
            "missing_ideas": required_ideas,
            "wrong_ideas_stated": [],
        }


# ─── Risk & Session Engine ────────────────────────────────────────────────────
EXAM_WEIGHT_MAP = {"low": 0.5, "medium": 1.0, "high": 1.5}
SESSION_SIZES = {10: 8, 20: 15, 30: 22}


def calculate_recall_probability(stability: float, last_reviewed_at) -> float:
    if last_reviewed_at is None:
        return 0.0
    if isinstance(last_reviewed_at, str):
        last_reviewed_at = datetime.fromisoformat(last_reviewed_at.replace("Z", "+00:00"))
    if last_reviewed_at.tzinfo is None:
        last_reviewed_at = last_reviewed_at.replace(tzinfo=timezone.utc)
    days_since = (datetime.now(timezone.utc) - last_reviewed_at).total_seconds() / 86400
    return round(math.exp(-days_since / max(stability, 0.1)), 4)


def calculate_risk(recall_probability: float, exam_weight: float, dependency_weight: float = 1.0) -> float:
    return round((1.0 - recall_probability) * exam_weight * dependency_weight, 4)


def days_until_exam(exam_date_str: Optional[str]) -> Optional[int]:
    """Return days until exam (0 = today, negative = past). None if no date set."""
    if not exam_date_str:
        return None
    try:
        exam_dt = datetime.fromisoformat(exam_date_str.replace("Z", "+00:00"))
        if exam_dt.tzinfo is None:
            exam_dt = exam_dt.replace(tzinfo=timezone.utc)
        delta = exam_dt.date() - datetime.now(timezone.utc).date()
        return delta.days
    except Exception:
        return None


def urgency_multiplier(exam_date_str: Optional[str]) -> float:
    """
    Urgency multiplier for risk scores based on days until exam.
    >30 days  → 1.0 (no boost)
    15–30     → 1.3
    7–14      → 1.6
    3–6       → 2.0
    <3        → 2.5
    """
    days = days_until_exam(exam_date_str)
    if days is None or days > 30:
        return 1.0
    if days >= 15:
        return 1.3
    if days >= 7:
        return 1.6
    if days >= 3:
        return 2.0
    return 2.5  # 0-2 days (or overdue)


def update_stability(stability: float, rating: str) -> float:
    multipliers = {"again": 0.7, "hard": 1.1, "good": 1.3, "easy": 2.0}
    return round(max(0.1, stability * multipliers.get(rating, 1.0)), 4)


def select_check_type(recall_probability: float) -> str:
    if recall_probability < 0.6:
        return "recall"
    elif recall_probability <= 0.8:
        return "contrast"
    else:
        return "scenario"


async def get_or_create_ucs(user_id: str, concept_id: str, exam_weight: float) -> dict:
    ucs = await ucs_col.find_one({"user_id": user_id, "concept_id": concept_id})
    if not ucs:
        ucs = {
            "user_id": user_id,
            "concept_id": concept_id,
            "stability": 1.0,
            "difficulty": 0.3,
            "recall_probability": 0.0,
            "risk": calculate_risk(0.0, exam_weight),
            "last_reviewed_at": None,
            "created_at": datetime.now(timezone.utc),
        }
        result = await ucs_col.insert_one(ucs)
        ucs["_id"] = result.inserted_id
    return ucs


# ─── Pydantic Models ──────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class CreatePackRequest(BaseModel):
    title: str
    description: str = ""
    domain: str = ""


class ExamDateRequest(BaseModel):
    exam_date: Optional[str] = None  # ISO date YYYY-MM-DD or null to clear


class UpdateConceptRequest(BaseModel):
    title: Optional[str] = None
    short_definition: Optional[str] = None
    common_mistake: Optional[str] = None
    exam_weight: Optional[str] = None  # "low" | "medium" | "high"


class StartSessionRequest(BaseModel):
    pack_id: str
    duration_minutes: int = 10
    doc_type_filter: Optional[str] = None  # None or "all" = no filter


class AnswerRequest(BaseModel):
    session_id: str
    concept_id: str
    check_id: str
    rating: str  # "again" | "hard" | "good" | "easy"
    user_answer: str = ""


class DrillSessionRequest(BaseModel):
    concept_ids: list  # top 1-2 concept IDs from debrief


class EvaluateAnswerRequest(BaseModel):
    check_id: str
    user_answer: str


class UploadChunkRequest(BaseModel):
    upload_id: str
    chunk_index: int
    total_chunks: int
    data: str  # base64-encoded chunk bytes


class FinalizeUploadRequest(BaseModel):
    upload_id: str
    pack_id: str
    filename: str


# ─── Auth Routes ──────────────────────────────────────────────────────────────
@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    if await users_col.find_one({"email": req.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = {
        "email": req.email,
        "password_hash": hash_password(req.password),
        "created_at": datetime.now(timezone.utc),
    }
    result = await users_col.insert_one(user)
    token = create_token(str(result.inserted_id))
    return {"token": token, "user_id": str(result.inserted_id), "email": req.email}


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = await users_col.find_one({"email": req.email})
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(str(user["_id"]))
    return {"token": token, "user_id": str(user["_id"]), "email": user["email"]}


# ─── Study Pack Routes ────────────────────────────────────────────────────────
@app.post("/api/packs")
async def create_pack(req: CreatePackRequest, user=Depends(get_current_user)):
    pack = {
        "owner_id": str(user["_id"]),
        "title": req.title,
        "description": req.description,
        "domain": req.domain,
        "visibility": "private",
        "version": 1,
        "concept_count": 0,
        "created_at": datetime.now(timezone.utc),
    }
    result = await packs_col.insert_one(pack)
    pack["id"] = str(result.inserted_id)
    pack.pop("_id", None)
    pack["created_at"] = pack["created_at"].isoformat()
    return pack


@app.get("/api/packs")
async def list_packs(user=Depends(get_current_user)):
    cursor = packs_col.find({"owner_id": str(user["_id"])}).sort("created_at", -1)
    packs = []
    async for p in cursor:
        packs.append(doc_id(p))
    return packs


@app.get("/api/packs/{pack_id}")
async def get_pack(pack_id: str, user=Depends(get_current_user)):
    try:
        pack = await packs_col.find_one({"_id": ObjectId(pack_id), "owner_id": str(user["_id"])})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pack ID")
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    return doc_id(pack)


@app.patch("/api/packs/{pack_id}/exam-date")
async def set_exam_date(pack_id: str, req: ExamDateRequest, user=Depends(get_current_user)):
    """Set or clear the exam date for a study pack."""
    try:
        pack = await packs_col.find_one({"_id": ObjectId(pack_id), "owner_id": str(user["_id"])})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pack ID")
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    if req.exam_date is None:
        await packs_col.update_one({"_id": ObjectId(pack_id)}, {"$unset": {"exam_date": ""}})
    else:
        # Validate ISO date format
        try:
            datetime.fromisoformat(req.exam_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
        await packs_col.update_one({"_id": ObjectId(pack_id)}, {"$set": {"exam_date": req.exam_date}})

    updated = await packs_col.find_one({"_id": ObjectId(pack_id)})
    return doc_id(updated)


# ─── Upload & AI Pipeline (Background Task) ──────────────────────────────────

async def _process_single_chunk(chunk: str, pack_id: str, job_id: str,
                               doc_type: str = "", source_name: str = "",
                               domain_context: str = "") -> list:
    """Extract concepts + checks from one chunk and persist to DB."""
    extracted = await extract_concepts_from_chunk(chunk, domain_context)
    saved = []
    for concept_data in extracted:
        concept_doc = {
            "study_pack_id": pack_id,
            "title": concept_data.get("concept_title", concept_data.get("title", "Unknown")),
            "short_definition": concept_data.get("short_definition", ""),
            "common_mistake": concept_data.get("common_mistake", ""),
            "exam_weight": 1.0,
            "exam_weight_label": "medium",
            "prerequisite_concepts": concept_data.get("prerequisite_concepts", []),
            "doc_type": doc_type,
            "source_name": source_name,
            "created_at": datetime.now(timezone.utc),
        }
        c_result = await concepts_col.insert_one(concept_doc)
        concept_id = str(c_result.inserted_id)

        raw_checks = await generate_checks_for_concept(concept_data)
        if raw_checks:
            approved_checks = await quality_filter_checks(raw_checks)
            for chk in approved_checks:
                raw_reqs = chk.get("answer_requirements", {})
                if isinstance(raw_reqs, dict):
                    normalized_reqs = raw_reqs
                elif isinstance(raw_reqs, list):
                    normalized_reqs = {"required_ideas": raw_reqs, "wrong_statements": []}
                else:
                    normalized_reqs = {"required_ideas": [], "wrong_statements": []}
                await checks_col.insert_one({
                    "concept_id": concept_id,
                    "type": chk.get("type", "recall"),
                    "prompt": chk.get("prompt", ""),
                    "expected_answer": chk.get("expected_answer", ""),
                    "explanation": chk.get("short_explanation", chk.get("explanation", "")),
                    "difficulty_hint": "medium",
                    "answer_requirements": normalized_reqs,
                })

        concept_doc["id"] = concept_id
        concept_doc.pop("_id", None)
        concept_doc["created_at"] = concept_doc["created_at"].isoformat()
        saved.append(concept_doc)

    # Update live progress counters
    if saved:
        await jobs_col.update_one(
            {"_id": ObjectId(job_id)},
            {"$inc": {"chunks_processed": 1, "concepts_extracted": len(saved)}}
        )
    return saved


async def _merge_similar_concepts(pack_id: str) -> dict:
    """
    Conservative post-processing deduplication.
    Finds concept pairs with 2+ overlapping title keywords and asks the LLM
    whether they are truly the same idea or just related.
    Rule: MERGE only if identical core idea. When in doubt: KEEP_BOTH.
    """
    def key_words(title: str) -> set:
        stop = {
            'die', 'der', 'das', 'ein', 'eine', 'und', 'von', 'des', 'dem', 'den',
            'the', 'of', 'and', 'a', 'an', 'in', 'für', 'vs', 'im', 'bei', 'als',
            'zum', 'zur', 'nach', 'über', 'unter', 'bei', 'mit',
        }
        return {w.lower() for w in re.findall(r'\b\w{4,}\b', title) if w.lower() not in stop}

    all_concepts = []
    async for c in concepts_col.find({"study_pack_id": pack_id}, {"_id": 1, "title": 1, "short_definition": 1}):
        all_concepts.append(c)

    if len(all_concepts) < 2:
        return {"checked": 0, "merged": 0}

    # Find candidate pairs with 2+ shared meaningful title words
    candidate_pairs = []
    for i in range(len(all_concepts)):
        for j in range(i + 1, len(all_concepts)):
            k1 = key_words(all_concepts[i].get('title', ''))
            k2 = key_words(all_concepts[j].get('title', ''))
            if k1 and k2 and len(k1 & k2) >= 2:
                candidate_pairs.append((all_concepts[i], all_concepts[j]))

    if not candidate_pairs:
        return {"checked": 0, "merged": 0}

    to_delete: set = set()
    merged_count = 0
    BATCH_SIZE = 15

    for start in range(0, len(candidate_pairs), BATCH_SIZE):
        batch = [
            (c1, c2) for c1, c2 in candidate_pairs[start:start + BATCH_SIZE]
            if str(c1['_id']) not in to_delete and str(c2['_id']) not in to_delete
        ]
        if not batch:
            continue

        pairs_text = "\n".join([
            f"Pair {i + 1}:\n  A: \"{c1['title']}\" — {c1.get('short_definition', '')[:120]}\n"
            f"  B: \"{c2['title']}\" — {c2.get('short_definition', '')[:120]}"
            for i, (c1, c2) in enumerate(batch)
        ])

        system = "You are a concept deduplication assistant. Be conservative."
        prompt = f"""Review each pair of learning concepts and decide whether to merge them.

STRICT RULE: Only mark MERGE if A and B express the EXACT same core idea in different words.
If they are related, sequential, or complementary — mark KEEP_BOTH.
When in doubt: KEEP_BOTH. Granularity is valuable for learners.

{pairs_text}

Return ONLY valid TOML using [[m]] array-of-tables:

[[m]]
pair = 1
decision = "MERGE"
keep = "A"

[[m]]
pair = 2
decision = "KEEP_BOTH"

Return ONLY valid TOML, no other text."""

        try:
            response = await call_haiku(system, prompt)  # Merge decisions are mechanical
            decisions = parse_toml_list(response, 'm')
            for d in decisions:
                idx = d.get("pair", 0) - 1
                if idx < 0 or idx >= len(batch):
                    continue
                if d.get("decision") == "MERGE":
                    c1, c2 = batch[idx]
                    keep = d.get("keep", "A")
                    delete_id = str(c2["_id"]) if keep == "A" else str(c1["_id"])
                    if delete_id not in to_delete:
                        to_delete.add(delete_id)
                        merged_count += 1
        except Exception as e:
            logger.warning(f"Merge batch failed: {e}")

    for cid in to_delete:
        try:
            await concepts_col.delete_one({"_id": ObjectId(cid)})
            await checks_col.delete_many({"concept_id": cid})
        except Exception as e:
            logger.warning(f"Delete duplicate concept {cid}: {e}")

    return {"checked": len(candidate_pairs), "merged": merged_count}


async def _run_ai_pipeline(job_id: str, pack_id: str, raw_text: str,
                           source_name: str = "", doc_type: str = ""):
    """Background task: extract concepts + checks from ALL chunks (no hard limit).
    Up to 2 chunks processed in parallel to balance speed vs. API rate limits.
    """
    try:
        # Detect document type if not provided
        if not doc_type:
            doc_type = await detect_document_type(raw_text)

        # Fetch pack title for domain relevance filtering
        pack_doc = await packs_col.find_one({"_id": ObjectId(pack_id)}, {"_id": 0, "title": 1})
        domain_context = pack_doc.get("title", "") if pack_doc else ""

        await jobs_col.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {
                "status": "processing",
                "started_at": datetime.now(timezone.utc),
                "doc_type": doc_type,
                "source_name": source_name,
            }}
        )

        chunks = chunk_text(raw_text)
        if not chunks:
            await jobs_col.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"status": "failed", "error": "Text too short to process"}}
            )
            return

        # Store total chunk count upfront so SSE can show "Chunk X / N"
        await jobs_col.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"chunks_total": len(chunks)}}
        )

        # Process all chunks, 3 at a time (Haiku on extraction = more headroom vs rate limits)
        semaphore = asyncio.Semaphore(3)

        async def bounded(chunk):
            async with semaphore:
                return await _process_single_chunk(chunk, pack_id, job_id, doc_type, source_name, domain_context)

        results = await asyncio.gather(*[bounded(c) for c in chunks], return_exceptions=True)

        saved_concepts = []
        for res in results:
            if isinstance(res, list):
                saved_concepts.extend(res)
            elif isinstance(res, Exception):
                logger.warning(f"Chunk processing error: {res}")

        concepts_before_merge = len(saved_concepts)
        avg_per_chunk = round(concepts_before_merge / len(chunks), 2) if chunks else 0

        # ── Merge step: remove true duplicates (conservative) ──
        merge_stats = await _merge_similar_concepts(pack_id)
        concepts_after_merge = concepts_before_merge - merge_stats["merged"]

        total_concepts = await concepts_col.count_documents({"study_pack_id": pack_id})
        await packs_col.update_one(
            {"_id": ObjectId(pack_id)},
            {"$set": {"concept_count": total_concepts}}
        )

        if concepts_after_merge == 0:
            await jobs_col.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"status": "failed", "error": "No concepts could be extracted. Try more detailed content."}}
            )
        else:
            risk_summary = []
            seen = set()
            for c in saved_concepts:
                mistake = c.get("common_mistake", "").strip()
                title = c.get("title", "")
                if mistake and title and title not in seen:
                    risk_summary.append({"concept": title, "misconception": mistake})
                    seen.add(title)

            await jobs_col.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {
                    "status": "complete",
                    "completed_at": datetime.now(timezone.utc),
                    "concepts_extracted": concepts_after_merge,
                    "chunks_processed": len(chunks),
                    "concepts": saved_concepts,
                    "risk_summary": risk_summary[:5],
                    # ── Before/After quality report ──
                    "quality_report": {
                        "chunks_total": len(chunks),
                        "concepts_before_merge": concepts_before_merge,
                        "concepts_after_merge": concepts_after_merge,
                        "duplicates_merged": merge_stats["merged"],
                        "duplicate_pairs_checked": merge_stats["checked"],
                        "avg_concepts_per_chunk": avg_per_chunk,
                    },
                }}
            )
    except Exception as e:
        logger.error(f"AI pipeline failed for job {job_id}: {e}")
        await jobs_col.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"status": "failed", "error": str(e)}}
        )


@app.post("/api/packs/{pack_id}/upload")
async def upload_material(
    background_tasks: BackgroundTasks,
    pack_id: str,
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    user=Depends(get_current_user),
):
    try:
        pack = await packs_col.find_one({"_id": ObjectId(pack_id), "owner_id": str(user["_id"])})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pack ID")
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    raw_text = ""
    source_name = ""
    if file and file.filename:
        content = await file.read()
        source_name = file.filename
        if file.filename.lower().endswith(".pdf"):
            try:
                raw_text = await asyncio.to_thread(_extract_text_from_pdf_sync, content)
            except RuntimeError as e:
                raise HTTPException(status_code=400, detail=str(e))
        else:
            raw_text = content.decode("utf-8", errors="ignore")
    elif text:
        raw_text = text
        source_name = "Text"
    else:
        raise HTTPException(status_code=400, detail="No file or text provided")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No text content found")

    # Create job document
    job_doc = {
        "pack_id": pack_id,
        "user_id": str(user["_id"]),
        "status": "queued",
        "source_name": source_name,
        "doc_type": "",
        "created_at": datetime.now(timezone.utc),
        "started_at": None,
        "completed_at": None,
        "concepts_extracted": 0,
        "chunks_processed": 0,
        "concepts": [],
        "error": None,
    }
    result = await jobs_col.insert_one(job_doc)
    job_id = str(result.inserted_id)

    # Run AI pipeline in background (non-blocking)
    background_tasks.add_task(_run_ai_pipeline, job_id, pack_id, raw_text, source_name)

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str, user=Depends(get_current_user)):
    try:
        job = await jobs_col.find_one({
            "_id": ObjectId(job_id),
            "user_id": str(user["_id"]),
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return doc_id(job)


@app.get("/api/jobs/{job_id}/stream")
async def stream_job_progress(job_id: str, token: str):
    """Server-Sent Events stream for real-time job progress."""
    from fastapi.responses import StreamingResponse

    # Validate token manually (SSE can't use Depends for auth)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Invalid token")
    except Exception:
        async def _err():
            yield "data: {\"error\": \"unauthorized\"}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    async def _event_generator():
        last_state = None
        for _ in range(300):  # max ~10 min (2s × 300)
            try:
                job = await jobs_col.find_one(
                    {"_id": ObjectId(job_id), "user_id": user_id},
                    {"status": 1, "chunks_processed": 1, "chunks_total": 1,
                     "concepts_extracted": 1, "doc_type": 1, "quality_report": 1, "error": 1}
                )
                if not job:
                    break

                state = {
                    "status": job.get("status"),
                    "chunks_processed": job.get("chunks_processed", 0),
                    "chunks_total": job.get("chunks_total", 0),
                    "concepts_extracted": job.get("concepts_extracted", 0),
                    "doc_type": job.get("doc_type", ""),
                    "quality_report": job.get("quality_report"),
                    "error": job.get("error"),
                }

                if state != last_state:
                    yield f"data: {json.dumps(state)}\n\n"
                    last_state = state

                if state["status"] in ("complete", "failed"):
                    break

                await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"SSE error: {e}")
                break

        yield "data: {\"status\": \"stream_end\"}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Chunked Upload Endpoints ─────────────────────────────────────────────────

@app.post("/api/upload/chunk")
async def receive_chunk(req: UploadChunkRequest, user=Depends(get_current_user)):
    """Receive one chunk of a multi-part file upload."""
    upload_dir = os.path.join(UPLOAD_TEMP_DIR, req.upload_id)
    os.makedirs(upload_dir, exist_ok=True)
    chunk_path = os.path.join(upload_dir, f"chunk_{req.chunk_index:05d}.bin")
    chunk_data = base64.b64decode(req.data)
    with open(chunk_path, "wb") as f:
        f.write(chunk_data)
    return {"received": req.chunk_index, "upload_id": req.upload_id}


@app.post("/api/upload/finalize")
async def finalize_upload(
    req: FinalizeUploadRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """Assemble uploaded chunks, extract text, and start the AI pipeline."""
    try:
        pack = await packs_col.find_one({"_id": ObjectId(req.pack_id), "owner_id": str(user["_id"])})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pack ID")
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    upload_dir = os.path.join(UPLOAD_TEMP_DIR, req.upload_id)
    if not os.path.exists(upload_dir):
        raise HTTPException(status_code=400, detail="Upload session not found — please retry")

    chunk_files = sorted(f for f in os.listdir(upload_dir) if f.startswith("chunk_"))
    if not chunk_files:
        raise HTTPException(status_code=400, detail="No chunks received")

    # Assemble
    assembled = b"".join(
        open(os.path.join(upload_dir, cf), "rb").read() for cf in chunk_files
    )
    shutil.rmtree(upload_dir, ignore_errors=True)  # clean up temp files

    # Extract text
    try:
        if req.filename.lower().endswith(".pdf"):
            raw_text = await asyncio.to_thread(_extract_text_from_pdf_sync, assembled)
        else:
            raw_text = assembled.decode("utf-8", errors="ignore")
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No text content found in file")

    job_doc = {
        "pack_id": req.pack_id,
        "user_id": str(user["_id"]),
        "status": "queued",
        "source_name": req.filename,
        "doc_type": "",
        "created_at": datetime.now(timezone.utc),
        "started_at": None,
        "completed_at": None,
        "concepts_extracted": 0,
        "chunks_processed": 0,
        "concepts": [],
        "error": None,
    }
    result = await jobs_col.insert_one(job_doc)
    job_id = str(result.inserted_id)
    background_tasks.add_task(_run_ai_pipeline, job_id, req.pack_id, raw_text, req.filename)
    return {"job_id": job_id, "status": "queued"}


# ─── URL Upload Endpoint ──────────────────────────────────────────────────────

class UrlUploadRequest(BaseModel):
    pack_id: str
    url: str


@app.post("/api/upload/url")
async def upload_from_url(
    req: UrlUploadRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """Fetch a public URL, extract its text, and start the AI pipeline."""
    try:
        pack = await packs_col.find_one({"_id": ObjectId(req.pack_id), "owner_id": str(user["_id"])})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pack ID")
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    try:
        raw_text = await asyncio.to_thread(_fetch_url_text_sync, req.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not fetch URL: {str(e)}")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No readable text found at this URL")

    # Use domain as source name
    from urllib.parse import urlparse
    source_name = urlparse(req.url).netloc or req.url

    job_doc = {
        "pack_id": req.pack_id,
        "user_id": str(user["_id"]),
        "status": "queued",
        "source_name": source_name,
        "source_url": req.url,
        "doc_type": "",
        "created_at": datetime.now(timezone.utc),
        "started_at": None,
        "completed_at": None,
        "concepts_extracted": 0,
        "chunks_processed": 0,
        "concepts": [],
        "error": None,
    }
    result = await jobs_col.insert_one(job_doc)
    job_id = str(result.inserted_id)
    background_tasks.add_task(_run_ai_pipeline, job_id, req.pack_id, raw_text, source_name)
    return {"job_id": job_id, "status": "queued"}


class TextUploadRequest(BaseModel):
    pack_id: str
    content: str
    source_name: str = "Text Upload"


@app.post("/api/upload/text")
async def upload_from_text(
    req: TextUploadRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """Accept raw text content and start the AI pipeline (used for testing / benchmarks)."""
    try:
        pack = await packs_col.find_one({"_id": ObjectId(req.pack_id), "owner_id": str(user["_id"])})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pack ID")
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    raw_text = req.content.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Empty content")

    job_doc = {
        "pack_id": req.pack_id,
        "user_id": str(user["_id"]),
        "status": "queued",
        "source_name": req.source_name,
        "doc_type": "",
        "created_at": datetime.now(timezone.utc),
        "started_at": None,
        "completed_at": None,
        "concepts_extracted": 0,
        "chunks_processed": 0,
        "concepts": [],
        "error": None,
    }
    result = await jobs_col.insert_one(job_doc)
    job_id = str(result.inserted_id)
    background_tasks.add_task(_run_ai_pipeline, job_id, req.pack_id, raw_text, req.source_name)
    return {"job_id": job_id, "status": "queued"}


# ─── Concept Routes ───────────────────────────────────────────────────────────
@app.get("/api/packs/{pack_id}/concepts")
async def list_concepts(pack_id: str, user=Depends(get_current_user)):
    try:
        pack = await packs_col.find_one({"_id": ObjectId(pack_id), "owner_id": str(user["_id"])})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pack ID")
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    cursor = concepts_col.find({"study_pack_id": pack_id}).sort("created_at", 1)
    concepts = []
    async for c in cursor:
        ucs = await ucs_col.find_one({"user_id": str(user["_id"]), "concept_id": str(c["_id"])})
        c_out = doc_id(c)
        if ucs:
            recall = calculate_recall_probability(ucs["stability"], ucs.get("last_reviewed_at"))
            risk = calculate_risk(recall, c_out.get("exam_weight", 1.0))
            c_out["recall_probability"] = recall
            c_out["risk"] = risk
            lra = ucs.get("last_reviewed_at")
            c_out["last_reviewed_at"] = lra.isoformat() if isinstance(lra, datetime) else lra
        else:
            c_out["recall_probability"] = 0.0
            c_out["risk"] = calculate_risk(0.0, c_out.get("exam_weight", 1.0))
            c_out["last_reviewed_at"] = None
        concepts.append(c_out)
    return concepts


@app.patch("/api/concepts/{concept_id}")
async def update_concept(concept_id: str, req: UpdateConceptRequest, user=Depends(get_current_user)):
    try:
        concept = await concepts_col.find_one({"_id": ObjectId(concept_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid concept ID")
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    pack = await packs_col.find_one({"_id": ObjectId(concept["study_pack_id"]), "owner_id": str(user["_id"])})
    if not pack:
        raise HTTPException(status_code=403, detail="Not authorized")

    update = {}
    if req.title is not None:
        update["title"] = req.title
    if req.short_definition is not None:
        update["short_definition"] = req.short_definition
    if req.common_mistake is not None:
        update["common_mistake"] = req.common_mistake
    if req.exam_weight is not None:
        update["exam_weight_label"] = req.exam_weight
        update["exam_weight"] = EXAM_WEIGHT_MAP.get(req.exam_weight, 1.0)

    if update:
        await concepts_col.update_one({"_id": ObjectId(concept_id)}, {"$set": update})

    concept = await concepts_col.find_one({"_id": ObjectId(concept_id)})
    return doc_id(concept)


@app.delete("/api/concepts/{concept_id}")
async def delete_concept(concept_id: str, user=Depends(get_current_user)):
    try:
        concept = await concepts_col.find_one({"_id": ObjectId(concept_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid concept ID")
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    pack = await packs_col.find_one({"_id": ObjectId(concept["study_pack_id"]), "owner_id": str(user["_id"])})
    if not pack:
        raise HTTPException(status_code=403, detail="Not authorized")

    await concepts_col.delete_one({"_id": ObjectId(concept_id)})
    await checks_col.delete_many({"concept_id": concept_id})
    await ucs_col.delete_many({"concept_id": concept_id})

    total = await concepts_col.count_documents({"study_pack_id": concept["study_pack_id"]})
    await packs_col.update_one(
        {"_id": ObjectId(concept["study_pack_id"])},
        {"$set": {"concept_count": total}}
    )
    return {"deleted": True}


@app.post("/api/concepts/{concept_id}/report")
async def report_concept(concept_id: str, user=Depends(get_current_user)):
    """Flag a concept as irrelevant or incorrect for manual review."""
    try:
        concept = await concepts_col.find_one({"_id": ObjectId(concept_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid concept ID")
    if not concept:
        raise HTTPException(status_code=404, detail="Concept not found")

    # Verify ownership via pack
    pack = await packs_col.find_one({
        "_id": ObjectId(concept["study_pack_id"]),
        "owner_id": str(user["_id"])
    })
    if not pack:
        raise HTTPException(status_code=403, detail="Not authorized")

    await concepts_col.update_one(
        {"_id": ObjectId(concept_id)},
        {"$set": {"reported": True, "reported_at": datetime.now(timezone.utc)}}
    )
    return {"reported": True, "concept_id": concept_id}


@app.get("/api/packs/{pack_id}/reported-concepts")
async def list_reported_concepts(pack_id: str, user=Depends(get_current_user)):
    """Return all reported concepts for a study pack."""
    pack = await packs_col.find_one({"_id": ObjectId(pack_id), "owner_id": str(user["_id"])})
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    docs = await concepts_col.find(
        {"study_pack_id": pack_id, "reported": True},
        {"_id": 1, "title": 1, "short_definition": 1, "common_mistake": 1,
         "doc_type": 1, "reported_at": 1}
    ).sort("reported_at", -1).to_list(length=None)

    result = []
    for d in docs:
        reported_at = d.get("reported_at")
        result.append({
            "id": str(d["_id"]),
            "title": d.get("title", ""),
            "short_definition": d.get("short_definition", ""),
            "common_mistake": d.get("common_mistake", ""),
            "doc_type": d.get("doc_type", ""),
            "reported_at": reported_at.isoformat() if reported_at else None,
        })
    return result


class BulkConceptRequest(BaseModel):
    concept_ids: List[str]


@app.post("/api/packs/{pack_id}/concepts/bulk-delete")
async def bulk_delete_concepts(pack_id: str, req: BulkConceptRequest, user=Depends(get_current_user)):
    """Delete multiple concepts at once."""
    pack = await packs_col.find_one({"_id": ObjectId(pack_id), "owner_id": str(user["_id"])})
    if not pack:
        raise HTTPException(status_code=403, detail="Not authorized")

    object_ids = []
    for cid in req.concept_ids:
        try:
            object_ids.append(ObjectId(cid))
        except Exception:
            pass

    if not object_ids:
        return {"deleted": 0}

    await concepts_col.delete_many({"_id": {"$in": object_ids}, "study_pack_id": pack_id})
    await checks_col.delete_many({"concept_id": {"$in": req.concept_ids}})
    await ucs_col.delete_many({"concept_id": {"$in": req.concept_ids}})

    total = await concepts_col.count_documents({"study_pack_id": pack_id})
    await packs_col.update_one({"_id": ObjectId(pack_id)}, {"$set": {"concept_count": total}})

    return {"deleted": len(object_ids)}


@app.post("/api/packs/{pack_id}/concepts/bulk-dismiss")
async def bulk_dismiss_reports(pack_id: str, req: BulkConceptRequest, user=Depends(get_current_user)):
    """Clear the 'reported' flag from multiple concepts (mark as reviewed / false alarm)."""
    pack = await packs_col.find_one({"_id": ObjectId(pack_id), "owner_id": str(user["_id"])})
    if not pack:
        raise HTTPException(status_code=403, detail="Not authorized")

    object_ids = []
    for cid in req.concept_ids:
        try:
            object_ids.append(ObjectId(cid))
        except Exception:
            pass

    if not object_ids:
        return {"dismissed": 0}

    await concepts_col.update_many(
        {"_id": {"$in": object_ids}, "study_pack_id": pack_id},
        {"$set": {"reported": False}, "$unset": {"reported_at": ""}}
    )
    return {"dismissed": len(object_ids)}


# ─── Session Routes ───────────────────────────────────────────────────────────
@app.post("/api/sessions/start")
async def start_session(req: StartSessionRequest, user=Depends(get_current_user)):
    user_id = str(user["_id"])
    try:
        pack = await packs_col.find_one({"_id": ObjectId(req.pack_id), "owner_id": user_id})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pack ID")
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    concepts_list = []
    async for c in concepts_col.find({"study_pack_id": req.pack_id}):
        concepts_list.append(c)

    if not concepts_list:
        raise HTTPException(status_code=400, detail="No concepts in this pack. Upload material first.")

    # Apply doc_type filter if requested
    if req.doc_type_filter and req.doc_type_filter != "all":
        filtered = [c for c in concepts_list if c.get("doc_type") == req.doc_type_filter]
        if not filtered:
            raise HTTPException(
                status_code=400,
                detail=f"Keine Konzepte für Quelle '{req.doc_type_filter}' gefunden."
            )
        concepts_list = filtered

    # Calculate risk per concept and build prioritized queue
    exam_date_str = pack.get("exam_date")
    urgency_mult = urgency_multiplier(exam_date_str)
    prioritized = []
    for concept in concepts_list:
        concept_id = str(concept["_id"])
        ucs = await get_or_create_ucs(user_id, concept_id, concept.get("exam_weight", 1.0))
        recall = calculate_recall_probability(ucs["stability"], ucs.get("last_reviewed_at"))
        risk = round(calculate_risk(recall, concept.get("exam_weight", 1.0)) * urgency_mult, 4)

        check_type = select_check_type(recall)
        check = await checks_col.find_one({"concept_id": concept_id, "type": check_type})
        if not check:
            check = await checks_col.find_one({"concept_id": concept_id})

        if check:
            prioritized.append({
                "concept_id": concept_id,
                "check_id": str(check["_id"]),
                "risk": risk,
                "recall": recall,
            })

    if not prioritized:
        raise HTTPException(status_code=400, detail="No checks available. Upload material with more content.")

    prioritized.sort(key=lambda x: x["risk"], reverse=True)
    n = SESSION_SIZES.get(req.duration_minutes, 8)
    queue = prioritized[:n]

    session_doc = {
        "user_id": user_id,
        "pack_id": req.pack_id,
        "duration_minutes": req.duration_minutes,
        "doc_type_filter": req.doc_type_filter or "all",
        "queue": queue,
        "current_index": 0,
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
        "stats": {"again": 0, "hard": 0, "good": 0, "easy": 0},
        "total": len(queue),
        "urgency_multiplier": urgency_mult,
        "exam_date": exam_date_str,
    }
    result = await sessions_col.insert_one(session_doc)
    session_id = str(result.inserted_id)

    first = queue[0]
    concept = await concepts_col.find_one({"_id": ObjectId(first["concept_id"])})
    check = await checks_col.find_one({"_id": ObjectId(first["check_id"])})

    return {
        "session_id": session_id,
        "total": len(queue),
        "current_index": 0,
        "current_item": {
            "concept": doc_id(concept) if concept else None,
            "check": doc_id(check) if check else None,
            "position": 1,
            "total": len(queue),
        },
    }


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str, user=Depends(get_current_user)):
    try:
        session = await sessions_col.find_one({
            "_id": ObjectId(session_id),
            "user_id": str(user["_id"]),
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID")
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return doc_id(session)


@app.post("/api/sessions/answer")
async def answer_session(req: AnswerRequest, user=Depends(get_current_user)):
    user_id = str(user["_id"])
    try:
        session = await sessions_col.find_one({
            "_id": ObjectId(req.session_id),
            "user_id": user_id,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID")
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("completed_at"):
        raise HTTPException(status_code=400, detail="Session already completed")
    if req.rating not in ("again", "hard", "good", "easy"):
        raise HTTPException(status_code=400, detail="Invalid rating")

    concept = await concepts_col.find_one({"_id": ObjectId(req.concept_id)})
    check = await checks_col.find_one({"_id": ObjectId(req.check_id)})
    if not concept or not check:
        raise HTTPException(status_code=404, detail="Concept or check not found")

    # Update UserConceptState
    ucs = await get_or_create_ucs(user_id, req.concept_id, concept.get("exam_weight", 1.0))
    new_stability = update_stability(ucs["stability"], req.rating)
    new_recall = calculate_recall_probability(new_stability, datetime.now(timezone.utc))
    new_risk = calculate_risk(new_recall, concept.get("exam_weight", 1.0))

    await ucs_col.update_one(
        {"user_id": user_id, "concept_id": req.concept_id},
        {"$set": {
            "stability": new_stability,
            "recall_probability": new_recall,
            "risk": new_risk,
            "last_reviewed_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )

    # Log review event
    await review_col.insert_one({
        "user_id": user_id,
        "session_id": req.session_id,
        "concept_id": req.concept_id,
        "check_id": req.check_id,
        "rating": req.rating,
        "user_answer": req.user_answer,
        "response_time": 0,
        "created_at": datetime.now(timezone.utc),
    })

    # Update session stats and index
    new_index = session["current_index"] + 1
    await sessions_col.update_one(
        {"_id": ObjectId(req.session_id)},
        {
            "$inc": {f"stats.{req.rating}": 1},
            "$set": {"current_index": new_index},
        },
    )

    # Generate micro-fix if rated "again" and user provided answer
    micro_fix = None
    if req.rating == "again" and req.user_answer.strip():
        micro_fix = await generate_micro_fix(
            {
                "title": concept.get("title", ""),
                "short_definition": concept.get("short_definition", ""),
                "common_mistake": concept.get("common_mistake", ""),
            },
            {
                "prompt": check.get("prompt", ""),
                "expected_answer": check.get("expected_answer", ""),
                "explanation": check.get("explanation", ""),
            },
            req.user_answer,
        )

    queue = session["queue"]
    current_stats = dict(session["stats"])
    current_stats[req.rating] = current_stats.get(req.rating, 0) + 1

    if new_index >= len(queue):
        await sessions_col.update_one(
            {"_id": ObjectId(req.session_id)},
            {"$set": {"completed_at": datetime.now(timezone.utc)}},
        )
        return {
            "session_complete": True,
            "next_item": None,
            "micro_fix": micro_fix,
            "correct_answer": check.get("expected_answer"),
            "explanation": check.get("explanation"),
            "stats": current_stats,
        }

    next_item = queue[new_index]
    next_concept = await concepts_col.find_one({"_id": ObjectId(next_item["concept_id"])})
    next_check = await checks_col.find_one({"_id": ObjectId(next_item["check_id"])})

    return {
        "session_complete": False,
        "next_item": {
            "concept": doc_id(next_concept) if next_concept else None,
            "check": doc_id(next_check) if next_check else None,
            "position": new_index + 1,
            "total": len(queue),
        },
        "micro_fix": micro_fix,
        "correct_answer": check.get("expected_answer"),
        "explanation": check.get("explanation"),
        "stats": current_stats,
    }


# ─── Session Debrief Route ────────────────────────────────────────────────────
@app.get("/api/sessions/{session_id}/debrief")
async def get_session_debrief(session_id: str, user=Depends(get_current_user)):
    user_id = str(user["_id"])
    try:
        session = await sessions_col.find_one({
            "_id": ObjectId(session_id),
            "user_id": user_id,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID")
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get all review events for this session
    wrong_items = []
    async for event in review_col.find({
        "session_id": session_id,
        "user_id": user_id,
        "rating": {"$in": ["again", "hard"]},
    }):
        concept = await concepts_col.find_one({"_id": ObjectId(event["concept_id"])})
        check = await checks_col.find_one({"_id": ObjectId(event["check_id"])})
        if concept and check:
            wrong_items.append({
                "concept_id": event["concept_id"],
                "concept_name": concept.get("title", ""),
                "check_type": check.get("type", "recall"),
                "expected_answer": check.get("expected_answer", ""),
                "user_answer": event.get("user_answer", ""),
                "common_mistake": concept.get("common_mistake", ""),
                "rating": event["rating"],
            })

    # Build debrief — AI only if we have wrong answers
    debrief = await generate_session_debrief(wrong_items)

    # Top concept IDs for drill (unique, max 2)
    seen_ids = []
    for item in wrong_items:
        cid = item["concept_id"]
        if cid not in seen_ids:
            seen_ids.append(cid)
        if len(seen_ids) == 2:
            break

    return {
        "session_id": session_id,
        "wrong_count": len(wrong_items),
        "top_gaps": debrief.get("top_gaps", []),
        "pattern": debrief.get("pattern"),
        "drill_concept_ids": seen_ids,
        "can_drill": len(seen_ids) > 0,
    }


@app.post("/api/sessions/drill")
async def start_drill_session(req: DrillSessionRequest, user=Depends(get_current_user)):
    """5-minute fix drill using only recall + contrast checks for specified concepts."""
    user_id = str(user["_id"])

    if not req.concept_ids:
        raise HTTPException(status_code=400, detail="No concepts specified for drill")

    queue = []
    for concept_id in req.concept_ids[:2]:  # Max 2 concepts
        try:
            concept = await concepts_col.find_one({"_id": ObjectId(concept_id)})
        except Exception:
            continue
        if not concept:
            continue

        # Force recall first, then contrast — per spec (no scenarios, no fluff)
        for check_type in ["recall", "contrast"]:
            check = await checks_col.find_one({"concept_id": concept_id, "type": check_type})
            if check:
                queue.append({
                    "concept_id": concept_id,
                    "check_id": str(check["_id"]),
                    "risk": 1.0,  # Max risk — these are the problem areas
                    "recall": 0.0,
                    "is_drill": True,
                })

    if not queue:
        raise HTTPException(status_code=400, detail="No drill checks available for these concepts")

    session_doc = {
        "user_id": user_id,
        "pack_id": None,
        "duration_minutes": 5,
        "is_drill": True,
        "queue": queue,
        "current_index": 0,
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
        "stats": {"again": 0, "hard": 0, "good": 0, "easy": 0},
        "total": len(queue),
    }
    result = await sessions_col.insert_one(session_doc)
    session_id = str(result.inserted_id)

    first = queue[0]
    concept = await concepts_col.find_one({"_id": ObjectId(first["concept_id"])})
    check = await checks_col.find_one({"_id": ObjectId(first["check_id"])})

    return {
        "session_id": session_id,
        "total": len(queue),
        "current_index": 0,
        "is_drill": True,
        "current_item": {
            "concept": doc_id(concept) if concept else None,
            "check": doc_id(check) if check else None,
            "position": 1,
            "total": len(queue),
        },
    }


# ─── Dashboard Routes ─────────────────────────────────────────────────────────
@app.get("/api/dashboard/overview")
async def dashboard_overview(user=Depends(get_current_user)):
    user_id = str(user["_id"])

    # Get all packs owned by user
    user_pack_ids = []
    async for p in packs_col.find({"owner_id": user_id}, {"_id": 1}):
        user_pack_ids.append(str(p["_id"]))

    total_packs = len(user_pack_ids)
    total_concepts = await concepts_col.count_documents({"study_pack_id": {"$in": user_pack_ids}})

    # Build concept state summary
    all_ucs = []
    async for ucs in ucs_col.find({"user_id": user_id}):
        concept = await concepts_col.find_one({"_id": ObjectId(ucs["concept_id"])})
        if concept and concept.get("study_pack_id") in user_pack_ids:
            recall = calculate_recall_probability(ucs["stability"], ucs.get("last_reviewed_at"))
            risk = calculate_risk(recall, concept.get("exam_weight", 1.0))
            lra = ucs.get("last_reviewed_at")
            all_ucs.append({
                "concept_id": ucs["concept_id"],
                "concept_title": concept.get("title", ""),
                "stability": ucs["stability"],
                "recall_probability": recall,
                "risk": risk,
                "last_reviewed_at": lra.isoformat() if isinstance(lra, datetime) else lra,
            })

    # Also include never-reviewed concepts for weakest list
    reviewed_ids = {u["concept_id"] for u in all_ucs}
    async for c in concepts_col.find({"study_pack_id": {"$in": user_pack_ids}}):
        cid = str(c["_id"])
        if cid not in reviewed_ids:
            all_ucs.append({
                "concept_id": cid,
                "concept_title": c.get("title", ""),
                "stability": 1.0,
                "recall_probability": 0.0,
                "risk": calculate_risk(0.0, c.get("exam_weight", 1.0)),
                "last_reviewed_at": None,
            })

    avg_risk = round(sum(u["risk"] for u in all_ucs) / len(all_ucs), 3) if all_ucs else 0.0
    weakest = sorted(all_ucs, key=lambda x: x["risk"], reverse=True)[:5]

    # Session history
    sessions_list = []
    cursor = sessions_col.find(
        {"user_id": user_id, "completed_at": {"$ne": None}}
    ).sort("started_at", -1).limit(10)
    async for s in cursor:
        pack_title = "5-Min Fix Drill" if s.get("is_drill") else "Unknown"
        if not s.get("is_drill") and s.get("pack_id"):
            pack_obj = await packs_col.find_one({"_id": ObjectId(s["pack_id"])})
            pack_title = pack_obj.get("title", "Unknown") if pack_obj else "Unknown"
        started = s.get("started_at")
        completed = s.get("completed_at")
        sessions_list.append({
            "id": str(s["_id"]),
            "pack_title": pack_title,
            "duration_minutes": s.get("duration_minutes", 0),
            "total": s.get("total", 0),
            "stats": s.get("stats", {}),
            "is_drill": s.get("is_drill", False),
            "started_at": started.isoformat() if isinstance(started, datetime) else started,
            "completed_at": completed.isoformat() if isinstance(completed, datetime) else completed,
        })

    return {
        "avg_risk": avg_risk,
        "total_concepts": total_concepts,
        "total_packs": total_packs,
        "reviewed_concepts": len([u for u in all_ucs if u["last_reviewed_at"] is not None]),
        "weakest_concepts": weakest,
        "recent_sessions": sessions_list,
    }


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ─── Answer Evaluation Route ──────────────────────────────────────────────────
@app.post("/api/checks/evaluate")
async def evaluate_answer(req: EvaluateAnswerRequest, user=Depends(get_current_user)):
    """
    Conservative answer evaluation — assisted self-assessment only.
    Step 1: Extract explicit claims via LLM (no judgment allowed).
    Step 2: Deterministic matching against stored answer_requirements.
    Never overrides user's self-rating.
    """
    if not req.user_answer.strip():
        return {
            "result": "no_answer",
            "summary": "No answer written — compare with the correct answer above.",
            "covered_ideas": [],
            "missing_ideas": [],
            "wrong_ideas_stated": [],
        }

    try:
        check = await checks_col.find_one({"_id": ObjectId(req.check_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid check ID")
    if not check:
        raise HTTPException(status_code=404, detail="Check not found")

    requirements = check.get("answer_requirements", {})
    # Defensive: LLM may occasionally return a list instead of dict for this field
    if not isinstance(requirements, dict):
        requirements = {}
    required_ideas = requirements.get("required_ideas", [])
    wrong_statements = requirements.get("wrong_statements", [])

    # No requirements stored (older check without requirements field)
    if not required_ideas:
        return {
            "result": "no_requirements",
            "summary": "Compare your answer with the correct answer above.",
            "covered_ideas": [],
            "missing_ideas": [],
            "wrong_ideas_stated": [],
        }

    # ── Step 1: Extract explicit claims (verbatim extraction, no judgment) ──
    claims = await _extract_claims(
        question=check.get("prompt", ""),
        expected_answer=check.get("expected_answer", ""),
        user_answer=req.user_answer,
    )

    # ── Step 2: Deterministic requirement matching ──
    match_result = await _match_claims_to_requirements(
        claims=claims,
        required_ideas=required_ideas,
        wrong_statements=wrong_statements,
    )

    covered = match_result["covered_ideas"]
    missing = match_result["missing_ideas"]
    wrong_stated = match_result["wrong_ideas_stated"]

    # Deterministic result classification — no LLM judgment
    if wrong_stated:
        result = "incorrect"
        summary = "Incorrect statement detected — key distinction missing."
    elif len(missing) == 0:
        result = "correct"
        summary = "All key ideas covered."
    elif len(covered) > 0:
        result = "partially_correct"
        n = len(missing)
        summary = f"Partially correct — {n} key idea{'s' if n > 1 else ''} missing."
    else:
        result = "incorrect"
        summary = "Key ideas not found in your answer."

    return {
        "result": result,
        "summary": summary,
        "covered_ideas": covered,
        "missing_ideas": missing,
        "wrong_ideas_stated": wrong_stated,
        "extracted_claims": claims,  # What the system actually parsed from the student's answer
    }
