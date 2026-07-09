# """
# Replays each sample conversation's user turns against YOUR running
# /chat endpoint and prints your bot's actual replies side by side with
# what the reference conversation shows — so you can eyeball how close
# you are before submitting.

# This is a starting point, not the real evaluator. SHL's real harness
# uses a simulated LLM user against your live deployment; this script
# just replays the fixed user lines from C1..C10 in order.

# Usage:
#     1. Run your API locally:  uvicorn app.main:app --reload
#     2. python tests/replay_eval.py
# """

# import re
# import requests
# from pathlib import Path

# API_URL = "http://localhost:8000/chat"
# TRACES_DIR = Path(__file__).parent.parent / "data" / "GenAI_SampleConversations"


# def extract_user_turns(md_text: str):
#     return re.findall(r"\*\*User\*\*\s*\n\s*>\s*(.+)", md_text)


# def run_trace(path: Path):
#     text = path.read_text(encoding="utf-8")
#     user_turns = extract_user_turns(text)

#     print(f"\n=== {path.name} ===")
#     history = []
#     for turn in user_turns:
#         history.append({"role": "user", "content": turn})
#         resp = requests.post(API_URL, json={"messages": history}, timeout=30)
#         data = resp.json()
#         print(f"USER: {turn}")
#         print(f"BOT : {data['reply']}")
#         print(f"     recs={len(data.get('recommendations', []))} "
#               f"end={data.get('end_of_conversation')}")
#         history.append({"role": "assistant", "content": data["reply"]})


# if __name__ == "__main__":
#     for md_file in sorted(TRACES_DIR.glob("C*.md")):
#         run_trace(md_file)


"""
Replays each sample conversation's user turns against YOUR running
/chat endpoint, prints your bot's actual replies alongside the
reference conversation, and scores Recall@10 against the expected
final shortlist (taken from the LAST recommendation table in each
.md file — i.e. the agreed-upon shortlist by the end of that
conversation).

This is a starting point, not the real evaluator. SHL's real harness
uses a simulated LLM user against your live deployment; this script
just replays the fixed user lines from C1..C10 in order against your
live API and checks recall.

This script only READS from your running API over HTTP — it does not
touch the inference pipeline or FastAPI app in-process, so it has no
effect on real /chat latency.

Usage:
    1. Run your API locally:  uvicorn app.main:app --reload
    2. python tests/replay_eval.py
"""

import re
import requests
from pathlib import Path
from typing import Dict, List

API_URL = "http://localhost:8000/chat"
TRACES_DIR = Path(__file__).parent.parent / "data" / "GenAI_SampleConversations"

# ---------------------------------------------------------------------
# Parsing the .md transcripts
# ---------------------------------------------------------------------

# Captures every line of a ">"-blockquoted user turn, not just the
# first one — a turn that wraps across multiple "> ..." lines in the
# source markdown is joined back into a single message.
USER_BLOCK_RE = re.compile(r"\*\*User\*\*\s*\n\n((?:^>.*\n?)+)", re.MULTILINE)

# A markdown table row, e.g.: | 1 | Smart Interview Live Coding | K | ... |
TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$", re.MULTILINE)


def extract_user_turns(md_text: str) -> List[str]:
    turns = []
    for m in USER_BLOCK_RE.finditer(md_text):
        lines = [ln.lstrip(">").strip() for ln in m.group(1).splitlines() if ln.strip()]
        turns.append(" ".join(lines).strip())
    return turns


def extract_expected_names(md_text: str) -> List[str]:
    """Expected final shortlist = names in the LAST table in the file."""
    tables, current = [], []
    for line in md_text.splitlines():
        if TABLE_ROW_RE.match(line):
            current.append(line)
        else:
            if current:
                tables.append(current)
                current = []
    if current:
        tables.append(current)
    if not tables:
        return []

    last_table = tables[-1]
    header_cells = [c.strip() for c in last_table[0].strip("|").split("|")]
    try:
        name_idx = [c.lower() for c in header_cells].index("name")
    except ValueError:
        return []

    names = []
    for row in last_table[2:]:  # skip header + "|---|---|" separator
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) <= name_idx:
            continue
        name = re.sub(r"^\*\*(.*)\*\*$", r"\1", cells[name_idx].strip())
        if name and name.lower() != "name":
            names.append(name)
    return names


# ---------------------------------------------------------------------
# Recall@10
# ---------------------------------------------------------------------

def recall_at_10(expected: List[str], predicted: List[str]) -> float:
    if not expected:
        return 1.0  # nothing was expected; vacuously satisfied
    expected_l = {e.lower() for e in expected}
    predicted_l = {p.lower() for p in predicted[:10]}
    return len(expected_l & predicted_l) / len(expected_l)


