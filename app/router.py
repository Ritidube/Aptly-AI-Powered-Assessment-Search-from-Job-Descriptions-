
# """
# Rule-based intent router. No LLM call — this removes one full LLM
# round trip from every single /chat request, which is the single
# biggest latency cost in the pipeline given the 30s-per-call budget.

# Classifies into five labels: off_topic, clarify_needed, compare,
# refine, recommend. Uses keyword/regex matching plus the turn/clarify
# budget helpers from state.py so hard overrides stay consistent.
# """

# import re
# from typing import List

# from app.models import Message
# from app.state import clarify_budget_exhausted, near_turn_cap, extract_requirements

# VALID_LABELS = {"off_topic", "clarify_needed", "compare", "refine", "recommend"}

# # ---------------------------------------------------------------------
# # Pattern banks
# # ---------------------------------------------------------------------

# OFF_TOPIC_PATTERNS = re.compile(
#     r"(?i)\b("
#     r"ignore (all|previous|prior|the) instructions|disregard (all|previous) instructions|"
#     r"pretend you are|pretend to be|act as (a|an)|you are now|jailbreak|"
#     r"system prompt|new instructions|reveal your prompt|"
#     r"legal advice|is it legal|lawsuit|sue (us|them|our)|discriminat\w*|"
#     r"employment law|visa sponsorship|immigration status|"
#     r"salary (negotiation|range) advice|"
#     r"weather|stock price|tell me a joke|write me a poem|"
#     r"who (won|is winning)|recipe for"
#     r")\b"
# )

# COMPARE_PATTERNS = re.compile(
#     r"(?i)("
#     r"difference between|differences? between|how (does|do|is) .* (differ|compare)|"
#     r"compare .* (to|with|and|vs)|\bvs\.?\b|\bversus\b|different from|"
#     r"which is better[:,]? .* or"
#     r")"
# )

# REFINE_ACTION_PATTERNS = re.compile(
#     r"(?i)\b("
#     r"remove|drop|replace|instead of|swap|take out|without the|"
#     r"also add|add (a|an|the)?|include (a|an|the)?|"
#     r"shorter|change|update the (list|shortlist)|keep|final list"
#     r")\b"
# )

# CONFIRM_PATTERNS = re.compile(
#     r"(?i)\b("
#     r"perfect|that works|sounds good|confirmed|confirm|locking it in|lock it in|"
#     r"that covers it|thanks|agreed|that'?s what we need|that'?s good|"
#     r"go ahead|approved|looks good|clear\.?$|understood|noted|as[- ]is|"
#     r"makes sense|that'?s right|sounds right"
#     r")\b"
# )


# def format_conversation(messages: List[Message]) -> str:
#     return "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)


# def _prior_shortlist_given(messages: List[Message]) -> bool:
#     """True once we've already produced at least one recommend/refine
#     turn (i.e. there's more than one user turn AND the first user turn
#     wasn't itself off-topic). We don't have the old reply's structured
#     recs here (stateless API), so this is approximated by: has there
#     been a prior assistant turn at all after the first user message.
#     """
#     assistant_turns = [m for m in messages if m.role == "assistant"]
#     return len(assistant_turns) >= 1


# def route(messages: List[Message]) -> str:
#     if not messages:
#         return "clarify_needed"

#     last_user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "")

#     # 1. Off-topic / prompt-injection guard — highest priority
#     if OFF_TOPIC_PATTERNS.search(last_user_msg):
#         return "off_topic"

#     # 2. Explicit comparison request
#     if COMPARE_PATTERNS.search(last_user_msg):
#         return "compare"

#     has_prior_turn = _prior_shortlist_given(messages)

#     # 3. Refinement/confirmation of an EXISTING shortlist only counts
#     #    once a shortlist could plausibly already exist.
#     if has_prior_turn and (
#         REFINE_ACTION_PATTERNS.search(last_user_msg) or CONFIRM_PATTERNS.search(last_user_msg)
#     ):
#         label = "refine"
#     else:
#         req = extract_requirements(messages)
#         label = "clarify_needed" if req.is_empty() else "recommend"

#     # Hard overrides — identical to prior behavior
#     if label == "clarify_needed" and clarify_budget_exhausted(messages):
#         label = "recommend"
#     if label == "clarify_needed" and near_turn_cap(messages):
#         label = "recommend"

#     return label


# """
# Rule-based intent router. Replaces the old LLM router call entirely —
# this removes one full LLM round trip from every single /chat request,
# which was the single biggest latency cost in the pipeline.

# Classifies into the same five labels the rest of the app already
# expects: off_topic, clarify_needed, compare, refine, recommend.
# Uses simple keyword matching + the existing turn/clarify-budget state
# from state.py (unchanged) so the hard-override behavior is identical
# to before.
# """

# import re
# from typing import List

# from app.models import Message
# from app.state import clarify_budget_exhausted, near_turn_cap


# VALID_LABELS = {"off_topic", "clarify_needed", "compare", "refine", "recommend"}

# # ---------------------------------------------------------------------
# # Pattern banks
# # ---------------------------------------------------------------------

