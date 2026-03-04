"""
Haiku vs. Sonnet Check Generation Benchmark
============================================
Fetches 20 diverse concepts from the ES5 study pack and generates checks
using three variants:
  A – Sonnet only (all 4 check types)
  B – Haiku only (all 4 check types)
  C – Hybrid (Haiku for recall+contrast, Sonnet for scenario+error)

Output: /app/frontend/public/benchmark.html  (static file served by React)
"""

import asyncio
import json
import os
import re
import uuid
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from emergentintegrations.llm.chat import LlmChat, UserMessage

load_dotenv("/app/backend/.env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
ES5_PACK_ID = "69a82c7bc7c639682e4e9224"

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
concepts_col = db["concepts"]

# ─── Models ───────────────────────────────────────────────────────────────────
SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"


# ─── LLM helpers ──────────────────────────────────────────────────────────────

def _make_blocking_call(model_name: str, system_msg: str, user_text: str) -> str:
    def _call():
        loop = asyncio.new_event_loop()
        try:
            chat = (
                LlmChat(
                    api_key=EMERGENT_LLM_KEY,
                    session_id=str(uuid.uuid4()),
                    system_message=system_msg,
                )
                .with_model("anthropic", model_name)
            )
            return loop.run_until_complete(chat.send_message(UserMessage(text=user_text)))
        finally:
            loop.close()
    return _call


async def call_llm(model_name: str, system_msg: str, user_text: str) -> str:
    return await asyncio.to_thread(_make_blocking_call(model_name, system_msg, user_text))


def extract_json(text: str):
    """Extract JSON from LLM response with json_repair fallback."""
    try:
        from json_repair import repair_json as _repair
        _HAS_REPAIR = True
    except ImportError:
        _HAS_REPAIR = False

    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
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

    # Manual array extraction fallback
    m = re.search(r'\[\s*\{.+?\}\s*\]', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            if _HAS_REPAIR:
                return json.loads(_repair(m.group()))
    raise ValueError("Could not parse JSON from LLM response")


# ─── Check generation ─────────────────────────────────────────────────────────

CHECK_SYSTEM = (
    "You are generating exam-oriented knowledge checks for a student. "
    "Use ONLY the provided concept information."
)

CHECK_TYPES = [
    ("recall", "Direct factual recall"),
    ("contrast", "Distinguish from a commonly confused concept"),
    ("scenario", "Practical or exam-style situation"),
    ("error", "Identify why a statement is wrong (Error-Spotting)"),
]


def build_prompt(concept: dict, types_subset: list = None) -> str:
    types_to_gen = types_subset or CHECK_TYPES
    type_instructions = "\n".join(
        f"{i+1}. {label} check ({desc})"
        for i, (label, desc) in enumerate(types_to_gen)
    )
    n = len(types_to_gen)
    type_names = " | ".join(t[0] for t in types_to_gen)
    return f"""You are generating exam-oriented knowledge checks for a student.

CRITICAL: Respond in the SAME LANGUAGE as the concept below. If German, all output must be in German.

Concept:
Title: {concept.get('title', '')}
Definition: {concept.get('short_definition', '')}
Common mistake: {concept.get('common_mistake', '')}

Generate EXACTLY {n} checks:

{type_instructions}

Rules:
- Each check must test ONE idea only.
- Avoid vague verbs ("explain", "discuss").
- expected_answer must be a single exam-grade sentence.
- short_explanation is 1-2 sentences of additional context only.
- Do not include trick questions.
- All text must be in the same language as the concept.

For each check, return:
- type ({type_names})
- prompt
- expected_answer (single sentence, exam-grade core answer)
- short_explanation (1-2 sentences additional context)
- answer_requirements:
    - required_ideas: list of 2-4 short phrases
    - wrong_statements: list of 1-3 short phrases

Return ONLY valid JSON array, no other text."""


async def generate_variant_a(concept: dict) -> list:
    """Variant A: Sonnet for ALL 4 types."""
    prompt = build_prompt(concept, CHECK_TYPES)
    try:
        resp = await call_llm(SONNET, CHECK_SYSTEM, prompt)
        data = extract_json(resp)
        return data[:4] if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"Variant A failed for '{concept.get('title')}': {e}")
        return []


async def generate_variant_b(concept: dict) -> list:
    """Variant B: Haiku for ALL 4 types."""
    prompt = build_prompt(concept, CHECK_TYPES)
    try:
        resp = await call_llm(HAIKU, CHECK_SYSTEM, prompt)
        data = extract_json(resp)
        return data[:4] if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"Variant B failed for '{concept.get('title')}': {e}")
        return []


