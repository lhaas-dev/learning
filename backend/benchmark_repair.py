"""
Benchmark Repair Run
====================
Re-generates only the failed checks (where variant has 0 results),
merges back into existing benchmark_raw.json, and re-renders the HTML report.
"""

import asyncio
import json
import os
import re
import uuid
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from json_repair import repair_json
from emergentintegrations.llm.chat import LlmChat, UserMessage

load_dotenv("/app/backend/.env")

# Import HTML renderer from main benchmark script
import sys
sys.path.insert(0, "/app/backend")
from benchmark_checks import (
    generate_variant_a, generate_variant_b, generate_variant_c,
    generate_html_report,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RAW_PATH = "/app/frontend/public/benchmark_raw.json"
HTML_PATH = "/app/frontend/public/benchmark.html"


# ─── Robust JSON extraction (used to monkey-patch extract_json) ───────────────

def robust_extract_json(text: str):
    """Try standard parse first, fall back to json_repair, then manual extraction."""
    text = text.strip()
    # Remove markdown fences
    text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Try standard first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try json_repair
    try:
        repaired = repair_json(text)
        return json.loads(repaired)
    except Exception:
        pass

    # Manual: find [ ... ] block
    match = re.search(r"\[\s*\{.+?\}\s*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            try:
                return json.loads(repair_json(match.group()))
            except Exception:
                pass

    raise ValueError(f"Could not parse JSON from response (len={len(text)})")


# Monkey-patch the benchmark module
import benchmark_checks
benchmark_checks.extract_json = robust_extract_json


async def repair_run():
    logger.info("=== Benchmark Repair Run Starting ===")
    start = asyncio.get_event_loop().time()

    from motor.motor_asyncio import AsyncIOMotorClient
    from bson import ObjectId
    MONGO_URL = os.environ["MONGO_URL"]
    DB_NAME = os.environ["DB_NAME"]
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    mdb = mongo_client[DB_NAME]
    concepts_col = mdb["concepts"]

    with open(RAW_PATH) as f:
        data = json.load(f)

    # Find entries that need repair
    to_repair = []
    for r in data:
        needs = {
            "a": len(r["variant_a"]) == 0,
            "b": len(r["variant_b"]) == 0,
            "c": len(r["variant_c"]) == 0,
        }
        if any(needs.values()):
            to_repair.append((r, needs))

    logger.info(f"Concepts needing repair: {len(to_repair)}")

    # Fetch full concept data for each entry that needs repair
    concept_ids = [r["concept_id"] for r, _ in to_repair]
    full_concepts = {}
    for cid in concept_ids:
        try:
            doc = await concepts_col.find_one(
                {"_id": ObjectId(cid)},
                {"_id": 0, "title": 1, "short_definition": 1, "common_mistake": 1}
            )
            if doc:
                doc["id"] = cid
                full_concepts[cid] = doc
        except Exception as e:
            logger.warning(f"Could not fetch concept {cid}: {e}")

    semaphore = asyncio.Semaphore(2)

    async def repair_entry(entry, needs):
        async with semaphore:
            cid = entry["concept_id"]
            concept = full_concepts.get(cid)
            if not concept:
                # Fallback: use title only
                concept = {"id": cid, "title": entry["concept_title"], "short_definition": "", "common_mistake": ""}
            logger.info(f"Repairing: {concept.get('title', '?')} — needs A:{needs['a']} B:{needs['b']} C:{needs['c']}")

            tasks = {}
            if needs["a"]:
                tasks["a"] = generate_variant_a(concept)
            if needs["b"]:
                tasks["b"] = generate_variant_b(concept)
            if needs["c"]:
                tasks["c"] = generate_variant_c(concept)

            results_gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
            repaired = dict(zip(tasks.keys(), results_gathered))

            for variant, result in repaired.items():
                if isinstance(result, Exception):
                    logger.warning(f"  Variant {variant.upper()} STILL failed: {result}")
                else:
                    key = f"variant_{variant}"
                    entry[key] = result
                    logger.info(f"  Variant {variant.upper()} repaired: {len(result)} checks")

    await asyncio.gather(*[repair_entry(r, n) for r, n in to_repair])

    elapsed = asyncio.get_event_loop().time() - start

    # Summary
    total_a = sum(len(r["variant_a"]) for r in data)
    total_b = sum(len(r["variant_b"]) for r in data)
    total_c = sum(len(r["variant_c"]) for r in data)
    logger.info(f"After repair — A: {total_a}, B: {total_b}, C: {total_c}")

    # Save updated JSON
    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Re-render HTML: we need to reconstruct "concept" dict for each entry
    results_for_html = []
    for r in data:
        cid = r["concept_id"]
        concept = full_concepts.get(cid, {
            "id": cid,
            "title": r["concept_title"],
            "short_definition": "",
            "common_mistake": "",
        })
        results_for_html.append({
            "concept": concept,
            "variant_a": r["variant_a"],
            "variant_b": r["variant_b"],
            "variant_c": r["variant_c"],
        })

    html = generate_html_report(results_for_html, elapsed)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ REPAIR COMPLETE: {elapsed:.0f}s")
    print(f"   A: {total_a}/80 checks  B: {total_b}/80 checks  C: {total_c}/80 checks")
    print(f"📄 Updated HTML: {HTML_PATH}")


if __name__ == "__main__":
    asyncio.run(repair_run())