# OFF_TOPIC_PATTERNS = re.compile(
#     r"(?i)\b("
#     r"ignore (all|previous|prior|the) instructions|disregard (all|previous) instructions|"
#     r"pretend you are|pretend to be|act as (a|an)|you are now|jailbreak|"
#     r"system prompt|new instructions|"
#     r"legal advice|is it legal|lawsuit|sue (us|them|our)|discriminat\w*|"
#     r"employment law|visa sponsorship|immigration status|"
#     r"salary (negotiation|range) advice|"
#     r"weather|stock price|tell me a joke|write me a poem|"
#     r"who (won|is winning)|recipe for"
#     r")\b"
# )

# COMPARE_PATTERNS = re.compile(
#     r"(?i)("
#     r"difference between|differences? between|how (does|do|is) .* (differ|compare)|"
#     r"compare .* (to|with|and|vs)|\bvs\.?\b|\bversus\b|different from|"
#     r"which is better[:,]? .* or"
#     r")"
# )

# # Words signalling the user wants to change/confirm an EXISTING shortlist
# REFINE_ACTION_PATTERNS = re.compile(
#     r"(?i)\b("
#     r"remove|drop|replace|instead of|swap|take out|without the|"
#     r"also add|add (a|an|the)?|include (a|an|the)?|"
#     r"shorter|change|update the (list|shortlist)|keep|final list"
#     r")\b"
# )

# CONFIRM_PATTERNS = re.compile(
#     r"(?i)\b("
#     r"perfect|that works|sounds good|confirmed|confirm|locking it in|lock it in|"
#     r"that covers it|thanks|agreed|that'?s what we need|that'?s good|"
#     r"go ahead|approved|looks good|clear\.?$|understood|noted|as[- ]is|"
#     r"makes sense|that'?s right|sounds right"
#     r")\b"
# )

# # Loose signal that the user has given SOME concrete hiring context
# # (role, level, skill, domain) worth searching the catalog for.
# CONTEXT_SIGNAL_PATTERNS = re.compile(
#     r"(?i)\b("
#     r"engineer|developer|programmer|analyst|manager|director|executive|"
#     r"cxo|leadership|sales|customer service|contact cent(er|re)|call cent(er|re)|"
#     r"admin|clerk|technician|operator|plant|graduate|trainee|entry.level|"
#     r"senior|junior|mid.level|intern|"
#     r"cognitive|personality|situational|reasoning|numerical|verbal|"
#     r"java|python|sql|excel|word|aws|docker|angular|spring|rust|coding|programming|"
#     r"healthcare|nurse|patient|finance|financial|accountant|banking|"
#     r"safety|compliance|dependability|"
#     r"assessment|test|screen(ing)?|hiring|recruit|candidate|battery|shortlist"
#     r")\b"
# )


# def format_conversation(messages: List[Message]) -> str:
#     lines = []
#     for m in messages:
#         lines.append(f"{m.role.upper()}: {m.content}")
#     return "\n".join(lines)


# def _prior_shortlist_given(messages: List[Message]) -> bool:
#     """
#     True if an earlier assistant turn already produced a recommendation
#     list. Our RECOMMEND_PROMPT format always emits pipe-delimited
#     "- name | url" lines with an http(s) link, so that's a cheap and
#     reliable fingerprint — no LLM needed to detect it.
#     """
#     for m in messages[:-1]:
#         if m.role == "assistant" and "|" in m.content and "http" in m.content.lower():
#             return True
#     return False


# def route(messages: List[Message]) -> str:
#     if not messages:
#         return "clarify_needed"

#     last_user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "")

#     # 1. Off-topic / prompt-injection guard — highest priority, checked first
#     if OFF_TOPIC_PATTERNS.search(last_user_msg):
#         return "off_topic"

#     # 2. Explicit comparison request
#     if COMPARE_PATTERNS.search(last_user_msg):
#         return "compare"

#     has_shortlist = _prior_shortlist_given(messages)

#     # 3. Refinement / confirmation of an EXISTING shortlist only counts
#     #    as "refine" if a shortlist actually exists yet — otherwise these
#     #    same words are just normal conversational filler.
#     if has_shortlist and (
#         REFINE_ACTION_PATTERNS.search(last_user_msg) or CONFIRM_PATTERNS.search(last_user_msg)
#     ):
#         label = "refine"
#     else:
#         # 4. Enough concrete context anywhere in the conversation to search on?
#         has_context = bool(CONTEXT_SIGNAL_PATTERNS.search(format_conversation(messages)))
#         label = "recommend" if has_context else "clarify_needed"

#     # Hard overrides regardless of heuristic result — identical to old behavior
#     if label == "clarify_needed" and clarify_budget_exhausted(messages):
#         label = "recommend"
#     if label == "clarify_needed" and near_turn_cap(messages):
#         label = "recommend"

#     return label


"""
Rule-based intent router. No LLM call — this removes one full LLM
round trip from every single /chat request, which is the single
biggest latency cost in the pipeline given the 30s-per-call budget.

Classifies into five labels: off_topic, clarify_needed, compare,
refine, recommend. Uses keyword/regex matching plus the turn/clarify
budget helpers from state.py so hard overrides stay consistent.
"""

import re
from typing import List

from app.models import Message
from app.state import clarify_budget_exhausted, near_turn_cap, extract_requirements

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
        req = extract_requirements(messages)
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

    return label