async def generate_variant_c(concept: dict) -> list:
    """Variant C: Haiku for recall+contrast, Sonnet for scenario+error."""
    simple_types = [("recall", "Direct factual recall"), ("contrast", "Distinguish from a commonly confused concept")]
    complex_types = [("scenario", "Practical or exam-style situation"), ("error", "Identify why a statement is wrong (Error-Spotting)")]

    prompt_simple = build_prompt(concept, simple_types)
    prompt_complex = build_prompt(concept, complex_types)

    try:
        simple_resp, complex_resp = await asyncio.gather(
            call_llm(HAIKU, CHECK_SYSTEM, prompt_simple),
            call_llm(SONNET, CHECK_SYSTEM, prompt_complex),
        )
        simple_data = extract_json(simple_resp)
        complex_data = extract_json(complex_resp)
        simple_checks = simple_data[:2] if isinstance(simple_data, list) else []
        complex_checks = complex_data[:2] if isinstance(complex_data, list) else []
        return simple_checks + complex_checks
    except Exception as e:
        logger.warning(f"Variant C failed for '{concept.get('title')}': {e}")
        return []


# ─── Concept selection ────────────────────────────────────────────────────────

async def fetch_diverse_concepts(n: int = 20) -> list:
    """
    Fetch n diverse concepts from ES5 pack.
    We skip evenly through the full list to ensure topical variety
    (ES5 covers Konjunktur, Break-even, Kostenrechnung, etc.).
    """
    all_concepts = await concepts_col.find(
        {"study_pack_id": ES5_PACK_ID},
        {"_id": 1, "title": 1, "short_definition": 1, "common_mistake": 1, "doc_type": 1}
    ).to_list(length=None)

    logger.info(f"Total concepts in ES5: {len(all_concepts)}")

    # Filter for quality: needs real definition + common_mistake
    good = [
        c for c in all_concepts
        if len(c.get("short_definition", "")) > 100
        and len(c.get("common_mistake", "")) > 40
    ]

    logger.info(f"Quality concepts (def>100, mistake>40): {len(good)}")

    # Sample evenly for diversity
    if len(good) <= n:
        selected = good
    else:
        step = len(good) // n
        selected = good[::step][:n]

    # Normalize IDs
    result = []
    for c in selected:
        c["id"] = str(c.pop("_id"))
        result.append(c)

    return result


# ─── HTML Report ──────────────────────────────────────────────────────────────

def escape_html(text: str) -> str:
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def render_check_card(check: dict, variant_label: str, variant_color: str) -> str:
    check_type = check.get("type", "unknown")
    is_focus = check_type in ("scenario", "error")
    border_style = "border: 2px solid #f59e0b;" if is_focus else "border: 1px solid #2d3748;"
    focus_badge = '<span style="background:#f59e0b;color:#000;font-size:10px;padding:2px 6px;border-radius:4px;margin-left:6px;font-weight:700;">FOKUS</span>' if is_focus else ""

    prompt = escape_html(check.get("prompt", "–"))
    expected = escape_html(check.get("expected_answer", "–"))
    explanation = escape_html(check.get("short_explanation", "–"))

    req = check.get("answer_requirements", {})
    req_ideas = req.get("required_ideas", []) if isinstance(req, dict) else []
    wrong = req.get("wrong_statements", []) if isinstance(req, dict) else []

    ideas_html = "".join(f'<li style="color:#86efac;">{escape_html(i)}</li>' for i in req_ideas) if req_ideas else "<li style='color:#4b5563;'>–</li>"
    wrong_html = "".join(f'<li style="color:#fca5a5;">{escape_html(w)}</li>' for w in wrong) if wrong else "<li style='color:#4b5563;'>–</li>"

    type_colors = {
        "recall": "#60a5fa",
        "contrast": "#a78bfa",
        "scenario": "#f59e0b",
        "error": "#f87171",
    }
    type_color = type_colors.get(check_type, "#9ca3af")

    return f"""
<div data-check-card data-check-type="{check_type}" style="background:#1a1f2e;{border_style}border-radius:8px;padding:14px;margin-bottom:10px;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
    <span data-check-type="{check_type}" style="background:{type_color};color:#000;font-size:10px;padding:2px 7px;border-radius:4px;font-weight:700;text-transform:uppercase;">{escape_html(check_type)}</span>
    {focus_badge}
  </div>
  <div style="margin-bottom:6px;">
    <span style="color:#9ca3af;font-size:11px;text-transform:uppercase;letter-spacing:0.05em;">Frage</span>
    <p style="margin:3px 0;color:#e2e8f0;font-size:13px;">{prompt}</p>
  </div>
  <div style="margin-bottom:6px;">
    <span style="color:#9ca3af;font-size:11px;text-transform:uppercase;letter-spacing:0.05em;">Musterlösung</span>
    <p style="margin:3px 0;color:#f0fdf4;font-size:13px;font-style:italic;">{expected}</p>
  </div>
  <div style="margin-bottom:6px;">
    <span style="color:#9ca3af;font-size:11px;text-transform:uppercase;letter-spacing:0.05em;">Erklärung</span>
    <p style="margin:3px 0;color:#cbd5e1;font-size:12px;">{explanation}</p>
  </div>
  <details style="margin-top:6px;">
    <summary style="color:#6b7280;font-size:11px;cursor:pointer;">Bewertungsregeln</summary>
    <div style="margin-top:6px;display:grid;grid-template-columns:1fr 1fr;gap:8px;">
      <div>
        <span style="color:#86efac;font-size:10px;">PFLICHT-IDEEN</span>
        <ul style="margin:3px 0;padding-left:16px;font-size:11px;">{ideas_html}</ul>
      </div>
      <div>
        <span style="color:#fca5a5;font-size:10px;">FALSCHE AUSSAGEN</span>
        <ul style="margin:3px 0;padding-left:16px;font-size:11px;">{wrong_html}</ul>
      </div>
    </div>
  </details>
</div>"""