# ---------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------

# def run_trace(path: Path) -> Dict:
#     text = path.read_text(encoding="utf-8")
#     user_turns = extract_user_turns(text)
#     expected = extract_expected_names(text)

#     print(f"\n=== {path.name} ===")
#     history = []
#     predicted: List[str] = []

#     for turn in user_turns:
#         history.append({"role": "user", "content": turn})
#         resp = requests.post(API_URL, json={"messages": history}, timeout=30)
#         # data = resp.json()
#         data = resp.json()
#         print("API Response:", data)

#         recs = data.get("recommendations") or []
#         print(f"USER: {turn}")
#         print(f"BOT : {data['reply']}")
#         print(f"     recs={len(recs)} end={data.get('end_of_conversation')}")

#         if recs:
#             predicted = [r["name"] for r in recs]  # last non-empty turn wins

#         history.append({"role": "assistant", "content": data["reply"]})

#     recall = recall_at_10(expected, predicted)
#     expected_l = {e.lower() for e in expected}
#     predicted_l = {p.lower() for p in predicted[:10]}
#     correct = [e for e in expected if e.lower() in predicted_l]
#     missing = [e for e in expected if e.lower() not in predicted_l]
#     extra = [p for p in predicted if p.lower() not in expected_l]

#     print(f"\nExpected:")
#     for e in expected:
#         print(f"  - {e}")
#     print(f"Predicted:")
#     for p in predicted:
#         print(f"  - {p}")
#     if missing:
#         print(f"Missing: {', '.join(missing)}")
#     if extra:
#         print(f"Extra: {', '.join(extra)}")
#     print(f"Recall@10 = {recall:.2f}")

#     return {
#         "id": path.stem,
#         "recall": recall,
#         "correct": len(correct),
#         "missing": len(missing),
#         "extra": len(extra),
#     }
def run_trace(path: Path) -> Dict:
    text = path.read_text(encoding="utf-8")
    user_turns = extract_user_turns(text)
    expected = extract_expected_names(text)

    print(f"\n=== {path.name} ===")
    history = []
    predicted: List[str] = []

    headers = {
        "X-API-Key": "my-test-secret-123"   # Replace with your actual API key
    }

    for turn in user_turns:
        history.append({"role": "user", "content": turn})

        resp = requests.post(
            API_URL,
            json={"messages": history},
            headers=headers,
            timeout=30,
        )

        data = resp.json()
        print("API Response:", data)

        # If the API returned an error, print it and stop this conversation
        if resp.status_code != 200:
            print(f"API Error ({resp.status_code}): {data}")
            break

        reply = (
            data.get("reply")
            or data.get("response")
            or data.get("answer")
            or data.get("message")
            or ""
        )

        recs = data.get("recommendations") or []

        print(f"USER: {turn}")
        print(f"BOT : {reply}")
        print(f"     recs={len(recs)} end={data.get('end_of_conversation')}")

        if recs:
            predicted = [r["name"] for r in recs]

        history.append({"role": "assistant", "content": reply})

    recall = recall_at_10(expected, predicted)
    expected_l = {e.lower() for e in expected}
    predicted_l = {p.lower() for p in predicted[:10]}
    correct = [e for e in expected if e.lower() in predicted_l]
    missing = [e for e in expected if e.lower() not in predicted_l]
    extra = [p for p in predicted if p.lower() not in expected_l]

    print("\nExpected:")
    for e in expected:
        print(f"  - {e}")

    print("Predicted:")
    for p in predicted:
        print(f"  - {p}")

    if missing:
        print(f"Missing: {', '.join(missing)}")

    if extra:
        print(f"Extra: {', '.join(extra)}")

    print(f"Recall@10 = {recall:.2f}")

    return {
        "id": path.stem,
        "recall": recall,
        "correct": len(correct),
        "missing": len(missing),
        "extra": len(extra),
    }

if __name__ == "__main__":
    results = [run_trace(md_file) for md_file in sorted(TRACES_DIR.glob("C*.md"))]

    if results:
        mean_recall = sum(r["recall"] for r in results) / len(results)
        total_correct = sum(r["correct"] for r in results)
        total_missing = sum(r["missing"] for r in results)
        total_extra = sum(r["extra"] for r in results)

        print("\n" + "=" * 50)
        print("EVALUATION SUMMARY")
        print("=" * 50)
        print(f"Conversations evaluated : {len(results)}")
        print(f"Total correct           : {total_correct}")
        print(f"Total missing           : {total_missing}")
        print(f"Total extra             : {total_extra}")
        print(f"Mean Recall@10          = {mean_recall:.2f}")
    else:
        print(f"No .md files found in {TRACES_DIR}")