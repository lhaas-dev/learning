from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import os
import json
import math
import uuid
import re
import io
import logging

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
def chunk_text(text: str, max_words: int = 500) -> list:
    """Split text into 300-600 word chunks at paragraph boundaries."""
    paragraphs = re.split(r'\n{2,}', text.strip())
    chunks = []
    current: list = []
    current_words = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        words = len(para.split())
        if current_words + words > max_words and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_words = words
        else:
            current.append(para)
            current_words += words

    if current:
        chunks.append("\n\n".join(current))

    return [c for c in chunks if len(c.split()) > 30]


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
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
        raise HTTPException(status_code=400, detail=f"PDF extraction failed: {str(e)}")


# ─── AI Service ───────────────────────────────────────────────────────────────
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
RAG_CONSTRAINT = (
    "Use ONLY the provided study material. "
    "If the information is not explicitly present, "
    "return 'INSUFFICIENT SOURCE INFORMATION'. "
    "Do NOT rely on prior knowledge."
)


async def call_claude(system_message: str, user_text: str) -> str:
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=str(uuid.uuid4()),
        system_message=system_message,
    ).with_model("anthropic", "claude-sonnet-4-6")
    response = await chat.send_message(UserMessage(text=user_text))
    return response


def extract_json(text: str) -> Any:
    """Extract JSON from LLM response (may contain markdown code fences)."""
    text = text.strip()
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```$', '', text, flags=re.MULTILINE)
    text = text.strip()
    return json.loads(text)


async def extract_concepts_from_chunk(chunk: str) -> list:
    system = f"You are an expert university-level educator. {RAG_CONSTRAINT}"
    prompt = f"""You are an expert university-level educator.

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
2. short_definition (1-2 sentences)
3. common_mistake (typical student misconception)
4. prerequisite_concepts (list, empty if none are obvious)

Study material:
<<<
{chunk}
>>>

Return the result as a JSON array. Return ONLY valid JSON, no other text."""

    try:
        response = await call_claude(system, prompt)
        if "INSUFFICIENT SOURCE INFORMATION" in response:
            return []
        data = extract_json(response)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"Concept extraction failed: {e}")
        return []


async def generate_checks_for_concept(concept: dict) -> list:
    system = f"You are generating exam-oriented knowledge checks for a university student. {RAG_CONSTRAINT}"
    prompt = f"""You are generating exam-oriented knowledge checks for a university student.

Concept:
Title: {concept.get('concept_title', concept.get('title', ''))}
Definition: {concept.get('short_definition', '')}
Common mistake: {concept.get('common_mistake', '')}

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

Return the result as JSON array. Return ONLY valid JSON, no other text."""

    try:
        response = await call_claude(system, prompt)
        if "INSUFFICIENT SOURCE INFORMATION" in response:
            return []
        data = extract_json(response)
        return data[:4] if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"Check generation failed: {e}")
        return []


async def quality_filter_checks(checks: list) -> list:
    if not checks:
        return []

    system = "You are reviewing automatically generated study questions."
    prompt = f"""You are reviewing automatically generated study questions.

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
- edited_version (only if decision = EDIT, with same fields as input)

Questions:
<<<
{json.dumps(checks, ensure_ascii=False)}
>>>

Return the result as JSON array. Return ONLY valid JSON, no other text."""

    try:
        response = await call_claude(system, prompt)
        results = extract_json(response)
        approved = []
        for i, result in enumerate(results):
            if i >= len(checks):
                break
            decision = result.get("decision", "DROP").upper()
            if decision == "KEEP":
                approved.append(checks[i])
            elif decision == "EDIT" and result.get("edited_version"):
                ev = result["edited_version"]
                if ev.get("prompt") and ev.get("expected_answer"):
                    merged = {**checks[i], **ev}
                    approved.append(merged)
                else:
                    approved.append(checks[i])
            # DROP: discard — per HALLUCINATION_PREVENTION.md
        return approved
    except Exception as e:
        logger.warning(f"Quality filter failed, keeping all: {e}")
        return checks  # Fallback: keep all on filter error


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


class UpdateConceptRequest(BaseModel):
    title: Optional[str] = None
    short_definition: Optional[str] = None
    common_mistake: Optional[str] = None
    exam_weight: Optional[str] = None  # "low" | "medium" | "high"


class StartSessionRequest(BaseModel):
    pack_id: str
    duration_minutes: int = 10


class AnswerRequest(BaseModel):
    session_id: str
    concept_id: str
    check_id: str
    rating: str  # "again" | "hard" | "good" | "easy"
    user_answer: str = ""


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


# ─── Upload & AI Pipeline (Background Task) ──────────────────────────────────

async def _run_ai_pipeline(job_id: str, pack_id: str, raw_text: str):
    """Background task: extract concepts + checks, update job status."""
    try:
        await jobs_col.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"status": "processing", "started_at": datetime.now(timezone.utc)}}
        )

        chunks = chunk_text(raw_text)
        if not chunks:
            await jobs_col.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"status": "failed", "error": "Text too short to process"}}
            )
            return

        saved_concepts = []
        for chunk in chunks[:6]:
            extracted = await extract_concepts_from_chunk(chunk)
            for concept_data in extracted:
                if len(saved_concepts) >= 15:
                    break

                concept_doc = {
                    "study_pack_id": pack_id,
                    "title": concept_data.get("concept_title", concept_data.get("title", "Unknown")),
                    "short_definition": concept_data.get("short_definition", ""),
                    "common_mistake": concept_data.get("common_mistake", ""),
                    "exam_weight": 1.0,
                    "exam_weight_label": "medium",
                    "prerequisite_concepts": concept_data.get("prerequisite_concepts", []),
                    "created_at": datetime.now(timezone.utc),
                }
                c_result = await concepts_col.insert_one(concept_doc)
                concept_id = str(c_result.inserted_id)

                raw_checks = await generate_checks_for_concept(concept_data)
                if raw_checks:
                    approved_checks = await quality_filter_checks(raw_checks)
                    for chk in approved_checks:
                        await checks_col.insert_one({
                            "concept_id": concept_id,
                            "type": chk.get("type", "recall"),
                            "prompt": chk.get("prompt", ""),
                            "expected_answer": chk.get("expected_answer", ""),
                            "explanation": chk.get("short_explanation", chk.get("explanation", "")),
                            "difficulty_hint": "medium",
                        })

                concept_doc["id"] = concept_id
                concept_doc.pop("_id", None)
                concept_doc["created_at"] = concept_doc["created_at"].isoformat()
                saved_concepts.append(concept_doc)

            if len(saved_concepts) >= 15:
                break

        total_concepts = await concepts_col.count_documents({"study_pack_id": pack_id})
        await packs_col.update_one(
            {"_id": ObjectId(pack_id)},
            {"$set": {"concept_count": total_concepts}}
        )

        if not saved_concepts:
            await jobs_col.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"status": "failed", "error": "No concepts could be extracted. Try more detailed content."}}
            )
        else:
            await jobs_col.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {
                    "status": "complete",
                    "completed_at": datetime.now(timezone.utc),
                    "concepts_extracted": len(saved_concepts),
                    "chunks_processed": len(chunks),
                    "concepts": saved_concepts,
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
    if file and file.filename:
        content = await file.read()
        if file.filename.lower().endswith(".pdf"):
            raw_text = extract_text_from_pdf(content)
        else:
            raw_text = content.decode("utf-8", errors="ignore")
    elif text:
        raw_text = text
    else:
        raise HTTPException(status_code=400, detail="No file or text provided")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No text content found")

    # Create job document
    job_doc = {
        "pack_id": pack_id,
        "user_id": str(user["_id"]),
        "status": "queued",  # queued → processing → complete | failed
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
    background_tasks.add_task(_run_ai_pipeline, job_id, pack_id, raw_text)

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

    # Calculate risk per concept and build prioritized queue
    prioritized = []
    for concept in concepts_list:
        concept_id = str(concept["_id"])
        ucs = await get_or_create_ucs(user_id, concept_id, concept.get("exam_weight", 1.0))
        recall = calculate_recall_probability(ucs["stability"], ucs.get("last_reviewed_at"))
        risk = calculate_risk(recall, concept.get("exam_weight", 1.0))

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
        "concept_id": req.concept_id,
        "check_id": req.check_id,
        "rating": req.rating,
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
        pack_obj = await packs_col.find_one({"_id": ObjectId(s["pack_id"])}) if s.get("pack_id") else None
        started = s.get("started_at")
        completed = s.get("completed_at")
        sessions_list.append({
            "id": str(s["_id"]),
            "pack_title": pack_obj.get("title", "Unknown") if pack_obj else "Unknown",
            "duration_minutes": s.get("duration_minutes", 0),
            "total": s.get("total", 0),
            "stats": s.get("stats", {}),
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