def generate_html_report(results: list, elapsed_sec: float) -> str:
    concept_blocks = []

    for i, entry in enumerate(results):
        concept = entry["concept"]
        va = entry.get("variant_a", [])
        vb = entry.get("variant_b", [])
        vc = entry.get("variant_c", [])

        va_cards = "".join(render_check_card(c, "A", "#4ade80") for c in va) if va else "<p style='color:#6b7280;'>Fehler beim Generieren</p>"
        vb_cards = "".join(render_check_card(c, "B", "#60a5fa") for c in vb) if vb else "<p style='color:#6b7280;'>Fehler beim Generieren</p>"
        vc_cards = "".join(render_check_card(c, "C", "#f59e0b") for c in vc) if vc else "<p style='color:#6b7280;'>Fehler beim Generieren</p>"

        # Count checks per type per variant for quick reference
        def type_summary(checks):
            types = {c.get("type", "?") for c in checks}
            return ", ".join(sorted(types)) if types else "–"

        concept_blocks.append(f"""
<div class="concept-block" style="background:#0f1420;border:1px solid #1e293b;border-radius:12px;padding:20px;margin-bottom:30px;">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px;">
    <div>
      <span style="color:#6b7280;font-size:11px;">KONZEPT {i+1}/20</span>
      <h3 style="margin:2px 0;color:#00e5ff;font-size:16px;font-weight:700;">{escape_html(concept.get('title', ''))}</h3>
      <p style="margin:4px 0;color:#94a3b8;font-size:12px;">{escape_html(concept.get('short_definition', ''))}</p>
    </div>
    <div style="background:#1a1f2e;border-radius:8px;padding:8px 12px;text-align:center;min-width:120px;">
      <div style="color:#6b7280;font-size:10px;">Typischer Fehler</div>
      <div style="color:#fca5a5;font-size:11px;margin-top:3px;">{escape_html(concept.get('common_mistake', ''))}</div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;">
    <div>
      <div style="background:#052e16;border:1px solid #166534;border-radius:6px;padding:8px 12px;margin-bottom:10px;text-align:center;">
        <div style="color:#4ade80;font-weight:700;font-size:13px;">VARIANTE A — SONNET</div>
        <div style="color:#86efac;font-size:11px;">Alle 4 Typen: {escape_html(type_summary(va))}</div>
      </div>
      {va_cards}
    </div>
    <div>
      <div style="background:#0c1a2e;border:1px solid #1e40af;border-radius:6px;padding:8px 12px;margin-bottom:10px;text-align:center;">
        <div style="color:#60a5fa;font-weight:700;font-size:13px;">VARIANTE B — HAIKU</div>
        <div style="color:#93c5fd;font-size:11px;">Alle 4 Typen: {escape_html(type_summary(vb))}</div>
      </div>
      {vb_cards}
    </div>
    <div>
      <div style="background:#1c1005;border:1px solid #92400e;border-radius:6px;padding:8px 12px;margin-bottom:10px;text-align:center;">
        <div style="color:#f59e0b;font-weight:700;font-size:13px;">VARIANTE C — HYBRID</div>
        <div style="color:#fcd34d;font-size:11px;">Haiku: recall+contrast | Sonnet: szenario+fehler</div>
      </div>
      {vc_cards}
    </div>
  </div>
</div>""")

    all_blocks = "\n".join(concept_blocks)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Haiku vs. Sonnet Benchmark — Check Generation</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #050a14; color: #e2e8f0; line-height: 1.5; }}
    h1, h2, h3 {{ line-height: 1.3; }}
    details summary::-webkit-details-marker {{ display: none; }}
    details summary::before {{ content: '▶ '; font-size: 10px; }}
    details[open] summary::before {{ content: '▼ '; }}
    .sticky-nav {{ position: sticky; top: 0; z-index: 100; background: #050a14; border-bottom: 1px solid #1e293b; padding: 0; }}
    .filter-bar {{ display: flex; gap: 10px; padding: 10px 24px; flex-wrap: wrap; align-items: center; }}
    .filter-btn {{ padding: 5px 14px; border-radius: 20px; border: 1px solid; cursor: pointer; font-size: 12px; font-weight: 600; background: transparent; transition: all 0.15s; }}
    .filter-btn:hover {{ opacity: 0.8; }}
    .filter-btn.active {{ opacity: 1 !important; }}
    #filter-all {{ border-color: #475569; color: #94a3b8; }}
    #filter-all.active {{ background: #1e293b; color: #e2e8f0; }}
    #filter-scenario {{ border-color: #f59e0b; color: #f59e0b; }}
    #filter-scenario.active {{ background: rgba(245,158,11,0.1); }}
    #filter-error {{ border-color: #f87171; color: #f87171; }}
    #filter-error.active {{ background: rgba(248,113,113,0.1); }}
    .concept-block {{ transition: opacity 0.2s; }}
    .concept-block.hidden {{ display: none; }}
    @media (max-width: 1100px) {{
      .grid-3 {{ grid-template-columns: 1fr !important; }}
    }}
  </style>
</head>
<body>

<div class="sticky-nav">
  <div style="background:#0a0f1a;padding:14px 24px;border-bottom:1px solid #1e293b;">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
      <div>
        <h1 style="color:#00e5ff;font-size:20px;font-weight:800;">Haiku vs. Sonnet — Check Generation Benchmark</h1>
        <p style="color:#64748b;font-size:12px;margin-top:3px;">W&G ES5 · 20 Konzepte · 60 Checks pro Variante · Generiert: {generated_at} · Laufzeit: {elapsed_sec:.0f}s</p>
      </div>
      <div style="display:flex;gap:16px;text-align:center;">
        <div style="background:#052e16;border:1px solid #166534;border-radius:8px;padding:8px 16px;">
          <div style="color:#4ade80;font-weight:700;font-size:15px;">A: Sonnet</div>
          <div style="color:#86efac;font-size:11px;">Alle 4 Typen</div>
        </div>
        <div style="background:#0c1a2e;border:1px solid #1e40af;border-radius:8px;padding:8px 16px;">
          <div style="color:#60a5fa;font-weight:700;font-size:15px;">B: Haiku</div>
          <div style="color:#93c5fd;font-size:11px;">Alle 4 Typen</div>
        </div>
        <div style="background:#1c1005;border:1px solid #92400e;border-radius:8px;padding:8px 16px;">
          <div style="color:#f59e0b;font-weight:700;font-size:15px;">C: Hybrid</div>
          <div style="color:#fcd34d;font-size:11px;">Haiku+Sonnet</div>
        </div>
      </div>
    </div>
  </div>
  <div class="filter-bar">
    <span style="color:#64748b;font-size:11px;font-weight:600;">Filter Fokus-Typen:</span>
    <button class="filter-btn active" id="filter-all" onclick="filterCards('all')">Alle Checks</button>
    <button class="filter-btn" id="filter-scenario" onclick="filterCards('scenario')">Nur Szenario</button>
    <button class="filter-btn" id="filter-error" onclick="filterCards('error')">Nur Fehler-Spotting</button>
    <span style="color:#475569;font-size:11px;margin-left:auto;">
      <span style="color:#f59e0b;">■</span> FOKUS = Szenario &amp; Fehler-Spotting Checks (manueller Review-Schwerpunkt)
    </span>
  </div>
</div>

<div style="max-width:1600px;margin:0 auto;padding:24px;">

  <div style="background:#0f172a;border:1px solid #1e3a5f;border-radius:10px;padding:16px;margin-bottom:24px;">
    <h2 style="color:#93c5fd;font-size:14px;font-weight:700;margin-bottom:8px;">Anleitung zum manuellen Review</h2>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;font-size:12px;color:#94a3b8;">
      <div>
        <strong style="color:#e2e8f0;">Was prüfen?</strong><br>
        Fokus auf <span style="color:#f59e0b;">Szenario</span> und <span style="color:#f87171;">Fehler-Spotting</span> (FOKUS-Badge).
        Diese sind am aufwendigsten zu generieren.
      </div>
      <div>
        <strong style="color:#e2e8f0;">Bewertungskriterien</strong><br>
        1. Ist die Frage klar und eindeutig?<br>
        2. Ist die Musterlösung treffend?<br>
        3. Sind die Pflicht-Ideen sinnvoll?
      </div>
      <div>
        <strong style="color:#e2e8f0;">Erwartetes Ergebnis</strong><br>
        Wenn B ≈ A: Haiku reicht für alle Typen (günstiger).<br>
        Wenn C ≈ A: Hybrid-Modell ist optimal (günstig + qualitativ).
      </div>
      <div>
        <strong style="color:#e2e8f0;">Kein DB-Schreibzugriff</strong><br>
        Alle generierten Checks sind nur für diesen Report.
        Keine bestehenden Daten werden überschrieben.
      </div>
    </div>
  </div>

  <div id="concepts-container">
    {all_blocks}
  </div>

  <div style="text-align:center;padding:40px;color:#374151;font-size:12px;">
    Benchmark abgeschlossen · {len(results)} Konzepte · Generiert am {generated_at}
  </div>
</div>

<script>
function filterCards(type) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('filter-' + type).classList.add('active');

  if (type === 'all') {{
    document.querySelectorAll('[data-check-card]').forEach(el => el.style.display = '');
    return;
  }}

  // Show only cards of the selected type (find by type badge text)
  document.querySelectorAll('[data-check-card]').forEach(el => {{
    const badge = el.querySelector('[data-check-type]');
    if (badge) {{
      el.style.display = badge.dataset.checkType === type ? '' : 'none';
    }}
  }});
}}
</script>
</body>
</html>"""


# ─── Main benchmark runner ────────────────────────────────────────────────────

async def run_benchmark():
    logger.info("=== Haiku vs. Sonnet Benchmark Starting ===")
    start = asyncio.get_event_loop().time()

    concepts = await fetch_diverse_concepts(20)
    logger.info(f"Selected {len(concepts)} concepts for benchmark")

    semaphore = asyncio.Semaphore(3)  # max 3 concepts in parallel

    async def process_concept(concept):
        async with semaphore:
            logger.info(f"Processing: {concept.get('title', '?')}")
            va, vb, vc = await asyncio.gather(
                generate_variant_a(concept),
                generate_variant_b(concept),
                generate_variant_c(concept),
                return_exceptions=False,
            )
            return {
                "concept": concept,
                "variant_a": va,
                "variant_b": vb,
                "variant_c": vc,
            }

    results = await asyncio.gather(*[process_concept(c) for c in concepts])
    results = [r for r in results if r is not None]

    elapsed = asyncio.get_event_loop().time() - start
    logger.info(f"All {len(results)} concepts processed in {elapsed:.1f}s")

    html = generate_html_report(results, elapsed)
    out_path = "/app/frontend/public/benchmark.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Report saved to {out_path}")
    logger.info(f"Access at: <REACT_APP_BACKEND_URL base>/benchmark.html")

    # Also save raw JSON for future reference
    json_path = "/app/frontend/public/benchmark_raw.json"
    raw = []
    for r in results:
        raw.append({
            "concept_id": r["concept"]["id"],
            "concept_title": r["concept"]["title"],
            "variant_a": r["variant_a"],
            "variant_b": r["variant_b"],
            "variant_c": r["variant_c"],
        })
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    logger.info(f"Raw JSON saved to {json_path}")

    print(f"\n✅ BENCHMARK COMPLETE: {len(results)} concepts, {elapsed:.0f}s")
    print(f"📄 HTML Report: {out_path}")
    print(f"📊 Raw JSON:    {json_path}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
