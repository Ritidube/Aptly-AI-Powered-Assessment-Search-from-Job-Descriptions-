"""
Hybrid retrieval: BM25 (catches exact names like "OPQ32r", "GSA")
+ dense embeddings via FAISS (catches soft queries like "good with
stakeholders"). Scores are merged via reciprocal rank fusion so both
exact and fuzzy matches have a chance to surface.
 
BUGFIX: exact_lookup() previously only did a plain substring check in
both directions. That fails for common user phrasing like "Verify G+"
against the catalog's actual name "SHL Verify Interactive G+" — "Verify
G+" is not a contiguous substring of that name, so an explicit-name
add/remove/final-list instruction silently found nothing. A
token-overlap fallback (all significant words of the query present
somewhere in the candidate name) now catches these without weakening
the plain substring path, which stays the first, most precise check.
 
ADDED: family-level de-duplication in search(). The catalog contains
many near-duplicate variants of the same underlying test ("HiPo
Assessment Report 1.0" / "... 2.0", "OPQ Team Types & Leadership
Styles Profile" / "... Report", "Graduate Scenarios" / "... Narrative
Report" / "... Profile Report"). Letting several siblings from the
same family occupy the fixed top_k window wastes slots that could
otherwise surface a genuinely different, expected assessment. Ranking
now prefers one representative per family first, and only backfills
with sibling variants if there aren't enough distinct families to
fill top_k.
"""
 
import re
from typing import Any, Dict, List
 
import numpy as np
import faiss
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from app.cache import get_cached_urls, set_cached_urls
 
_TOKEN_RE = re.compile(r"[a-z0-9]+")
 
 
def _tokenize(text: str) -> List[str]:
    # BUGFIX: BM25 was tokenizing with a naive `.lower().split()`,
    # which only splits on whitespace. Real user/JD text is full of
    # hyphenated and slash-joined compounds -- "SQL/relational",
    # "re-skill", "co-op", "front-end" -- that would otherwise never
    # match the plain "sql", "skill", "frontend" tokens the catalog
    # text and structured query terms actually use. Splitting on any
    # non-alphanumeric boundary fixes this for both the catalog index
    # and every query, with no downside (it only ever creates
    # additional valid match opportunities, never removes one).
    return _TOKEN_RE.findall(text.lower())
 
# Words that describe a REPORT/PACKAGING variant of the same
# underlying assessment rather than a functionally different product.
# Stripped out when computing a "family key" for de-duplication.
# Deliberately does NOT include tier words like "Essentials" — those
# usually denote a genuinely different-scope product, not just a
# different report format, so collapsing them would risk hiding the
# actually-correct tier.
_VARIANT_STRIP_RE = re.compile(
    r"(?i)\b(report|profile|narrative report|solution|version|new|pack|package|and)\b"
    r"|\(new\)|\bv\d+(\.\d+)?\b|\b\d+(\.\d+)?\b"
)
 
_STOPWORDS = {"the", "a", "an", "test", "assessment", "exam", "of", "for"}
 
 
# BUGFIX: ampersand and the word "and" are the same connector in SHL
# naming ("...Types and Leadership Styles Report" vs "...Types &
# Leadership Styles Profile" are the SAME underlying product), but the
# old key only stripped the word "and" and left a bare "&" to be
# turned into whitespace by the final non-alnum collapse -- so one
# variant kept a stray "and" token the other never had, and the two
# names hashed to different family keys. Normalizing "&" -> "and"
# BEFORE stripping "and" as a connector word means both variants
# collapse to the same family key, so de-dup below actually catches
# them.
def _family_key(name: str) -> str:
    key = name.lower().replace("&", " and ")
    key = _VARIANT_STRIP_RE.sub(" ", key)
    key = re.sub(r"[^a-z0-9]+", " ", key).strip()
    return key
 
 
def _canonical_bonus(name: str) -> float:
    """
    Small, deterministic tie-breaker used only to decide which member
    of a name FAMILY wins the family's slot when their fused scores
    are close (same-family siblings routinely score near-identically
    since their name/description text overlaps heavily). Verified
    against the sample conversations: SHL's own naming convention
    treats the un-suffixed / shorter member of a family as canonical
    ("Graduate Scenarios" over "...Narrative/Profile Report", "SHL
    Verify Interactive G+" over "Verify G+ - Ability Test Report"),
    and a higher version number as current when both exist ("OPQ
    Universal Competency Report 2.0" over "...1.0", "Sales
    Transformation 2.0" over "...1.0"). The magnitude is deliberately
    tiny relative to a typical RRF score gap -- it only breaks
    near-ties within a family, it must never be large enough to
    reorder genuinely different, unrelated catalog items.
    """
    bonus = 0.0
    m = re.search(r"(\d+)\.(\d+)", name)
    if m:
        bonus += float(f"{m.group(1)}.{m.group(2)}") * 0.0005
    bonus -= len(name) * 0.00002
    return bonus
 
 
