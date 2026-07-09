"""
Loads shl_product_catalog.json and turns each entry into a clean,
searchable document.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List

CATALOG_PATH = Path(__file__).parent.parent / "data" / "shl_product_catalog.json"

CATEGORY_TO_CODE = {
    "Ability & Aptitude": "A",
    "Biodata & Situational Judgment": "B",
    "Competencies": "C",
    "Development & 360": "D",
    "Assessment Exercises": "E",
    "Knowledge & Skills": "K",
    "Personality & Behavior": "P",
    "Simulations": "S",
}

_WS_RE = re.compile(r"\s+")

# entity_id -> corrected name, for catalog rows where the scraper
# mangled the display name (verified against the product URL slug and
# description text).
_NAME_CORRECTIONS = {
    "4207": "Microsoft Excel 365 (New)",
}


def _clean_name(entity_id: str, raw_name: str) -> str:
    name = _WS_RE.sub(" ", raw_name).strip()
    return _NAME_CORRECTIONS.get(entity_id, name)


def load_catalog(path: Path = CATALOG_PATH) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    raw = json.loads(text, strict=False)

    catalog = []
    for entry in raw:
        if entry.get("status") != "ok":
            continue

        entity_id = str(entry.get("entity_id", ""))
        name = _clean_name(entity_id, entry.get("name", ""))
        url = entry.get("link", entry.get("url", "")).strip()
        if not name or not url:
            continue

        test_type = _build_test_type(entry)

        catalog.append({
            "entity_id": entry.get("entity_id", ""),
            "name": name,
            "url": url,
            "description": _WS_RE.sub(" ", entry.get("description", "")).strip(),
            "job_levels": entry.get("job_levels", []),
            "job_levels_raw": entry.get("job_levels_raw", ""),
            "duration": entry.get("duration", ""),
            "languages": entry.get("languages", []),
            "keys": entry.get("keys", []),
            "test_type": test_type,
            "remote": entry.get("remote", ""),
            "adaptive": entry.get("adaptive", ""),
            "search_text": _build_search_text(entry, name),
        })
    return catalog


def _build_test_type(entry: Dict[str, Any]) -> str:
    keys = entry.get("keys", []) or []
    codes: List[str] = []
    for k in keys:
        code = CATEGORY_TO_CODE.get(k)
        if code and code not in codes:
            codes.append(code)
    return "".join(codes)


def _build_search_text(entry: Dict[str, Any], clean_name: str) -> str:
    parts = [
        clean_name,
        entry.get("description", ""),
        " ".join(entry.get("keys", [])),
        entry.get("job_levels_raw", ""),
        entry.get("languages_raw", ""),
    ]
    return _WS_RE.sub(" ", " ".join(p for p in parts if p)).strip()


if __name__ == "__main__":
    cat = load_catalog()
    print(f"Loaded {len(cat)} catalog entries")
    if cat:
        print(cat[0])