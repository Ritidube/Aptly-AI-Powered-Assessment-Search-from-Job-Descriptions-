"""
Rule-based intent router. No LLM call — this removes one full LLM
round trip from every single /chat request, which is the single
biggest latency cost in the pipeline given the 30s-per-call budget.

Classifies into five labels: off_topic, clarify_needed, compare,
refine, recommend. Uses keyword/regex matching plus the turn/clarify
budget helpers from state.py so hard overrides stay consistent.
"""

import logging
import re
from typing import List

from app.models import Message
from app.state import (
    clarify_budget_exhausted,
    near_turn_cap,
    extract_requirements,
    REQUIREMENTS_RECENT_TURNS,
)

logger = logging.getLogger("shl.router")

VALID_LABELS = {"off_topic", "clarify_needed", "compare", "refine", "recommend"}

# ---------------------------------------------------------------------
# Pattern banks
# ---------------------------------------------------------------------

OFF_TOPIC_PATTERNS = re.compile(
    r"(?i)\b("
    r"ignore (all|previous|prior|the) instructions|disregard (all|previous) instructions|"
    r"pretend you are|pretend to be|act as (a|an)|you are now|jailbreak|"
    r"system prompt|new instructions|reveal your prompt|"
    r"legal advice|is it legal|lawsuit|sue (us|them|our)|discriminat\w*|"
    r"employment law|visa sponsorship|immigration status|"
    r"salary (negotiation|range) advice|"
    r"weather|stock price|tell me a joke|write me a poem|"
    r"who (won|is winning)|recipe for"
    r")\b"
)

COMPARE_PATTERNS = re.compile(
    r"(?i)("
    r"difference between|differences? between|how (does|do|is) .* (differ|compare)|"
    r"compare .* (to|with|and|vs)|\bvs\.?\b|\bversus\b|different from|"
    r"which is better[:,]? .* or"
    r")"
)

REFINE_ACTION_PATTERNS = re.compile(
    r"(?i)\b("
    r"remove|drop|replace|instead of|swap|take out|without the|"
    r"also add|add (a|an|the)?|include (a|an|the)?|"
    r"shorter|change|update the (list|shortlist)|keep|final list"
    r")\b"
)

CONFIRM_PATTERNS = re.compile(
    r"(?i)\b("
    r"perfect|that works|sounds good|confirmed|confirm|locking it in|lock it in|"
    r"that covers it|thanks|agreed|that'?s what we need|that'?s good|"
    r"go ahead|approved|looks good|clear\.?$|understood|noted|as[- ]is|"
    r"makes sense|that'?s right|sounds right"
    r")\b"
)


def format_conversation(messages: List[Message]) -> str:
    return "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)


def _prior_shortlist_given(messages: List[Message]) -> bool:
    """True once we've already produced at least one recommend/refine
    turn (i.e. there's more than one user turn AND the first user turn
    wasn't itself off-topic). We don't have the old reply's structured
    recs here (stateless API), so this is approximated by: has there
    been a prior assistant turn at all after the first user message.
    """
    assistant_turns = [m for m in messages if m.role == "assistant"]
    return len(assistant_turns) >= 1


def route(messages: List[Message]) -> str:
    if not messages:
        return "clarify_needed"

    last_user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "")

    # 1. Off-topic / prompt-injection guard — highest priority
    if OFF_TOPIC_PATTERNS.search(last_user_msg):
        return "off_topic"

    # 2. Explicit comparison request
    if COMPARE_PATTERNS.search(last_user_msg):
        return "compare"

    has_prior_turn = _prior_shortlist_given(messages)

    # 3. Refinement/confirmation of an EXISTING shortlist only counts
    #    once a shortlist could plausibly already exist.
    if has_prior_turn and (
        REFINE_ACTION_PATTERNS.search(last_user_msg) or CONFIRM_PATTERNS.search(last_user_msg)
    ):
        label = "refine"
    else:
        # extract_requirements() accumulates over the WHOLE conversation,
        # so on turn 2+ it can still be non-empty purely from earlier
        # turns even if the CURRENT message is a total non-sequitur
        # ("how to make paneer?"). Left unchecked, that stale signal
        # would silently push us to "recommend" and re-answer the old
        # question instead of reacting to what was actually just said.
        #
        # Guard against that: if there's prior context, first check
        # whether the latest message alone contributes anything new. If
        # it doesn't, fall back to clarify_needed — the same path a
        # first-turn message with no signal would take — rather than
        # trusting leftover history from earlier turns.
        if has_prior_turn:
            last_msg_only = extract_requirements(
                [Message(role="user", content=last_user_msg)]
            )
            if last_msg_only.is_empty():
                label = "clarify_needed"
                if label == "clarify_needed" and clarify_budget_exhausted(messages):
                    label = "recommend"
                if label == "clarify_needed" and near_turn_cap(messages):
                    label = "recommend"
                logger.debug("route_classified", extra={"route_label": label, "turn_count": len(messages)})
                return label

        req = extract_requirements(messages, recent_turns=REQUIREMENTS_RECENT_TURNS)
        if req.is_empty():
            label = "clarify_needed"
        elif req.critical_missing():
            # Enough general context exists (role/level/skill), but a
            # constraint that changes WHICH item is correct — e.g. call
            # language for a contact-centre role — hasn't been given
            # yet. Ask for it before committing to a shortlist rather
            # than recommending a possibly-wrong-language assessment.
            label = "clarify_needed"
        else:
            label = "recommend"

    # Hard overrides — identical to prior behavior
    if label == "clarify_needed" and clarify_budget_exhausted(messages):
        label = "recommend"
    if label == "clarify_needed" and near_turn_cap(messages):
        label = "recommend"

    logger.debug("route_classified", extra={"route_label": label, "turn_count": len(messages)})
    return label