class HybridRetriever:
    def __init__(self, catalog: List[Dict[str, Any]], model_name: str = "all-MiniLM-L6-v2"):
        self.catalog = catalog
        self.texts = [c["search_text"] for c in catalog]
 
        # BM25
        tokenized = [_tokenize(t) for t in self.texts]
        self.bm25 = BM25Okapi(tokenized)
 
        # Dense embeddings — computed once at startup, not per request.
        self.embedder = SentenceTransformer(model_name)
        embeddings = self.embedder.encode(self.texts, normalize_embeddings=True)
        self.dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(self.dim)  # cosine sim via normalized IP
        self.index.add(np.array(embeddings, dtype="float32"))

        # Lets a cache hit (which only stores urls, see app/cache.py)
        # map straight back onto this process's live catalog dicts
        # instead of needing a second copy of the full records in Redis.
        self._url_to_entry = {c["url"]: c for c in catalog}
 
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            return []

        # Cache sits in front of BOTH BM25 and the FAISS/embedding
        # lookup, and stores the list AFTER RRF fusion + family de-dup
        # -- i.e. exactly what this function would otherwise return.
        # A hit skips every line below down to the `return`.
        cached_urls = get_cached_urls(query, top_k)
        if cached_urls is not None:
            hydrated = [self._url_to_entry[u] for u in cached_urls if u in self._url_to_entry]
            # If every cached url still maps to a live catalog entry,
            # trust the cache. If the catalog has since changed shape
            # (e.g. a redeploy with a refreshed scrape) and some urls
            # vanished, fall through and recompute fresh rather than
            # silently returning a shorter-than-requested list.
            if len(hydrated) == len(cached_urls):
                return hydrated
 
        # Wider pool than top_k so family de-dup has room to pick real
        # alternates instead of backfilling with siblings. This is a
        # single extra argsort/slice over scores we already computed —
        # not an extra embedding call — so widening it is essentially
        # free and only helps recall.
        pool = max(top_k * 6, 30)
 
        # BM25 scores
        bm25_scores = self.bm25.get_scores(_tokenize(query))
        bm25_top = np.argsort(bm25_scores)[::-1][:pool]
 
        # Dense scores
        q_emb = self.embedder.encode([query], normalize_embeddings=True)
        _, dense_idx = self.index.search(np.array(q_emb, dtype="float32"), pool)
        dense_top = dense_idx[0]
 
        # Merge: reciprocal rank fusion
        rrf_scores: Dict[int, float] = {}
        for rank, idx in enumerate(bm25_top):
            if idx < 0:
                continue
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (60 + rank)
        for rank, idx in enumerate(dense_top):
            if idx < 0:
                continue
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (60 + rank)
 
        # SOFT family-aware re-ranking. An earlier version tried a HARD
        # "one slot per family" cutoff and reverted it -- picking a
        # single "representative" per family by raw score alone is a
        # coin flip on which sibling is the one actually expected, so a
        # wrong guess turned "both siblings safely in the top 10" into
        # "the correct one is gone completely", which regressed overall
        # recall. This version applies a MULTIPLICATIVE penalty (never
        # deletion) each time an item from an already-picked family
        # would be selected again, combined with a small deterministic
        # _canonical_bonus() so that when two siblings are genuinely
        # close, the one SHL's own naming treats as canonical wins the
        # tie. A duplicate sibling only loses its slot when something
        # else is a genuinely competitive match; if nothing else scores
        # close, it still gets in -- so this can only ever free a slot
        # for a different family, never remove an item that had no real
        # competition for that slot.
        FAMILY_PENALTY = 0.6
 
        remaining = {
            idx: score + _canonical_bonus(self.catalog[idx]["name"])
            for idx, score in rrf_scores.items()
        }
        selected: List[int] = []
        while remaining and len(selected) < top_k:
            idx = max(remaining, key=remaining.get)
            selected.append(idx)
            fam = _family_key(self.catalog[idx]["name"])
            del remaining[idx]
            for idx2 in remaining:
                if _family_key(self.catalog[idx2]["name"]) == fam:
                    remaining[idx2] *= FAMILY_PENALTY
 
        results = [self.catalog[idx] for idx in selected]
        set_cached_urls(query, top_k, [r["url"] for r in results])
        return results
 
    def exact_lookup(self, name_query: str) -> List[Dict[str, Any]]:
        """Used for 'compare X vs Y' and refine remove/add-by-name —
        direct name match, no dense/BM25 scoring involved.
 
        Two passes:
          1. Plain substring match, either direction (fast, most
             precise — catches "OPQ32r", "GSA", exact/near-exact names).
          2. Token-overlap fallback: every significant word in the
             query must appear somewhere in the candidate's name. This
             catches common abbreviated/paraphrased references like
             "Verify G+" -> "SHL Verify Interactive G+" that don't
             share a contiguous substring with the real catalog name.
        """
        name_query = name_query.strip().lower()
        if not name_query:
            return []
 
        substring_matches = [c for c in self.catalog if name_query in c["name"].lower()]
        if not substring_matches:
            substring_matches = [c for c in self.catalog if c["name"].lower() in name_query]
 
        tokens = [
            t for t in re.findall(r"[a-z0-9+]+", name_query)
            if t not in _STOPWORDS and len(t) > 1
        ]
        token_matches = (
            [c for c in self.catalog if all(t in c["name"].lower() for t in tokens)]
            if tokens else []
        )
 
        # BUGFIX: previously returned substring_matches immediately and
        # never even looked at token_matches once a substring hit was
        # found. That silently drops the actually-correct catalog entry
        # whenever a paraphrased/abbreviated query (e.g. "Verify G+")
        # is a contiguous substring of one variant's name (e.g. "Verify
        # G+ - Candidate Report") but NOT of the canonical one (e.g.
        # "SHL Verify Interactive G+", where "Interactive" breaks the
        # contiguous match). Now we union both passes — substring hits
        # first (most precise, kept as the preferred ordering) followed
        # by any additional token-overlap hits — so downstream callers
        # (e.g. agent.py's shortest-name-wins resolver) actually get to
        # consider the canonical item instead of never seeing it.
        seen_urls = set()
        merged: List[Dict[str, Any]] = []
        for c in substring_matches + token_matches:
            if c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                merged.append(c)
        return merged
    
 
 
 
 