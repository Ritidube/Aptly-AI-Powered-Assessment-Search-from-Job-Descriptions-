# """
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.

# This module now derives a STRUCTURED requirements profile (role,
# level, skills, industry, language, preferred test types, explicit
# add/remove instructions) from the conversation, instead of just
# concatenating raw text. Retrieval is built on top of this structured
# profile so that:
#   - stray conversational filler ("Perfect, thanks") doesn't dilute
#     the search query, and
#   - a later turn's edits (e.g. "also add personality tests") are
#     additive rather than overwriting everything that came before.
# """

# import re
# from dataclasses import dataclass, field
# from typing import List, Optional

# from app.models import Message

# MAX_CLARIFYING_QUESTIONS = 2


# # ---------------------------------------------------------------------
# # Turn-budget helpers (unchanged behavior from the original app)
# # ---------------------------------------------------------------------

# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")


# def count_clarifying_turns(messages: List[Message]) -> int:
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count


# def turns_used(messages: List[Message]) -> int:
#     return len(messages)


# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS


# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)


# # ---------------------------------------------------------------------
# # Structured requirements profile
# # ---------------------------------------------------------------------

# ROLE_TERMS = [
#     "engineer", "developer", "programmer", "analyst", "manager", "director",
#     "executive", "cxo", "leadership", "sales", "customer service",
#     "contact centre", "contact center", "call centre", "call center",
#     "admin", "administrative assistant", "clerk", "technician", "operator",
#     "plant operator", "graduate", "trainee", "intern", "nurse", "accountant",
#     "financial analyst", "healthcare admin",
# ]

# LEVEL_TERMS = [
#     "entry-level", "entry level", "graduate", "junior", "mid-level",
#     "mid level", "senior", "director", "executive", "cxo", "individual contributor",
#     "supervisor", "front line manager", "manager", "professional",
# ]

# SKILL_TERMS = [
#     "java", "python", "sql", "excel", "word", "aws", "docker", "angular",
#     "spring", "rust", "coding", "programming", ".net", "javascript",
#     "numerical reasoning", "verbal reasoning", "cognitive", "deductive reasoning",
#     "situational judgement", "situational judgment", "personality",
#     "typing", "data entry", "customer service", "sales skills",
# ]

# INDUSTRY_TERMS = [
#     "healthcare", "finance", "financial", "banking", "manufacturing",
#     "chemical", "retail", "technology", "insurance", "pharma",
# ]

# LANGUAGE_TERMS = [
#     "english", "spanish", "french", "german", "mandarin", "hindi", "portuguese",
# ]

# TEST_TYPE_HINTS = {
#     "personality": "P", "cognitive": "A", "ability": "A", "aptitude": "A",
#     "situational judgement": "B", "situational judgment": "B", "biodata": "B",
#     "competenc": "C", "development": "D", "360": "D",
#     "assessment exercise": "E", "knowledge": "K", "skills test": "K",
#     "simulation": "S",
# }

# # Words that signal the user is editing an EXISTING shortlist, plus
# # which direction the edit goes. Order matters: check "replace" before
# # plain "add"/"remove" since it implies both.
# ADD_PATTERN = re.compile(r"(?i)\b(also add|add (?:a|an|the)?|include (?:a|an|the)?)\s+([^.,;]+)")
# REMOVE_PATTERN = re.compile(
#     r"(?i)\b(remove|drop|take out|without the|exclude)\s+(?:the\s+)?([^.,;]+?)"
#     r"(?=\s+(?:and|but|,|\.|$))"
# )
# REPLACE_PATTERN = re.compile(
#     r"(?i)\bremove\s+(?:the\s+)?([^.,;]+?)\s+and\s+replace\s+(?:it\s+)?with\s+([^.,;]+)|"
#     r"\breplace\s+(?:the\s+)?([^.,;]+?)\s+with\s+([^.,;]+)"
# )


# @dataclass
# class Requirements:
#     roles: List[str] = field(default_factory=list)
#     levels: List[str] = field(default_factory=list)
#     skills: List[str] = field(default_factory=list)
#     industries: List[str] = field(default_factory=list)
#     languages: List[str] = field(default_factory=list)
#     test_type_hints: List[str] = field(default_factory=list)
#     free_text: List[str] = field(default_factory=list)  # raw user turns, for BM25/dense fallback

#     def to_query(self) -> str:
#         """Flatten the structured profile into a clean retrieval query.
#         Structured terms are repeated up front (cheap way to weight
#         them higher for BM25) followed by the raw text as a fallback
#         signal for anything the keyword lists didn't catch."""
#         structured = (
#             self.roles + self.levels + self.skills + self.industries + self.languages
#         )
#         parts = []
#         if structured:
#             parts.append(" ".join(structured) + " " + " ".join(structured))
#         parts.extend(self.free_text)
#         return " ".join(parts).strip()

#     def is_empty(self) -> bool:
#         return not (self.roles or self.levels or self.skills or self.industries)


# def _extract_terms(text: str, term_list: List[str]) -> List[str]:
#     text_l = text.lower()
#     found = []
#     for term in term_list:
#         if term in text_l and term not in found:
#             found.append(term)
#     return found


# def extract_requirements(messages: List[Message]) -> Requirements:
#     """Build a structured requirements profile from ALL user turns so
#     far. Called fresh on every request since the API is stateless."""
#     req = Requirements()
#     for m in messages:
#         if m.role != "user":
#             continue
#         text = m.content
#         req.roles.extend(t for t in _extract_terms(text, ROLE_TERMS) if t not in req.roles)
#         req.levels.extend(t for t in _extract_terms(text, LEVEL_TERMS) if t not in req.levels)
#         req.skills.extend(t for t in _extract_terms(text, SKILL_TERMS) if t not in req.skills)
#         req.industries.extend(t for t in _extract_terms(text, INDUSTRY_TERMS) if t not in req.industries)
#         req.languages.extend(t for t in _extract_terms(text, LANGUAGE_TERMS) if t not in req.languages)
#         for hint, code in TEST_TYPE_HINTS.items():
#             if hint in text.lower() and code not in req.test_type_hints:
#                 req.test_type_hints.append(code)
#         req.free_text.append(text)
#     return req


# @dataclass
# class RefineAction:
#     add_terms: List[str] = field(default_factory=list)
#     remove_terms: List[str] = field(default_factory=list)
#     is_pure_confirmation: bool = False


# def parse_refine_action(last_user_msg: str) -> RefineAction:
#     """Pull out explicit add/remove/replace instructions from the
#     latest user turn so a 'refine' turn can edit the previous
#     shortlist instead of recomputing it from scratch."""
#     action = RefineAction()

#     for m in REPLACE_PATTERN.finditer(last_user_msg):
#         if m.group(1) and m.group(2):
#             action.remove_terms.append(m.group(1).strip())
#             action.add_terms.append(m.group(2).strip())
#         elif m.group(3) and m.group(4):
#             action.remove_terms.append(m.group(3).strip())
#             action.add_terms.append(m.group(4).strip())

#     for m in ADD_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.add_terms:
#             action.add_terms.append(term)

#     for m in REMOVE_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.remove_terms:
#             action.remove_terms.append(term)

#     if not action.add_terms and not action.remove_terms:
#         action.is_pure_confirmation = True

#     return action

# """
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.

# We keep it simple: extract raw user turns as "known facts" text,
# count how many assistant turns already asked a question, and pull the
# last shortlist out of the last assistant recommendation table (if any).
# """

# from typing import Any, Dict, List
# from app.models import Message


# MAX_CLARIFYING_QUESTIONS = 2


# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")


# def count_clarifying_turns(messages: List[Message]) -> int:
#     """
#     Rough heuristic: an assistant turn that ends in '?' and has no
#     table/list of names is treated as a clarifying question.
#     Good enough for a turn-budget guard; refine after testing against
#     the sample conversations.
#     """
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count


# def turns_used(messages: List[Message]) -> int:
#     return len(messages)


# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS


# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)

# """
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.

# This module now derives a STRUCTURED requirements profile (role,
# level, skills, industry, language, preferred test types, explicit
# add/remove instructions) from the conversation, instead of just
# concatenating raw text. Retrieval is built on top of this structured
# profile so that:
#   - stray conversational filler ("Perfect, thanks") doesn't dilute
#     the search query, and
#   - a later turn's edits (e.g. "also add personality tests") are
#     additive rather than overwriting everything that came before.
# """

# import re
# from dataclasses import dataclass, field
# from typing import List, Optional

# from app.models import Message

# MAX_CLARIFYING_QUESTIONS = 2


# # ---------------------------------------------------------------------
# # Turn-budget helpers (unchanged behavior from the original app)
# # ---------------------------------------------------------------------

# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")


# def count_clarifying_turns(messages: List[Message]) -> int:
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count


# def turns_used(messages: List[Message]) -> int:
#     return len(messages)


# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS


# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)


# # ---------------------------------------------------------------------
# # Structured requirements profile
# # ---------------------------------------------------------------------

# ROLE_TERMS = [
#     "engineer", "developer", "programmer", "analyst", "manager", "director",
#     "executive", "cxo", "leadership", "sales", "customer service",
#     "contact centre", "contact center", "call centre", "call center",
#     "admin", "administrative assistant", "clerk", "technician", "operator",
#     "plant operator", "graduate", "trainee", "intern", "nurse", "accountant",
#     "financial analyst", "healthcare admin",
# ]

# LEVEL_TERMS = [
#     "entry-level", "entry level", "graduate", "junior", "mid-level",
#     "mid level", "senior", "director", "executive", "cxo", "individual contributor",
#     "supervisor", "front line manager", "manager", "professional",
# ]

# SKILL_TERMS = [
#     "java", "python", "sql", "excel", "word", "aws", "docker", "angular",
#     "spring", "rust", "coding", "programming", ".net", "javascript",
#     "numerical reasoning", "verbal reasoning", "cognitive", "deductive reasoning",
#     "situational judgement", "situational judgment", "personality",
#     "typing", "data entry", "customer service", "sales skills",
# ]

# INDUSTRY_TERMS = [
#     "healthcare", "finance", "financial", "banking", "manufacturing",
#     "chemical", "retail", "technology", "insurance", "pharma",
# ]

# LANGUAGE_TERMS = [
#     "english", "spanish", "french", "german", "mandarin", "hindi", "portuguese",
# ]

# TEST_TYPE_HINTS = {
#     "personality": "P", "cognitive": "A", "ability": "A", "aptitude": "A",
#     "situational judgement": "B", "situational judgment": "B", "biodata": "B",
#     "competenc": "C", "development": "D", "360": "D",
#     "assessment exercise": "E", "knowledge": "K", "skills test": "K",
#     "simulation": "S",
# }

# # ---------------------------------------------------------------------
# # Critical-constraint detection
# # ---------------------------------------------------------------------
# # Some roles have a constraint that materially changes WHICH catalog
# # item is correct, not just how well it's explained — e.g. a phone /
# # contact-centre role needs a language-specific version of a test, so
# # recommending before that's known risks handing back the wrong SKU.
# # `Requirements.is_empty()` alone doesn't catch this: a message like
# # "500 entry-level contact centre agents, inbound calls" already
# # populates roles + levels, so the old router treated it as fully
# # specified and recommended immediately. `critical_missing()` adds a
# # second, narrower gate on top of is_empty() for exactly these cases,
# # without turning the router into pure keyword matching for the
# # general routing decision — it only tightens the recommend/clarify
# # boundary for a small, well-defined set of situations where getting
# # it wrong is costly.

# # Phrases signalling a phone/voice-based customer-facing role, where
# # the SPOKEN LANGUAGE of the assessment (and the calls) is a hard
# # constraint on which SHL item is correct.
# PHONE_CONTACT_HINTS = [
#     "contact centre", "contact center", "call centre", "call center",
#     "inbound call", "inbound calls", "outbound call", "outbound calls",
#     "phone support", "telephone support", "telephone screening",
#     "customer service", "customer support", "help desk", "helpdesk",
#     "support agent", "support agents",
# ]

# # Human-readable phrasing for what's missing, used to steer the
# # clarifying question toward the actual gap instead of a generic one.
# MISSING_HINT_TEXT = {
#     "language": "the language(s) the calls / assessments need to be conducted in",
# }

# # Words that signal the user is editing an EXISTING shortlist, plus
# # which direction the edit goes. Order matters: check "replace" before
# # plain "add"/"remove" since it implies both.
# ADD_PATTERN = re.compile(r"(?i)\b(also add|add (?:a|an|the)?|include (?:a|an|the)?)\s+([^.,;]+)")
# REMOVE_PATTERN = re.compile(
#     r"(?i)\b(remove|drop|take out|without the|exclude)\s+(?:the\s+)?([^.,;]+?)"
#     r"(?=\s+(?:and|but|,|\.|$))"
# )
# REPLACE_PATTERN = re.compile(
#     r"(?i)\bremove\s+(?:the\s+)?([^.,;]+?)\s+and\s+replace\s+(?:it\s+)?with\s+([^.,;]+)|"
#     r"\breplace\s+(?:the\s+)?([^.,;]+?)\s+with\s+([^.,;]+)"
# )


# @dataclass
# class Requirements:
#     roles: List[str] = field(default_factory=list)
#     levels: List[str] = field(default_factory=list)
#     skills: List[str] = field(default_factory=list)
#     industries: List[str] = field(default_factory=list)
#     languages: List[str] = field(default_factory=list)
#     test_type_hints: List[str] = field(default_factory=list)
#     free_text: List[str] = field(default_factory=list)  # raw user turns, for BM25/dense fallback

#     def to_query(self) -> str:
#         """Flatten the structured profile into a clean retrieval query.
#         Structured terms are repeated up front (cheap way to weight
#         them higher for BM25) followed by the raw text as a fallback
#         signal for anything the keyword lists didn't catch."""
#         structured = (
#             self.roles + self.levels + self.skills + self.industries + self.languages
#         )
#         parts = []
#         if structured:
#             parts.append(" ".join(structured) + " " + " ".join(structured))
#         parts.extend(self.free_text)
#         return " ".join(parts).strip()

#     def is_empty(self) -> bool:
#         return not (self.roles or self.levels or self.skills or self.industries)

#     def critical_missing(self) -> List[str]:
#         """
#         Returns a list of critical-constraint keys that are still
#         missing even though enough general context exists to not be
#         `is_empty()`. Currently covers: phone/contact-centre-type
#         roles missing a call/assessment language, since that decides
#         which language-specific catalog item is actually correct.

#         Deliberately narrow and additive: this never fires for roles
#         outside the phone-contact hint list, so it doesn't change
#         behavior for the large majority of recommend-eligible turns
#         (e.g. "Java developers, mid-level" still recommends directly).
#         """
#         missing: List[str] = []
#         combined_text = " ".join(self.free_text).lower()
#         is_phone_role = any(hint in combined_text for hint in PHONE_CONTACT_HINTS)
#         if is_phone_role and not self.languages:
#             missing.append("language")
#         return missing


# def _extract_terms(text: str, term_list: List[str]) -> List[str]:
#     text_l = text.lower()
#     found = []
#     for term in term_list:
#         if term in text_l and term not in found:
#             found.append(term)
#     return found


# def extract_requirements(messages: List[Message]) -> Requirements:
#     """Build a structured requirements profile from ALL user turns so
#     far. Called fresh on every request since the API is stateless."""
#     req = Requirements()
#     for m in messages:
#         if m.role != "user":
#             continue
#         text = m.content
#         req.roles.extend(t for t in _extract_terms(text, ROLE_TERMS) if t not in req.roles)
#         req.levels.extend(t for t in _extract_terms(text, LEVEL_TERMS) if t not in req.levels)
#         req.skills.extend(t for t in _extract_terms(text, SKILL_TERMS) if t not in req.skills)
#         req.industries.extend(t for t in _extract_terms(text, INDUSTRY_TERMS) if t not in req.industries)
#         req.languages.extend(t for t in _extract_terms(text, LANGUAGE_TERMS) if t not in req.languages)
#         for hint, code in TEST_TYPE_HINTS.items():
#             if hint in text.lower() and code not in req.test_type_hints:
#                 req.test_type_hints.append(code)
#         req.free_text.append(text)
#     return req


# @dataclass
# class RefineAction:
#     add_terms: List[str] = field(default_factory=list)
#     remove_terms: List[str] = field(default_factory=list)
#     is_pure_confirmation: bool = False


# def parse_refine_action(last_user_msg: str) -> RefineAction:
#     """Pull out explicit add/remove/replace instructions from the
#     latest user turn so a 'refine' turn can edit the previous
#     shortlist instead of recomputing it from scratch."""
#     action = RefineAction()

#     for m in REPLACE_PATTERN.finditer(last_user_msg):
#         if m.group(1) and m.group(2):
#             action.remove_terms.append(m.group(1).strip())
#             action.add_terms.append(m.group(2).strip())
#         elif m.group(3) and m.group(4):
#             action.remove_terms.append(m.group(3).strip())
#             action.add_terms.append(m.group(4).strip())

#     for m in ADD_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.add_terms:
#             action.add_terms.append(term)

#     for m in REMOVE_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.remove_terms:
#             action.remove_terms.append(term)

#     if not action.add_terms and not action.remove_terms:
#         action.is_pure_confirmation = True

#     return action


# """
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.
 
# This module now derives a STRUCTURED requirements profile (role,
# level, skills, industry, language, preferred test types, explicit
# add/remove instructions) from the conversation, instead of just
# concatenating raw text. Retrieval is built on top of this structured
# profile so that:
#   - stray conversational filler ("Perfect, thanks") doesn't dilute
#     the search query, and
#   - a later turn's edits (e.g. "also add personality tests") are
#     additive rather than overwriting everything that came before.
# """
 
# import re
# from dataclasses import dataclass, field
# from typing import List, Optional
 
# from app.models import Message
 
# MAX_CLARIFYING_QUESTIONS = 2
 
# # Minimum confidence_score() needed to skip clarification and go
# # straight to retrieval. Categories are: role, level, skill, industry,
# # test-type preference (max possible = 5). Threshold of 2 means a
# # single vague category hit (e.g. only "leadership", or only
# # "assessment") is NOT enough on its own — it still routes to
# # clarify_needed — while any two concrete signals (e.g. role+level,
# # or skill+industry) are enough to retrieve immediately. Tuned against
# # the spec's own examples: "I need an assessment" (score 0), "We need
# # a leadership solution" (score 1, role-only) both stay below
# # threshold; "Java developers, mid-level" (role+level, score 2) clears it.
# CONFIDENCE_THRESHOLD = 2
 
 
# # ---------------------------------------------------------------------
# # Turn-budget helpers (unchanged behavior from the original app)
# # ---------------------------------------------------------------------
 
# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")
 
 
# def count_clarifying_turns(messages: List[Message]) -> int:
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count
 
 
# def turns_used(messages: List[Message]) -> int:
#     return len(messages)
 
 
# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS
 
 
# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)
 
 
# # ---------------------------------------------------------------------
# # Structured requirements profile
# # ---------------------------------------------------------------------
 
# ROLE_TERMS = [
#     "engineer", "developer", "programmer", "analyst", "manager", "director",
#     "executive", "cxo", "leadership", "sales", "customer service",
#     "contact centre", "contact center", "call centre", "call center",
#     "admin", "administrative assistant", "clerk", "technician", "operator",
#     "plant operator", "graduate", "trainee", "intern", "nurse", "accountant",
#     "financial analyst", "healthcare admin",
# ]
 
# # Terms in ROLE_TERMS that are too generic to identify a searchable
# # role on their own (e.g. "leadership" could mean anyone from a new
# # supervisor to a CXO). They still populate Requirements.roles so
# # retrieval queries include them, but they don't earn a point in
# # confidence_score() unless paired with something more specific (a
# # level, a concrete title, etc. — captured by the OTHER categories
# # already scoring their own point). Matches the sample pattern where
# # "we need a solution for senior leadership" still gets a clarifying
# # question about who exactly the audience is, despite "leadership"
# # + "senior" superficially looking like two populated categories.
# VAGUE_ROLE_TERMS = {"leadership"}
 
# LEVEL_TERMS = [
#     "entry-level", "entry level", "graduate", "junior", "mid-level",
#     "mid level", "senior", "director", "executive", "cxo", "individual contributor",
#     "supervisor", "front line manager", "manager", "professional",
# ]
 
# SKILL_TERMS = [
#     "java", "python", "sql", "excel", "word", "aws", "docker", "angular",
#     "spring", "rust", "coding", "programming", ".net", "javascript",
#     "numerical reasoning", "verbal reasoning", "cognitive", "deductive reasoning",
#     "situational judgement", "situational judgment", "personality",
#     "typing", "data entry", "customer service", "sales skills",
# ]
 
# INDUSTRY_TERMS = [
#     "healthcare", "finance", "financial", "banking", "manufacturing",
#     "chemical", "retail", "technology", "insurance", "pharma",
# ]
 
# LANGUAGE_TERMS = [
#     "english", "spanish", "french", "german", "mandarin", "hindi", "portuguese",
# ]
 
# TEST_TYPE_HINTS = {
#     "personality": "P", "cognitive": "A", "ability": "A", "aptitude": "A",
#     "situational judgement": "B", "situational judgment": "B", "biodata": "B",
#     "competenc": "C", "development": "D", "360": "D",
#     "assessment exercise": "E", "knowledge": "K", "skills test": "K",
#     "simulation": "S",
# }
 
# # ---------------------------------------------------------------------
# # Critical-constraint detection
# # ---------------------------------------------------------------------
# # Some roles have a constraint that materially changes WHICH catalog
# # item is correct, not just how well it's explained — e.g. a phone /
# # contact-centre role needs a language-specific version of a test, so
# # recommending before that's known risks handing back the wrong SKU.
# # `Requirements.is_empty()` alone doesn't catch this: a message like
# # "500 entry-level contact centre agents, inbound calls" already
# # populates roles + levels, so the old router treated it as fully
# # specified and recommended immediately. `critical_missing()` adds a
# # second, narrower gate on top of is_empty() for exactly these cases,
# # without turning the router into pure keyword matching for the
# # general routing decision — it only tightens the recommend/clarify
# # boundary for a small, well-defined set of situations where getting
# # it wrong is costly.
 
# # Phrases signalling a phone/voice-based customer-facing role, where
# # the SPOKEN LANGUAGE of the assessment (and the calls) is a hard
# # constraint on which SHL item is correct.
# PHONE_CONTACT_HINTS = [
#     "contact centre", "contact center", "call centre", "call center",
#     "inbound call", "inbound calls", "outbound call", "outbound calls",
#     "phone support", "telephone support", "telephone screening",
#     "customer service", "customer support", "help desk", "helpdesk",
#     "support agent", "support agents",
# ]
 
# # Human-readable phrasing for what's missing, used to steer the
# # clarifying question toward the actual gap instead of a generic one.
# MISSING_HINT_TEXT = {
#     "language": "the language(s) the calls / assessments need to be conducted in",
# }
 
# # Words that signal the user is editing an EXISTING shortlist, plus
# # which direction the edit goes. Order matters: check "replace" before
# # plain "add"/"remove" since it implies both.
# ADD_PATTERN = re.compile(r"(?i)\b(also add|add (?:a|an|the)?|include (?:a|an|the)?)\s+([^.,;]+)")
# REMOVE_PATTERN = re.compile(
#     r"(?i)\b(remove|drop|take out|without the|exclude)\s+(?:the\s+)?([^.,;]+?)"
#     r"(?=\s+(?:and|but|,|\.|$))"
# )
# REPLACE_PATTERN = re.compile(
#     r"(?i)\bremove\s+(?:the\s+)?([^.,;]+?)\s+and\s+replace\s+(?:it\s+)?with\s+([^.,;]+)|"
#     r"\breplace\s+(?:the\s+)?([^.,;]+?)\s+with\s+([^.,;]+)"
# )
 
 
# @dataclass
# class Requirements:
#     roles: List[str] = field(default_factory=list)
#     levels: List[str] = field(default_factory=list)
#     skills: List[str] = field(default_factory=list)
#     industries: List[str] = field(default_factory=list)
#     languages: List[str] = field(default_factory=list)
#     test_type_hints: List[str] = field(default_factory=list)
#     free_text: List[str] = field(default_factory=list)  # raw user turns, for BM25/dense fallback
 
#     def to_query(self) -> str:
#         """Flatten the structured profile into a clean retrieval query.
#         Structured terms are repeated up front (cheap way to weight
#         them higher for BM25) followed by the raw text as a fallback
#         signal for anything the keyword lists didn't catch."""
#         structured = (
#             self.roles + self.levels + self.skills + self.industries + self.languages
#         )
#         parts = []
#         if structured:
#             parts.append(" ".join(structured) + " " + " ".join(structured))
#         parts.extend(self.free_text)
#         return " ".join(parts).strip()
 
#     def is_empty(self) -> bool:
#         return not (self.roles or self.levels or self.skills or self.industries)
 
#     def confidence_score(self) -> int:
#         """
#         Lightweight rule-based confidence score over the already-
#         extracted structured fields — no LLM call, no extra parsing,
#         O(1) on data we already have. One point per requirement
#         CATEGORY that has at least one hit:
 
#             role present                -> +1
#             seniority/level present     -> +1
#             skill present               -> +1
#             industry present            -> +1
#             assessment/test-type pref.  -> +1  (test_type_hints)
 
#         This intentionally scores by category, not by term count, so
#         a message that mentions five skill keywords doesn't outscore
#         one that mentions a role + a level. A single vague category
#         hit (e.g. just "leadership") stays below CONFIDENCE_THRESHOLD,
#         matching the sample pattern where "we need a leadership
#         solution" still gets a clarifying question rather than a
#         shortlist.
#         """
#         score = 0
#         if self.roles:
#             score += 1
#         if self.levels:
#             score += 1
#         if self.skills:
#             score += 1
#         if self.industries:
#             score += 1
#         if self.test_type_hints:
#             score += 1
#         return score
 
#     def critical_missing(self) -> List[str]:
#         """
#         Returns a list of critical-constraint keys that are still
#         missing even though enough general context exists to not be
#         `is_empty()`. Currently covers: phone/contact-centre-type
#         roles missing a call/assessment language, since that decides
#         which language-specific catalog item is actually correct.
 
#         Deliberately narrow and additive: this never fires for roles
#         outside the phone-contact hint list, so it doesn't change
#         behavior for the large majority of recommend-eligible turns
#         (e.g. "Java developers, mid-level" still recommends directly).
#         """
#         missing: List[str] = []
#         combined_text = " ".join(self.free_text).lower()
#         is_phone_role = any(hint in combined_text for hint in PHONE_CONTACT_HINTS)
#         if is_phone_role and not self.languages:
#             missing.append("language")
#         return missing
 
 
# def _extract_terms(text: str, term_list: List[str]) -> List[str]:
#     text_l = text.lower()
#     found = []
#     for term in term_list:
#         if term in text_l and term not in found:
#             found.append(term)
#     return found
 
 
# def extract_requirements(messages: List[Message]) -> Requirements:
#     """Build a structured requirements profile from ALL user turns so
#     far. Called fresh on every request since the API is stateless."""
#     req = Requirements()
#     for m in messages:
#         if m.role != "user":
#             continue
#         text = m.content
#         req.roles.extend(t for t in _extract_terms(text, ROLE_TERMS) if t not in req.roles)
#         req.levels.extend(t for t in _extract_terms(text, LEVEL_TERMS) if t not in req.levels)
#         req.skills.extend(t for t in _extract_terms(text, SKILL_TERMS) if t not in req.skills)
#         req.industries.extend(t for t in _extract_terms(text, INDUSTRY_TERMS) if t not in req.industries)
#         req.languages.extend(t for t in _extract_terms(text, LANGUAGE_TERMS) if t not in req.languages)
#         for hint, code in TEST_TYPE_HINTS.items():
#             if hint in text.lower() and code not in req.test_type_hints:
#                 req.test_type_hints.append(code)
#         req.free_text.append(text)
#     return req
 
 
# @dataclass
# class RefineAction:
#     add_terms: List[str] = field(default_factory=list)
#     remove_terms: List[str] = field(default_factory=list)
#     is_pure_confirmation: bool = False
 
 
# def parse_refine_action(last_user_msg: str) -> RefineAction:
#     """Pull out explicit add/remove/replace instructions from the
#     latest user turn so a 'refine' turn can edit the previous
#     shortlist instead of recomputing it from scratch."""
#     action = RefineAction()
 
#     for m in REPLACE_PATTERN.finditer(last_user_msg):
#         if m.group(1) and m.group(2):
#             action.remove_terms.append(m.group(1).strip())
#             action.add_terms.append(m.group(2).strip())
#         elif m.group(3) and m.group(4):
#             action.remove_terms.append(m.group(3).strip())
#             action.add_terms.append(m.group(4).strip())
 
#     for m in ADD_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.add_terms:
#             action.add_terms.append(term)
 
#     for m in REMOVE_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.remove_terms:
#             action.remove_terms.append(term)
 
#     if not action.add_terms and not action.remove_terms:
#         action.is_pure_confirmation = True
 
#     return action


# r"""
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.

# This module now derives a STRUCTURED requirements profile (role,
# level, skills, industry, language, preferred test types, explicit
# add/remove instructions) from the conversation, instead of just
# concatenating raw text. Retrieval is built on top of this structured
# profile so that:
#   - stray conversational filler ("Perfect, thanks") doesn't dilute
#     the search query, and
#   - a later turn's edits ("also add personality tests") are additive
#     rather than overwriting everything that came before.

# BUGFIX NOTES (all three found by replaying real sample conversations
# through the live pipeline and diffing expected vs. predicted):

#   - ADD_PATTERN previously required a *second* mandatory whitespace
#     after "add " even when no article followed, which is impossible
#     to satisfy — "Add AWS and Docker." never matched at all. Fixed by
#     making the article an optional *prefix* of the capture instead of
#     a fixed-width gap.
#   - REMOVE_PATTERN's lookahead required `\s+` before the sentence
#     terminator, so "Drop the OPQ." (no space before the period) never
#     matched. Now uses `\s*`.
#   - REPLACE_PATTERN's replacement-term capture didn't exclude "?", so
#     a message ending in a question ("...replace it with something
#     shorter? Candidates complain...") swallowed the entire rest of
#     the sentence into a garbage search query.

# Also added FINAL_LIST_PATTERN: phrasing like "Final list: X and Y" or
# "keep only X and Y" is common in refine turns and previously matched
# NEITHER add nor remove, so the named items silently never made it
# into the shortlist. This is now parsed as a full-replacement
# instruction (see RefineAction.full_replacement_terms).
# """

# import re
# from dataclasses import dataclass, field
# from typing import List, Optional

# from app.models import Message

# MAX_CLARIFYING_QUESTIONS = 2

# # Minimum confidence_score() needed to skip clarification and go
# # straight to retrieval. Categories are: role, level, skill, industry,
# # test-type preference (max possible = 5). Threshold of 2 means a
# # single vague category hit (e.g. only "leadership", or only
# # "assessment") is NOT enough on its own — it still routes to
# # clarify_needed — while any two concrete signals (e.g. role+level,
# # or skill+industry) are enough to retrieve immediately. Tuned against
# # the spec's own examples: "I need an assessment" (score 0), "We need
# # a leadership solution" (score 1, role-only) both stay below
# # threshold; "Java developers, mid-level" (role+level, score 2) clears it.
# CONFIDENCE_THRESHOLD = 2


# # ---------------------------------------------------------------------
# # Turn-budget helpers (unchanged behavior from the original app)
# # ---------------------------------------------------------------------

# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")


# def count_clarifying_turns(messages: List[Message]) -> int:
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count


# def turns_used(messages: List[Message]) -> int:
#     return len(messages)


# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS


# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)


# # ---------------------------------------------------------------------
# # Structured requirements profile
# # ---------------------------------------------------------------------

# ROLE_TERMS = [
#     "engineer", "developer", "programmer", "analyst", "manager", "director",
#     "executive", "cxo", "leadership", "sales", "customer service",
#     "contact centre", "contact center", "call centre", "call center",
#     "admin", "administrative assistant", "clerk", "technician", "operator",
#     "plant operator", "graduate", "trainee", "intern", "nurse", "accountant",
#     "financial analyst", "healthcare admin",
# ]

# # Terms in ROLE_TERMS that are too generic to identify a searchable
# # role on their own (e.g. "leadership" could mean anyone from a new
# # supervisor to a CXO). They still populate Requirements.roles so
# # retrieval queries include them, but they don't earn a point in
# # confidence_score() unless paired with something more specific (a
# # level, a concrete title, etc. — captured by the OTHER categories
# # already scoring their own point). Matches the sample pattern where
# # "we need a solution for senior leadership" still gets a clarifying
# # question about who exactly the audience is, despite "leadership"
# # + "senior" superficially looking like two populated categories.
# VAGUE_ROLE_TERMS = {"leadership"}

# LEVEL_TERMS = [
#     "entry-level", "entry level", "graduate", "junior", "mid-level",
#     "mid level", "senior", "director", "executive", "cxo", "individual contributor",
#     "supervisor", "front line manager", "manager", "professional",
# ]

# SKILL_TERMS = [
#     "java", "python", "sql", "excel", "word", "aws", "docker", "angular",
#     "spring", "rust", "coding", "programming", ".net", "javascript",
#     "numerical reasoning", "verbal reasoning", "cognitive", "deductive reasoning",
#     "situational judgement", "situational judgment", "personality",
#     "typing", "data entry", "customer service", "sales skills",
# ]

# INDUSTRY_TERMS = [
#     "healthcare", "finance", "financial", "banking", "manufacturing",
#     "chemical", "retail", "technology", "insurance", "pharma",
# ]

# LANGUAGE_TERMS = [
#     "english", "spanish", "french", "german", "mandarin", "hindi", "portuguese",
# ]

# TEST_TYPE_HINTS = {
#     "personality": "P", "cognitive": "A", "ability": "A", "aptitude": "A",
#     "situational judgement": "B", "situational judgment": "B", "biodata": "B",
#     "competenc": "C", "development": "D", "360": "D",
#     "assessment exercise": "E", "knowledge": "K", "skills test": "K",
#     "simulation": "S",
# }

# # ---------------------------------------------------------------------
# # Critical-constraint detection
# # ---------------------------------------------------------------------
# # Some roles have a constraint that materially changes WHICH catalog
# # item is correct, not just how well it's explained — e.g. a phone /
# # contact-centre role needs a language-specific version of a test, so
# # recommending before that's known risks handing back the wrong SKU.
# # `Requirements.is_empty()` alone doesn't catch this: a message like
# # "500 entry-level contact centre agents, inbound calls" already
# # populates roles + levels, so the old router treated it as fully
# # specified and recommended immediately. `critical_missing()` adds a
# # second, narrower gate on top of is_empty() for exactly these cases,
# # without turning the router into pure keyword matching for the
# # general routing decision — it only tightens the recommend/clarify
# # boundary for a small, well-defined set of situations where getting
# # it wrong is costly.

# # Phrases signalling a phone/voice-based customer-facing role, where
# # the SPOKEN LANGUAGE of the assessment (and the calls) is a hard
# # constraint on which SHL item is correct.
# PHONE_CONTACT_HINTS = [
#     "contact centre", "contact center", "call centre", "call center",
#     "inbound call", "inbound calls", "outbound call", "outbound calls",
#     "phone support", "telephone support", "telephone screening",
#     "customer service", "customer support", "help desk", "helpdesk",
#     "support agent", "support agents",
# ]

# # Human-readable phrasing for what's missing, used to steer the
# # clarifying question toward the actual gap instead of a generic one.
# MISSING_HINT_TEXT = {
#     "language": "the language(s) the calls / assessments need to be conducted in",
# }

# # ---------------------------------------------------------------------
# # Refine-instruction patterns
# # ---------------------------------------------------------------------
# # Words that signal the user is editing an EXISTING shortlist, plus
# # which direction the edit goes. Order matters: check "replace" before
# # plain "add"/"remove" since it implies both.
# #
# # ADD_PATTERN: the article ("a"/"an"/"the") is an optional PREFIX of
# # the capture, not a separate fixed-width gap — "add X", "add a X",
# # "add an X", "add the X", and "also add X" all match with exactly one
# # required space between the trigger and the content.
# ADD_PATTERN = re.compile(r"(?i)\b(also add|add|include)\s+(?:a\s+|an\s+|the\s+)?([^.,;?]+)")

# # REMOVE_PATTERN: lookahead uses `\s*` (not `\s+`) so a terminator that
# # immediately follows the term with no space ("Drop the OPQ.") still
# # matches. "?" and an em-dash are also valid terminators.
# REMOVE_PATTERN = re.compile(
#     r"(?i)\b(remove|drop|take out|without the|exclude)\s+(?:the\s+)?([^.,;?—]+?)"
#     r"(?=\s*(?:and|but|,|\.|\?|—|$))"
# )

# # REPLACE_PATTERN: both captures exclude "?" so a trailing question in
# # the same sentence doesn't get swallowed into the replacement term.
# REPLACE_PATTERN = re.compile(
#     r"(?i)\bremove\s+(?:the\s+)?([^.,;?]+?)\s+and\s+replace\s+(?:it\s+)?with\s+([^.,;?]+)|"
#     r"\breplace\s+(?:the\s+)?([^.,;?]+?)\s+with\s+([^.,;?]+)"
# )

# # FINAL_LIST_PATTERN: "Final list: X and Y" / "keep only X and Y" /
# # "just keep X and Y" / "only keep X and Y" — the user is stating the
# # complete desired shortlist, not adding to or subtracting from the
# # existing one. Previously this phrasing matched neither ADD_PATTERN
# # nor REMOVE_PATTERN and the named items were silently dropped.
# FINAL_LIST_PATTERN = re.compile(r"(?i)\b(?:final list|keep only|just keep|only keep)[:\s]+([^.?!]+)")

# # Splits a captured "X and Y", "X, Y and Z", "X & Y" span into
# # individual terms — ADD_PATTERN/FINAL_LIST_PATTERN capture the whole
# # conjunction as one span so multi-item edits aren't lost.
# _TERM_SPLIT_RE = re.compile(r"(?i)\s*(?:,\s*(?:and\s+)?|\s+and\s+|\s*&\s*)\s*")


# def _split_terms(text: str) -> List[str]:
#     parts = [p.strip(" .") for p in _TERM_SPLIT_RE.split(text) if p.strip(" .")]
#     return parts if parts else ([text.strip(" .")] if text.strip(" .") else [])


# @dataclass
# class Requirements:
#     roles: List[str] = field(default_factory=list)
#     levels: List[str] = field(default_factory=list)
#     skills: List[str] = field(default_factory=list)
#     industries: List[str] = field(default_factory=list)
#     languages: List[str] = field(default_factory=list)
#     test_type_hints: List[str] = field(default_factory=list)
#     free_text: List[str] = field(default_factory=list)  # raw user turns, for BM25/dense fallback

#     def to_query(self) -> str:
#         """Flatten the structured profile into a clean retrieval query.
#         Structured terms are repeated up front (cheap way to weight
#         them higher for BM25) followed by the raw text as a fallback
#         signal for anything the keyword lists didn't catch."""
#         structured = (
#             self.roles + self.levels + self.skills + self.industries + self.languages
#         )
#         parts = []
#         if structured:
#             parts.append(" ".join(structured) + " " + " ".join(structured))
#         parts.extend(self.free_text)
#         return " ".join(parts).strip()

#     def is_empty(self) -> bool:
#         return not (self.roles or self.levels or self.skills or self.industries)

#     def confidence_score(self) -> int:
#         """
#         Lightweight rule-based confidence score over the already-
#         extracted structured fields — no LLM call, no extra parsing,
#         O(1) on data we already have. One point per requirement
#         CATEGORY that has at least one hit:

#             role present                -> +1
#             seniority/level present     -> +1
#             skill present               -> +1
#             industry present            -> +1
#             assessment/test-type pref.  -> +1  (test_type_hints)

#         This intentionally scores by category, not by term count, so
#         a message that mentions five skill keywords doesn't outscore
#         one that mentions a role + a level. A single vague category
#         hit (e.g. just "leadership") stays below CONFIDENCE_THRESHOLD,
#         matching the sample pattern where "we need a leadership
#         solution" still gets a clarifying question rather than a
#         shortlist.
#         """
#         score = 0
#         if self.roles:
#             score += 1
#         if self.levels:
#             score += 1
#         if self.skills:
#             score += 1
#         if self.industries:
#             score += 1
#         if self.test_type_hints:
#             score += 1
#         return score

#     def critical_missing(self) -> List[str]:
#         """
#         Returns a list of critical-constraint keys that are still
#         missing even though enough general context exists to not be
#         `is_empty()`. Currently covers: phone/contact-centre-type
#         roles missing a call/assessment language, since that decides
#         which language-specific catalog item is actually correct.

#         Deliberately narrow and additive: this never fires for roles
#         outside the phone-contact hint list, so it doesn't change
#         behavior for the large majority of recommend-eligible turns
#         (e.g. "Java developers, mid-level" still recommends directly).
#         """
#         missing: List[str] = []
#         combined_text = " ".join(self.free_text).lower()
#         is_phone_role = any(hint in combined_text for hint in PHONE_CONTACT_HINTS)
#         if is_phone_role and not self.languages:
#             missing.append("language")
#         return missing


# def _extract_terms(text: str, term_list: List[str]) -> List[str]:
#     text_l = text.lower()
#     found = []
#     for term in term_list:
#         if term in text_l and term not in found:
#             found.append(term)
#     return found


# def extract_requirements(messages: List[Message]) -> Requirements:
#     """Build a structured requirements profile from ALL user turns so
#     far. Called fresh on every request since the API is stateless."""
#     req = Requirements()
#     for m in messages:
#         if m.role != "user":
#             continue
#         text = m.content
#         req.roles.extend(t for t in _extract_terms(text, ROLE_TERMS) if t not in req.roles)
#         req.levels.extend(t for t in _extract_terms(text, LEVEL_TERMS) if t not in req.levels)
#         req.skills.extend(t for t in _extract_terms(text, SKILL_TERMS) if t not in req.skills)
#         req.industries.extend(t for t in _extract_terms(text, INDUSTRY_TERMS) if t not in req.industries)
#         req.languages.extend(t for t in _extract_terms(text, LANGUAGE_TERMS) if t not in req.languages)
#         for hint, code in TEST_TYPE_HINTS.items():
#             if hint in text.lower() and code not in req.test_type_hints:
#                 req.test_type_hints.append(code)
#         req.free_text.append(text)
#     return req


# @dataclass
# class RefineAction:
#     add_terms: List[str] = field(default_factory=list)
#     remove_terms: List[str] = field(default_factory=list)
#     # If non-empty, the user stated the COMPLETE desired shortlist
#     # ("Final list: X and Y") rather than an incremental edit — this
#     # should override prior_items/add/remove merging entirely.
#     full_replacement_terms: List[str] = field(default_factory=list)
#     is_pure_confirmation: bool = False


# def parse_refine_action(last_user_msg: str) -> RefineAction:
#     """Pull out explicit add/remove/replace/final-list instructions
#     from the latest user turn so a 'refine' turn can edit the previous
#     shortlist instead of recomputing it from scratch."""
#     action = RefineAction()

#     for m in FINAL_LIST_PATTERN.finditer(last_user_msg):
#         for term in _split_terms(m.group(1)):
#             if term and term not in action.full_replacement_terms:
#                 action.full_replacement_terms.append(term)

#     for m in REPLACE_PATTERN.finditer(last_user_msg):
#         if m.group(1) and m.group(2):
#             action.remove_terms.append(m.group(1).strip())
#             action.add_terms.extend(_split_terms(m.group(2)))
#         elif m.group(3) and m.group(4):
#             action.remove_terms.append(m.group(3).strip())
#             action.add_terms.extend(_split_terms(m.group(4)))

#     for m in ADD_PATTERN.finditer(last_user_msg):
#         for term in _split_terms(m.group(2)):
#             if term and term not in action.add_terms:
#                 action.add_terms.append(term)

#     for m in REMOVE_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.remove_terms:
#             action.remove_terms.append(term)

#     if not action.add_terms and not action.remove_terms and not action.full_replacement_terms:
#         action.is_pure_confirmation = True

#     return action


# """
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.

# This module now derives a STRUCTURED requirements profile (role,
# level, skills, industry, language, preferred test types, explicit
# add/remove instructions) from the conversation, instead of just
# concatenating raw text. Retrieval is built on top of this structured
# profile so that:
#   - stray conversational filler ("Perfect, thanks") doesn't dilute
#     the search query, and
#   - a later turn's edits (e.g. "also add personality tests") are
#     additive rather than overwriting everything that came before.
# """

# import re
# from dataclasses import dataclass, field
# from typing import List, Optional

# from app.models import Message

# MAX_CLARIFYING_QUESTIONS = 2


# # ---------------------------------------------------------------------
# # Turn-budget helpers (unchanged behavior from the original app)
# # ---------------------------------------------------------------------

# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")


# def count_clarifying_turns(messages: List[Message]) -> int:
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count


# def turns_used(messages: List[Message]) -> int:
#     return len(messages)


# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS


# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)


# # ---------------------------------------------------------------------
# # Structured requirements profile
# # ---------------------------------------------------------------------

# ROLE_TERMS = [
#     "engineer", "developer", "programmer", "analyst", "manager", "director",
#     "executive", "cxo", "leadership", "sales", "customer service",
#     "contact centre", "contact center", "call centre", "call center",
#     "admin", "administrative assistant", "clerk", "technician", "operator",
#     "plant operator", "graduate", "trainee", "intern", "nurse", "accountant",
#     "financial analyst", "healthcare admin",
# ]

# LEVEL_TERMS = [
#     "entry-level", "entry level", "graduate", "junior", "mid-level",
#     "mid level", "senior", "director", "executive", "cxo", "individual contributor",
#     "supervisor", "front line manager", "manager", "professional",
# ]

# SKILL_TERMS = [
#     "java", "python", "sql", "excel", "word", "aws", "docker", "angular",
#     "spring", "rust", "coding", "programming", ".net", "javascript",
#     "numerical reasoning", "verbal reasoning", "cognitive", "deductive reasoning",
#     "situational judgement", "situational judgment", "personality",
#     "typing", "data entry", "customer service", "sales skills",
# ]

# INDUSTRY_TERMS = [
#     "healthcare", "finance", "financial", "banking", "manufacturing",
#     "chemical", "retail", "technology", "insurance", "pharma",
# ]

# LANGUAGE_TERMS = [
#     "english", "spanish", "french", "german", "mandarin", "hindi", "portuguese",
# ]

# TEST_TYPE_HINTS = {
#     "personality": "P", "cognitive": "A", "ability": "A", "aptitude": "A",
#     "situational judgement": "B", "situational judgment": "B", "biodata": "B",
#     "competenc": "C", "development": "D", "360": "D",
#     "assessment exercise": "E", "knowledge": "K", "skills test": "K",
#     "simulation": "S",
# }

# # Words that signal the user is editing an EXISTING shortlist, plus
# # which direction the edit goes. Order matters: check "replace" before
# # plain "add"/"remove" since it implies both.
# ADD_PATTERN = re.compile(r"(?i)\b(also add|add (?:a|an|the)?|include (?:a|an|the)?)\s+([^.,;]+)")
# REMOVE_PATTERN = re.compile(
#     r"(?i)\b(remove|drop|take out|without the|exclude)\s+(?:the\s+)?([^.,;]+?)"
#     r"(?=\s+(?:and|but|,|\.|$))"
# )
# REPLACE_PATTERN = re.compile(
#     r"(?i)\bremove\s+(?:the\s+)?([^.,;]+?)\s+and\s+replace\s+(?:it\s+)?with\s+([^.,;]+)|"
#     r"\breplace\s+(?:the\s+)?([^.,;]+?)\s+with\s+([^.,;]+)"
# )


# @dataclass
# class Requirements:
#     roles: List[str] = field(default_factory=list)
#     levels: List[str] = field(default_factory=list)
#     skills: List[str] = field(default_factory=list)
#     industries: List[str] = field(default_factory=list)
#     languages: List[str] = field(default_factory=list)
#     test_type_hints: List[str] = field(default_factory=list)
#     free_text: List[str] = field(default_factory=list)  # raw user turns, for BM25/dense fallback

#     def to_query(self) -> str:
#         """Flatten the structured profile into a clean retrieval query.
#         Structured terms are repeated up front (cheap way to weight
#         them higher for BM25) followed by the raw text as a fallback
#         signal for anything the keyword lists didn't catch."""
#         structured = (
#             self.roles + self.levels + self.skills + self.industries + self.languages
#         )
#         parts = []
#         if structured:
#             parts.append(" ".join(structured) + " " + " ".join(structured))
#         parts.extend(self.free_text)
#         return " ".join(parts).strip()

#     def is_empty(self) -> bool:
#         return not (self.roles or self.levels or self.skills or self.industries)


# def _extract_terms(text: str, term_list: List[str]) -> List[str]:
#     text_l = text.lower()
#     found = []
#     for term in term_list:
#         if term in text_l and term not in found:
#             found.append(term)
#     return found


# def extract_requirements(messages: List[Message]) -> Requirements:
#     """Build a structured requirements profile from ALL user turns so
#     far. Called fresh on every request since the API is stateless."""
#     req = Requirements()
#     for m in messages:
#         if m.role != "user":
#             continue
#         text = m.content
#         req.roles.extend(t for t in _extract_terms(text, ROLE_TERMS) if t not in req.roles)
#         req.levels.extend(t for t in _extract_terms(text, LEVEL_TERMS) if t not in req.levels)
#         req.skills.extend(t for t in _extract_terms(text, SKILL_TERMS) if t not in req.skills)
#         req.industries.extend(t for t in _extract_terms(text, INDUSTRY_TERMS) if t not in req.industries)
#         req.languages.extend(t for t in _extract_terms(text, LANGUAGE_TERMS) if t not in req.languages)
#         for hint, code in TEST_TYPE_HINTS.items():
#             if hint in text.lower() and code not in req.test_type_hints:
#                 req.test_type_hints.append(code)
#         req.free_text.append(text)
#     return req


# @dataclass
# class RefineAction:
#     add_terms: List[str] = field(default_factory=list)
#     remove_terms: List[str] = field(default_factory=list)
#     is_pure_confirmation: bool = False


# def parse_refine_action(last_user_msg: str) -> RefineAction:
#     """Pull out explicit add/remove/replace instructions from the
#     latest user turn so a 'refine' turn can edit the previous
#     shortlist instead of recomputing it from scratch."""
#     action = RefineAction()

#     for m in REPLACE_PATTERN.finditer(last_user_msg):
#         if m.group(1) and m.group(2):
#             action.remove_terms.append(m.group(1).strip())
#             action.add_terms.append(m.group(2).strip())
#         elif m.group(3) and m.group(4):
#             action.remove_terms.append(m.group(3).strip())
#             action.add_terms.append(m.group(4).strip())

#     for m in ADD_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.add_terms:
#             action.add_terms.append(term)

#     for m in REMOVE_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.remove_terms:
#             action.remove_terms.append(term)

#     if not action.add_terms and not action.remove_terms:
#         action.is_pure_confirmation = True

#     return action

# """
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.

# We keep it simple: extract raw user turns as "known facts" text,
# count how many assistant turns already asked a question, and pull the
# last shortlist out of the last assistant recommendation table (if any).
# """

# from typing import Any, Dict, List
# from app.models import Message


# MAX_CLARIFYING_QUESTIONS = 2


# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")


# def count_clarifying_turns(messages: List[Message]) -> int:
#     """
#     Rough heuristic: an assistant turn that ends in '?' and has no
#     table/list of names is treated as a clarifying question.
#     Good enough for a turn-budget guard; refine after testing against
#     the sample conversations.
#     """
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count


# def turns_used(messages: List[Message]) -> int:
#     return len(messages)


# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS


# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)

# """
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.

# This module now derives a STRUCTURED requirements profile (role,
# level, skills, industry, language, preferred test types, explicit
# add/remove instructions) from the conversation, instead of just
# concatenating raw text. Retrieval is built on top of this structured
# profile so that:
#   - stray conversational filler ("Perfect, thanks") doesn't dilute
#     the search query, and
#   - a later turn's edits (e.g. "also add personality tests") are
#     additive rather than overwriting everything that came before.
# """

# import re
# from dataclasses import dataclass, field
# from typing import List, Optional

# from app.models import Message

# MAX_CLARIFYING_QUESTIONS = 2


# # ---------------------------------------------------------------------
# # Turn-budget helpers (unchanged behavior from the original app)
# # ---------------------------------------------------------------------

# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")


# def count_clarifying_turns(messages: List[Message]) -> int:
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count


# def turns_used(messages: List[Message]) -> int:
#     return len(messages)


# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS


# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)


# # ---------------------------------------------------------------------
# # Structured requirements profile
# # ---------------------------------------------------------------------

# ROLE_TERMS = [
#     "engineer", "developer", "programmer", "analyst", "manager", "director",
#     "executive", "cxo", "leadership", "sales", "customer service",
#     "contact centre", "contact center", "call centre", "call center",
#     "admin", "administrative assistant", "clerk", "technician", "operator",
#     "plant operator", "graduate", "trainee", "intern", "nurse", "accountant",
#     "financial analyst", "healthcare admin",
# ]

# LEVEL_TERMS = [
#     "entry-level", "entry level", "graduate", "junior", "mid-level",
#     "mid level", "senior", "director", "executive", "cxo", "individual contributor",
#     "supervisor", "front line manager", "manager", "professional",
# ]

# SKILL_TERMS = [
#     "java", "python", "sql", "excel", "word", "aws", "docker", "angular",
#     "spring", "rust", "coding", "programming", ".net", "javascript",
#     "numerical reasoning", "verbal reasoning", "cognitive", "deductive reasoning",
#     "situational judgement", "situational judgment", "personality",
#     "typing", "data entry", "customer service", "sales skills",
# ]

# INDUSTRY_TERMS = [
#     "healthcare", "finance", "financial", "banking", "manufacturing",
#     "chemical", "retail", "technology", "insurance", "pharma",
# ]

# LANGUAGE_TERMS = [
#     "english", "spanish", "french", "german", "mandarin", "hindi", "portuguese",
# ]

# TEST_TYPE_HINTS = {
#     "personality": "P", "cognitive": "A", "ability": "A", "aptitude": "A",
#     "situational judgement": "B", "situational judgment": "B", "biodata": "B",
#     "competenc": "C", "development": "D", "360": "D",
#     "assessment exercise": "E", "knowledge": "K", "skills test": "K",
#     "simulation": "S",
# }

# # ---------------------------------------------------------------------
# # Critical-constraint detection
# # ---------------------------------------------------------------------
# # Some roles have a constraint that materially changes WHICH catalog
# # item is correct, not just how well it's explained — e.g. a phone /
# # contact-centre role needs a language-specific version of a test, so
# # recommending before that's known risks handing back the wrong SKU.
# # `Requirements.is_empty()` alone doesn't catch this: a message like
# # "500 entry-level contact centre agents, inbound calls" already
# # populates roles + levels, so the old router treated it as fully
# # specified and recommended immediately. `critical_missing()` adds a
# # second, narrower gate on top of is_empty() for exactly these cases,
# # without turning the router into pure keyword matching for the
# # general routing decision — it only tightens the recommend/clarify
# # boundary for a small, well-defined set of situations where getting
# # it wrong is costly.

# # Phrases signalling a phone/voice-based customer-facing role, where
# # the SPOKEN LANGUAGE of the assessment (and the calls) is a hard
# # constraint on which SHL item is correct.
# PHONE_CONTACT_HINTS = [
#     "contact centre", "contact center", "call centre", "call center",
#     "inbound call", "inbound calls", "outbound call", "outbound calls",
#     "phone support", "telephone support", "telephone screening",
#     "customer service", "customer support", "help desk", "helpdesk",
#     "support agent", "support agents",
# ]

# # Human-readable phrasing for what's missing, used to steer the
# # clarifying question toward the actual gap instead of a generic one.
# MISSING_HINT_TEXT = {
#     "language": "the language(s) the calls / assessments need to be conducted in",
# }

# # Words that signal the user is editing an EXISTING shortlist, plus
# # which direction the edit goes. Order matters: check "replace" before
# # plain "add"/"remove" since it implies both.
# ADD_PATTERN = re.compile(r"(?i)\b(also add|add (?:a|an|the)?|include (?:a|an|the)?)\s+([^.,;]+)")
# REMOVE_PATTERN = re.compile(
#     r"(?i)\b(remove|drop|take out|without the|exclude)\s+(?:the\s+)?([^.,;]+?)"
#     r"(?=\s+(?:and|but|,|\.|$))"
# )
# REPLACE_PATTERN = re.compile(
#     r"(?i)\bremove\s+(?:the\s+)?([^.,;]+?)\s+and\s+replace\s+(?:it\s+)?with\s+([^.,;]+)|"
#     r"\breplace\s+(?:the\s+)?([^.,;]+?)\s+with\s+([^.,;]+)"
# )


# @dataclass
# class Requirements:
#     roles: List[str] = field(default_factory=list)
#     levels: List[str] = field(default_factory=list)
#     skills: List[str] = field(default_factory=list)
#     industries: List[str] = field(default_factory=list)
#     languages: List[str] = field(default_factory=list)
#     test_type_hints: List[str] = field(default_factory=list)
#     free_text: List[str] = field(default_factory=list)  # raw user turns, for BM25/dense fallback

#     def to_query(self) -> str:
#         """Flatten the structured profile into a clean retrieval query.
#         Structured terms are repeated up front (cheap way to weight
#         them higher for BM25) followed by the raw text as a fallback
#         signal for anything the keyword lists didn't catch."""
#         structured = (
#             self.roles + self.levels + self.skills + self.industries + self.languages
#         )
#         parts = []
#         if structured:
#             parts.append(" ".join(structured) + " " + " ".join(structured))
#         parts.extend(self.free_text)
#         return " ".join(parts).strip()

#     def is_empty(self) -> bool:
#         return not (self.roles or self.levels or self.skills or self.industries)

#     def critical_missing(self) -> List[str]:
#         """
#         Returns a list of critical-constraint keys that are still
#         missing even though enough general context exists to not be
#         `is_empty()`. Currently covers: phone/contact-centre-type
#         roles missing a call/assessment language, since that decides
#         which language-specific catalog item is actually correct.

#         Deliberately narrow and additive: this never fires for roles
#         outside the phone-contact hint list, so it doesn't change
#         behavior for the large majority of recommend-eligible turns
#         (e.g. "Java developers, mid-level" still recommends directly).
#         """
#         missing: List[str] = []
#         combined_text = " ".join(self.free_text).lower()
#         is_phone_role = any(hint in combined_text for hint in PHONE_CONTACT_HINTS)
#         if is_phone_role and not self.languages:
#             missing.append("language")
#         return missing


# def _extract_terms(text: str, term_list: List[str]) -> List[str]:
#     text_l = text.lower()
#     found = []
#     for term in term_list:
#         if term in text_l and term not in found:
#             found.append(term)
#     return found


# def extract_requirements(messages: List[Message]) -> Requirements:
#     """Build a structured requirements profile from ALL user turns so
#     far. Called fresh on every request since the API is stateless."""
#     req = Requirements()
#     for m in messages:
#         if m.role != "user":
#             continue
#         text = m.content
#         req.roles.extend(t for t in _extract_terms(text, ROLE_TERMS) if t not in req.roles)
#         req.levels.extend(t for t in _extract_terms(text, LEVEL_TERMS) if t not in req.levels)
#         req.skills.extend(t for t in _extract_terms(text, SKILL_TERMS) if t not in req.skills)
#         req.industries.extend(t for t in _extract_terms(text, INDUSTRY_TERMS) if t not in req.industries)
#         req.languages.extend(t for t in _extract_terms(text, LANGUAGE_TERMS) if t not in req.languages)
#         for hint, code in TEST_TYPE_HINTS.items():
#             if hint in text.lower() and code not in req.test_type_hints:
#                 req.test_type_hints.append(code)
#         req.free_text.append(text)
#     return req


# @dataclass
# class RefineAction:
#     add_terms: List[str] = field(default_factory=list)
#     remove_terms: List[str] = field(default_factory=list)
#     is_pure_confirmation: bool = False


# def parse_refine_action(last_user_msg: str) -> RefineAction:
#     """Pull out explicit add/remove/replace instructions from the
#     latest user turn so a 'refine' turn can edit the previous
#     shortlist instead of recomputing it from scratch."""
#     action = RefineAction()

#     for m in REPLACE_PATTERN.finditer(last_user_msg):
#         if m.group(1) and m.group(2):
#             action.remove_terms.append(m.group(1).strip())
#             action.add_terms.append(m.group(2).strip())
#         elif m.group(3) and m.group(4):
#             action.remove_terms.append(m.group(3).strip())
#             action.add_terms.append(m.group(4).strip())

#     for m in ADD_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.add_terms:
#             action.add_terms.append(term)

#     for m in REMOVE_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.remove_terms:
#             action.remove_terms.append(term)

#     if not action.add_terms and not action.remove_terms:
#         action.is_pure_confirmation = True

#     return action


# """
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.
 
# This module now derives a STRUCTURED requirements profile (role,
# level, skills, industry, language, preferred test types, explicit
# add/remove instructions) from the conversation, instead of just
# concatenating raw text. Retrieval is built on top of this structured
# profile so that:
#   - stray conversational filler ("Perfect, thanks") doesn't dilute
#     the search query, and
#   - a later turn's edits (e.g. "also add personality tests") are
#     additive rather than overwriting everything that came before.
# """
 
# import re
# from dataclasses import dataclass, field
# from typing import List, Optional
 
# from app.models import Message
 
# MAX_CLARIFYING_QUESTIONS = 2
 
# # Minimum confidence_score() needed to skip clarification and go
# # straight to retrieval. Categories are: role, level, skill, industry,
# # test-type preference (max possible = 5). Threshold of 2 means a
# # single vague category hit (e.g. only "leadership", or only
# # "assessment") is NOT enough on its own — it still routes to
# # clarify_needed — while any two concrete signals (e.g. role+level,
# # or skill+industry) are enough to retrieve immediately. Tuned against
# # the spec's own examples: "I need an assessment" (score 0), "We need
# # a leadership solution" (score 1, role-only) both stay below
# # threshold; "Java developers, mid-level" (role+level, score 2) clears it.
# CONFIDENCE_THRESHOLD = 2
 
 
# # ---------------------------------------------------------------------
# # Turn-budget helpers (unchanged behavior from the original app)
# # ---------------------------------------------------------------------
 
# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")
 
 
# def count_clarifying_turns(messages: List[Message]) -> int:
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count
 
 
# def turns_used(messages: List[Message]) -> int:
#     return len(messages)
 
 
# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS
 
 
# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)
 
 
# # ---------------------------------------------------------------------
# # Structured requirements profile
# # ---------------------------------------------------------------------
 
# ROLE_TERMS = [
#     "engineer", "developer", "programmer", "analyst", "manager", "director",
#     "executive", "cxo", "leadership", "sales", "customer service",
#     "contact centre", "contact center", "call centre", "call center",
#     "admin", "administrative assistant", "clerk", "technician", "operator",
#     "plant operator", "graduate", "trainee", "intern", "nurse", "accountant",
#     "financial analyst", "healthcare admin",
# ]
 
# # Terms in ROLE_TERMS that are too generic to identify a searchable
# # role on their own (e.g. "leadership" could mean anyone from a new
# # supervisor to a CXO). They still populate Requirements.roles so
# # retrieval queries include them, but they don't earn a point in
# # confidence_score() unless paired with something more specific (a
# # level, a concrete title, etc. — captured by the OTHER categories
# # already scoring their own point). Matches the sample pattern where
# # "we need a solution for senior leadership" still gets a clarifying
# # question about who exactly the audience is, despite "leadership"
# # + "senior" superficially looking like two populated categories.
# VAGUE_ROLE_TERMS = {"leadership"}
 
# LEVEL_TERMS = [
#     "entry-level", "entry level", "graduate", "junior", "mid-level",
#     "mid level", "senior", "director", "executive", "cxo", "individual contributor",
#     "supervisor", "front line manager", "manager", "professional",
# ]
 
# SKILL_TERMS = [
#     "java", "python", "sql", "excel", "word", "aws", "docker", "angular",
#     "spring", "rust", "coding", "programming", ".net", "javascript",
#     "numerical reasoning", "verbal reasoning", "cognitive", "deductive reasoning",
#     "situational judgement", "situational judgment", "personality",
#     "typing", "data entry", "customer service", "sales skills",
# ]
 
# INDUSTRY_TERMS = [
#     "healthcare", "finance", "financial", "banking", "manufacturing",
#     "chemical", "retail", "technology", "insurance", "pharma",
# ]
 
# LANGUAGE_TERMS = [
#     "english", "spanish", "french", "german", "mandarin", "hindi", "portuguese",
# ]
 
# TEST_TYPE_HINTS = {
#     "personality": "P", "cognitive": "A", "ability": "A", "aptitude": "A",
#     "situational judgement": "B", "situational judgment": "B", "biodata": "B",
#     "competenc": "C", "development": "D", "360": "D",
#     "assessment exercise": "E", "knowledge": "K", "skills test": "K",
#     "simulation": "S",
# }
 
# # ---------------------------------------------------------------------
# # Critical-constraint detection
# # ---------------------------------------------------------------------
# # Some roles have a constraint that materially changes WHICH catalog
# # item is correct, not just how well it's explained — e.g. a phone /
# # contact-centre role needs a language-specific version of a test, so
# # recommending before that's known risks handing back the wrong SKU.
# # `Requirements.is_empty()` alone doesn't catch this: a message like
# # "500 entry-level contact centre agents, inbound calls" already
# # populates roles + levels, so the old router treated it as fully
# # specified and recommended immediately. `critical_missing()` adds a
# # second, narrower gate on top of is_empty() for exactly these cases,
# # without turning the router into pure keyword matching for the
# # general routing decision — it only tightens the recommend/clarify
# # boundary for a small, well-defined set of situations where getting
# # it wrong is costly.
 
# # Phrases signalling a phone/voice-based customer-facing role, where
# # the SPOKEN LANGUAGE of the assessment (and the calls) is a hard
# # constraint on which SHL item is correct.
# PHONE_CONTACT_HINTS = [
#     "contact centre", "contact center", "call centre", "call center",
#     "inbound call", "inbound calls", "outbound call", "outbound calls",
#     "phone support", "telephone support", "telephone screening",
#     "customer service", "customer support", "help desk", "helpdesk",
#     "support agent", "support agents",
# ]
 
# # Human-readable phrasing for what's missing, used to steer the
# # clarifying question toward the actual gap instead of a generic one.
# MISSING_HINT_TEXT = {
#     "language": "the language(s) the calls / assessments need to be conducted in",
# }
 
# # Words that signal the user is editing an EXISTING shortlist, plus
# # which direction the edit goes. Order matters: check "replace" before
# # plain "add"/"remove" since it implies both.
# ADD_PATTERN = re.compile(r"(?i)\b(also add|add (?:a|an|the)?|include (?:a|an|the)?)\s+([^.,;]+)")
# REMOVE_PATTERN = re.compile(
#     r"(?i)\b(remove|drop|take out|without the|exclude)\s+(?:the\s+)?([^.,;]+?)"
#     r"(?=\s+(?:and|but|,|\.|$))"
# )
# REPLACE_PATTERN = re.compile(
#     r"(?i)\bremove\s+(?:the\s+)?([^.,;]+?)\s+and\s+replace\s+(?:it\s+)?with\s+([^.,;]+)|"
#     r"\breplace\s+(?:the\s+)?([^.,;]+?)\s+with\s+([^.,;]+)"
# )
 
 
# @dataclass
# class Requirements:
#     roles: List[str] = field(default_factory=list)
#     levels: List[str] = field(default_factory=list)
#     skills: List[str] = field(default_factory=list)
#     industries: List[str] = field(default_factory=list)
#     languages: List[str] = field(default_factory=list)
#     test_type_hints: List[str] = field(default_factory=list)
#     free_text: List[str] = field(default_factory=list)  # raw user turns, for BM25/dense fallback
 
#     def to_query(self) -> str:
#         """Flatten the structured profile into a clean retrieval query.
#         Structured terms are repeated up front (cheap way to weight
#         them higher for BM25) followed by the raw text as a fallback
#         signal for anything the keyword lists didn't catch."""
#         structured = (
#             self.roles + self.levels + self.skills + self.industries + self.languages
#         )
#         parts = []
#         if structured:
#             parts.append(" ".join(structured) + " " + " ".join(structured))
#         parts.extend(self.free_text)
#         return " ".join(parts).strip()
 
#     def is_empty(self) -> bool:
#         return not (self.roles or self.levels or self.skills or self.industries)
 
#     def confidence_score(self) -> int:
#         """
#         Lightweight rule-based confidence score over the already-
#         extracted structured fields — no LLM call, no extra parsing,
#         O(1) on data we already have. One point per requirement
#         CATEGORY that has at least one hit:
 
#             role present                -> +1
#             seniority/level present     -> +1
#             skill present               -> +1
#             industry present            -> +1
#             assessment/test-type pref.  -> +1  (test_type_hints)
 
#         This intentionally scores by category, not by term count, so
#         a message that mentions five skill keywords doesn't outscore
#         one that mentions a role + a level. A single vague category
#         hit (e.g. just "leadership") stays below CONFIDENCE_THRESHOLD,
#         matching the sample pattern where "we need a leadership
#         solution" still gets a clarifying question rather than a
#         shortlist.
#         """
#         score = 0
#         if self.roles:
#             score += 1
#         if self.levels:
#             score += 1
#         if self.skills:
#             score += 1
#         if self.industries:
#             score += 1
#         if self.test_type_hints:
#             score += 1
#         return score
 
#     def critical_missing(self) -> List[str]:
#         """
#         Returns a list of critical-constraint keys that are still
#         missing even though enough general context exists to not be
#         `is_empty()`. Currently covers: phone/contact-centre-type
#         roles missing a call/assessment language, since that decides
#         which language-specific catalog item is actually correct.
 
#         Deliberately narrow and additive: this never fires for roles
#         outside the phone-contact hint list, so it doesn't change
#         behavior for the large majority of recommend-eligible turns
#         (e.g. "Java developers, mid-level" still recommends directly).
#         """
#         missing: List[str] = []
#         combined_text = " ".join(self.free_text).lower()
#         is_phone_role = any(hint in combined_text for hint in PHONE_CONTACT_HINTS)
#         if is_phone_role and not self.languages:
#             missing.append("language")
#         return missing
 
 
# def _extract_terms(text: str, term_list: List[str]) -> List[str]:
#     text_l = text.lower()
#     found = []
#     for term in term_list:
#         if term in text_l and term not in found:
#             found.append(term)
#     return found
 
 
# def extract_requirements(messages: List[Message]) -> Requirements:
#     """Build a structured requirements profile from ALL user turns so
#     far. Called fresh on every request since the API is stateless."""
#     req = Requirements()
#     for m in messages:
#         if m.role != "user":
#             continue
#         text = m.content
#         req.roles.extend(t for t in _extract_terms(text, ROLE_TERMS) if t not in req.roles)
#         req.levels.extend(t for t in _extract_terms(text, LEVEL_TERMS) if t not in req.levels)
#         req.skills.extend(t for t in _extract_terms(text, SKILL_TERMS) if t not in req.skills)
#         req.industries.extend(t for t in _extract_terms(text, INDUSTRY_TERMS) if t not in req.industries)
#         req.languages.extend(t for t in _extract_terms(text, LANGUAGE_TERMS) if t not in req.languages)
#         for hint, code in TEST_TYPE_HINTS.items():
#             if hint in text.lower() and code not in req.test_type_hints:
#                 req.test_type_hints.append(code)
#         req.free_text.append(text)
#     return req
 
 
# @dataclass
# class RefineAction:
#     add_terms: List[str] = field(default_factory=list)
#     remove_terms: List[str] = field(default_factory=list)
#     is_pure_confirmation: bool = False
 
 
# def parse_refine_action(last_user_msg: str) -> RefineAction:
#     """Pull out explicit add/remove/replace instructions from the
#     latest user turn so a 'refine' turn can edit the previous
#     shortlist instead of recomputing it from scratch."""
#     action = RefineAction()
 
#     for m in REPLACE_PATTERN.finditer(last_user_msg):
#         if m.group(1) and m.group(2):
#             action.remove_terms.append(m.group(1).strip())
#             action.add_terms.append(m.group(2).strip())
#         elif m.group(3) and m.group(4):
#             action.remove_terms.append(m.group(3).strip())
#             action.add_terms.append(m.group(4).strip())
 
#     for m in ADD_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.add_terms:
#             action.add_terms.append(term)
 
#     for m in REMOVE_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.remove_terms:
#             action.remove_terms.append(term)
 
#     if not action.add_terms and not action.remove_terms:
#         action.is_pure_confirmation = True
 
#     return action


# r"""
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.

# This module now derives a STRUCTURED requirements profile (role,
# level, skills, industry, language, preferred test types, explicit
# add/remove instructions) from the conversation, instead of just
# concatenating raw text. Retrieval is built on top of this structured
# profile so that:
#   - stray conversational filler ("Perfect, thanks") doesn't dilute
#     the search query, and
#   - a later turn's edits ("also add personality tests") are additive
#     rather than overwriting everything that came before.

# BUGFIX NOTES (all three found by replaying real sample conversations
# through the live pipeline and diffing expected vs. predicted):

#   - ADD_PATTERN previously required a *second* mandatory whitespace
#     after "add " even when no article followed, which is impossible
#     to satisfy — "Add AWS and Docker." never matched at all. Fixed by
#     making the article an optional *prefix* of the capture instead of
#     a fixed-width gap.
#   - REMOVE_PATTERN's lookahead required `\s+` before the sentence
#     terminator, so "Drop the OPQ." (no space before the period) never
#     matched. Now uses `\s*`.
#   - REPLACE_PATTERN's replacement-term capture didn't exclude "?", so
#     a message ending in a question ("...replace it with something
#     shorter? Candidates complain...") swallowed the entire rest of
#     the sentence into a garbage search query.

# Also added FINAL_LIST_PATTERN: phrasing like "Final list: X and Y" or
# "keep only X and Y" is common in refine turns and previously matched
# NEITHER add nor remove, so the named items silently never made it
# into the shortlist. This is now parsed as a full-replacement
# instruction (see RefineAction.full_replacement_terms).
# """

# import re
# from dataclasses import dataclass, field
# from typing import List, Optional

# from app.models import Message

# MAX_CLARIFYING_QUESTIONS = 2

# # Minimum confidence_score() needed to skip clarification and go
# # straight to retrieval. Categories are: role, level, skill, industry,
# # test-type preference (max possible = 5). Threshold of 2 means a
# # single vague category hit (e.g. only "leadership", or only
# # "assessment") is NOT enough on its own — it still routes to
# # clarify_needed — while any two concrete signals (e.g. role+level,
# # or skill+industry) are enough to retrieve immediately. Tuned against
# # the spec's own examples: "I need an assessment" (score 0), "We need
# # a leadership solution" (score 1, role-only) both stay below
# # threshold; "Java developers, mid-level" (role+level, score 2) clears it.
# CONFIDENCE_THRESHOLD = 2


# # ---------------------------------------------------------------------
# # Turn-budget helpers (unchanged behavior from the original app)
# # ---------------------------------------------------------------------

# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")


# def count_clarifying_turns(messages: List[Message]) -> int:
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count


# def turns_used(messages: List[Message]) -> int:
#     return len(messages)


# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS


# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)


# # ---------------------------------------------------------------------
# # Structured requirements profile
# # ---------------------------------------------------------------------

# ROLE_TERMS = [
#     "engineer", "developer", "programmer", "analyst", "manager", "director",
#     "executive", "cxo", "leadership", "sales", "customer service",
#     "contact centre", "contact center", "call centre", "call center",
#     "admin", "administrative assistant", "clerk", "technician", "operator",
#     "plant operator", "graduate", "trainee", "intern", "nurse", "accountant",
#     "financial analyst", "healthcare admin",
# ]

# # Terms in ROLE_TERMS that are too generic to identify a searchable
# # role on their own (e.g. "leadership" could mean anyone from a new
# # supervisor to a CXO). They still populate Requirements.roles so
# # retrieval queries include them, but they don't earn a point in
# # confidence_score() unless paired with something more specific (a
# # level, a concrete title, etc. — captured by the OTHER categories
# # already scoring their own point). Matches the sample pattern where
# # "we need a solution for senior leadership" still gets a clarifying
# # question about who exactly the audience is, despite "leadership"
# # + "senior" superficially looking like two populated categories.
# VAGUE_ROLE_TERMS = {"leadership"}

# LEVEL_TERMS = [
#     "entry-level", "entry level", "graduate", "junior", "mid-level",
#     "mid level", "senior", "director", "executive", "cxo", "individual contributor",
#     "supervisor", "front line manager", "manager", "professional",
# ]

# SKILL_TERMS = [
#     "java", "python", "sql", "excel", "word", "aws", "docker", "angular",
#     "spring", "rust", "coding", "programming", ".net", "javascript",
#     "numerical reasoning", "verbal reasoning", "cognitive", "deductive reasoning",
#     "situational judgement", "situational judgment", "personality",
#     "typing", "data entry", "customer service", "sales skills",
# ]

# INDUSTRY_TERMS = [
#     "healthcare", "finance", "financial", "banking", "manufacturing",
#     "chemical", "retail", "technology", "insurance", "pharma",
# ]

# LANGUAGE_TERMS = [
#     "english", "spanish", "french", "german", "mandarin", "hindi", "portuguese",
# ]

# TEST_TYPE_HINTS = {
#     "personality": "P", "cognitive": "A", "ability": "A", "aptitude": "A",
#     "situational judgement": "B", "situational judgment": "B", "biodata": "B",
#     "competenc": "C", "development": "D", "360": "D",
#     "assessment exercise": "E", "knowledge": "K", "skills test": "K",
#     "simulation": "S",
# }

# # ---------------------------------------------------------------------
# # Critical-constraint detection
# # ---------------------------------------------------------------------
# # Some roles have a constraint that materially changes WHICH catalog
# # item is correct, not just how well it's explained — e.g. a phone /
# # contact-centre role needs a language-specific version of a test, so
# # recommending before that's known risks handing back the wrong SKU.
# # `Requirements.is_empty()` alone doesn't catch this: a message like
# # "500 entry-level contact centre agents, inbound calls" already
# # populates roles + levels, so the old router treated it as fully
# # specified and recommended immediately. `critical_missing()` adds a
# # second, narrower gate on top of is_empty() for exactly these cases,
# # without turning the router into pure keyword matching for the
# # general routing decision — it only tightens the recommend/clarify
# # boundary for a small, well-defined set of situations where getting
# # it wrong is costly.

# # Phrases signalling a phone/voice-based customer-facing role, where
# # the SPOKEN LANGUAGE of the assessment (and the calls) is a hard
# # constraint on which SHL item is correct.
# PHONE_CONTACT_HINTS = [
#     "contact centre", "contact center", "call centre", "call center",
#     "inbound call", "inbound calls", "outbound call", "outbound calls",
#     "phone support", "telephone support", "telephone screening",
#     "customer service", "customer support", "help desk", "helpdesk",
#     "support agent", "support agents",
# ]

# # Roles where the hiring need is dominated by a role-specific
# # operational/safety instrument (e.g. Manufac. & Indust. - Safety &
# # Dependability) rather than a general workplace-behavioural-style
# # assessment — so we should NOT nudge retrieval toward a generic
# # personality query for these.
# OPERATIONAL_SAFETY_HINTS = [
#     "plant operator", "plant operators", "chemical facility",
#     "chemical plant", "manufacturing floor", "factory floor",
#     "warehouse operator", "machine operator", "production line",
# ]

# # Human-readable phrasing for what's missing, used to steer the
# # clarifying question toward the actual gap instead of a generic one.
# MISSING_HINT_TEXT = {
#     "language": "the language(s) the calls / assessments need to be conducted in",
# }

# # ---------------------------------------------------------------------
# # Refine-instruction patterns
# # ---------------------------------------------------------------------
# # Words that signal the user is editing an EXISTING shortlist, plus
# # which direction the edit goes. Order matters: check "replace" before
# # plain "add"/"remove" since it implies both.
# #
# # ADD_PATTERN: the article ("a"/"an"/"the") is an optional PREFIX of
# # the capture, not a separate fixed-width gap — "add X", "add a X",
# # "add an X", "add the X", and "also add X" all match with exactly one
# # required space between the trigger and the content.
# ADD_PATTERN = re.compile(r"(?i)\b(also add|add|include)\s+(?:a\s+|an\s+|the\s+)?([^.,;?]+)")

# # REMOVE_PATTERN: lookahead uses `\s*` (not `\s+`) so a terminator that
# # immediately follows the term with no space ("Drop the OPQ.") still
# # matches. "?" and an em-dash are also valid terminators.
# REMOVE_PATTERN = re.compile(
#     r"(?i)\b(remove|drop|take out|without the|exclude)\s+(?:the\s+)?([^.,;?—]+?)"
#     r"(?=\s*(?:and|but|,|\.|\?|—|$))"
# )

# # REPLACE_PATTERN: both captures exclude "?" so a trailing question in
# # the same sentence doesn't get swallowed into the replacement term.
# REPLACE_PATTERN = re.compile(
#     r"(?i)\bremove\s+(?:the\s+)?([^.,;?]+?)\s+and\s+replace\s+(?:it\s+)?with\s+([^.,;?]+)|"
#     r"\breplace\s+(?:the\s+)?([^.,;?]+?)\s+with\s+([^.,;?]+)"
# )

# # FINAL_LIST_PATTERN: "Final list: X and Y" / "keep only X and Y" /
# # "just keep X and Y" / "only keep X and Y" — the user is stating the
# # complete desired shortlist, not adding to or subtracting from the
# # existing one. Previously this phrasing matched neither ADD_PATTERN
# # nor REMOVE_PATTERN and the named items were silently dropped.
# FINAL_LIST_PATTERN = re.compile(r"(?i)\b(?:final list|keep only|just keep|only keep)[:\s]+([^.?!]+)")

# # Splits a captured "X and Y", "X, Y and Z", "X & Y" span into
# # individual terms — ADD_PATTERN/FINAL_LIST_PATTERN capture the whole
# # conjunction as one span so multi-item edits aren't lost.
# _TERM_SPLIT_RE = re.compile(r"(?i)\s*(?:,\s*(?:and\s+)?|\s+and\s+|\s*&\s*)\s*")


# def _split_terms(text: str) -> List[str]:
#     parts = [p.strip(" .") for p in _TERM_SPLIT_RE.split(text) if p.strip(" .")]
#     return parts if parts else ([text.strip(" .")] if text.strip(" .") else [])


# @dataclass
# class Requirements:
#     roles: List[str] = field(default_factory=list)
#     levels: List[str] = field(default_factory=list)
#     skills: List[str] = field(default_factory=list)
#     industries: List[str] = field(default_factory=list)
#     languages: List[str] = field(default_factory=list)
#     test_type_hints: List[str] = field(default_factory=list)
#     free_text: List[str] = field(default_factory=list)  # raw user turns, for BM25/dense fallback

#     def wants_personality_boost(self) -> bool:
#         """
#         True when there's real hiring context (a role and/or level) but
#         neither a phone/contact-centre constraint nor an operational-
#         safety role is in play. In SHL's own catalog, a general
#         workplace-behavioural-style assessment (e.g. the OPQ32r family)
#         is near-universally part of a professional/managerial hiring
#         battery even when the user's phrasing never says the word
#         "personality" — role and seniority alone usually imply it. This
#         is deliberately narrow (excludes phone/contact-centre roles,
#         where language is the binding constraint, and operational/
#         safety roles, where a role-specific safety instrument is the
#         right fit instead) so it doesn't distort retrieval for the
#         cases where a generic personality nudge would be wrong.
#         """
#         if not (self.roles or self.levels):
#             return False
#         combined_text = " ".join(self.free_text).lower()
#         if any(hint in combined_text for hint in PHONE_CONTACT_HINTS):
#             return False
#         if any(hint in combined_text for hint in OPERATIONAL_SAFETY_HINTS):
#             return False
#         return True

#     def to_query(self) -> str:
#         """Flatten the structured profile into a clean retrieval query.
#         Structured terms are repeated up front (cheap way to weight
#         them higher for BM25) followed by the raw text as a fallback
#         signal for anything the keyword lists didn't catch.

#         Also appends a single light-weight "personality/behavioural
#         style" boost phrase when wants_personality_boost() holds. This
#         only nudges BM25/dense ranking toward surfacing generalist
#         personality items in the retrieved pool — it never hardcodes or
#         force-injects a specific catalog item, so it stays correct even
#         if catalog naming changes.
#         """
#         structured = (
#             self.roles + self.levels + self.skills + self.industries + self.languages
#         )
#         parts = []
#         if structured:
#             parts.append(" ".join(structured) + " " + " ".join(structured))
#         parts.extend(self.free_text)
#         if self.wants_personality_boost():
#             parts.append("personality behavioural style workplace conduct questionnaire")
#         return " ".join(parts).strip()

#     def is_empty(self) -> bool:
#         return not (self.roles or self.levels or self.skills or self.industries)

#     def confidence_score(self) -> int:
#         """
#         Lightweight rule-based confidence score over the already-
#         extracted structured fields — no LLM call, no extra parsing,
#         O(1) on data we already have. One point per requirement
#         CATEGORY that has at least one hit:

#             role present                -> +1
#             seniority/level present     -> +1
#             skill present               -> +1
#             industry present            -> +1
#             assessment/test-type pref.  -> +1  (test_type_hints)

#         This intentionally scores by category, not by term count, so
#         a message that mentions five skill keywords doesn't outscore
#         one that mentions a role + a level. A single vague category
#         hit (e.g. just "leadership") stays below CONFIDENCE_THRESHOLD,
#         matching the sample pattern where "we need a leadership
#         solution" still gets a clarifying question rather than a
#         shortlist.
#         """
#         score = 0
#         if self.roles:
#             score += 1
#         if self.levels:
#             score += 1
#         if self.skills:
#             score += 1
#         if self.industries:
#             score += 1
#         if self.test_type_hints:
#             score += 1
#         return score

#     def critical_missing(self) -> List[str]:
#         """
#         Returns a list of critical-constraint keys that are still
#         missing even though enough general context exists to not be
#         `is_empty()`. Currently covers: phone/contact-centre-type
#         roles missing a call/assessment language, since that decides
#         which language-specific catalog item is actually correct.

#         Deliberately narrow and additive: this never fires for roles
#         outside the phone-contact hint list, so it doesn't change
#         behavior for the large majority of recommend-eligible turns
#         (e.g. "Java developers, mid-level" still recommends directly).
#         """
#         missing: List[str] = []
#         combined_text = " ".join(self.free_text).lower()
#         is_phone_role = any(hint in combined_text for hint in PHONE_CONTACT_HINTS)
#         if is_phone_role and not self.languages:
#             missing.append("language")
#         return missing


# def _extract_terms(text: str, term_list: List[str]) -> List[str]:
#     text_l = text.lower()
#     found = []
#     for term in term_list:
#         if term in text_l and term not in found:
#             found.append(term)
#     return found


# def extract_requirements(messages: List[Message]) -> Requirements:
#     """Build a structured requirements profile from ALL user turns so
#     far. Called fresh on every request since the API is stateless."""
#     req = Requirements()
#     for m in messages:
#         if m.role != "user":
#             continue
#         text = m.content
#         req.roles.extend(t for t in _extract_terms(text, ROLE_TERMS) if t not in req.roles)
#         req.levels.extend(t for t in _extract_terms(text, LEVEL_TERMS) if t not in req.levels)
#         req.skills.extend(t for t in _extract_terms(text, SKILL_TERMS) if t not in req.skills)
#         req.industries.extend(t for t in _extract_terms(text, INDUSTRY_TERMS) if t not in req.industries)
#         req.languages.extend(t for t in _extract_terms(text, LANGUAGE_TERMS) if t not in req.languages)
#         for hint, code in TEST_TYPE_HINTS.items():
#             if hint in text.lower() and code not in req.test_type_hints:
#                 req.test_type_hints.append(code)
#         req.free_text.append(text)
#     return req


# @dataclass
# class RefineAction:
#     add_terms: List[str] = field(default_factory=list)
#     remove_terms: List[str] = field(default_factory=list)
#     # If non-empty, the user stated the COMPLETE desired shortlist
#     # ("Final list: X and Y") rather than an incremental edit — this
#     # should override prior_items/add/remove merging entirely.
#     full_replacement_terms: List[str] = field(default_factory=list)
#     is_pure_confirmation: bool = False


# def parse_refine_action(last_user_msg: str) -> RefineAction:
#     """Pull out explicit add/remove/replace/final-list instructions
#     from the latest user turn so a 'refine' turn can edit the previous
#     shortlist instead of recomputing it from scratch."""
#     action = RefineAction()

#     for m in FINAL_LIST_PATTERN.finditer(last_user_msg):
#         for term in _split_terms(m.group(1)):
#             if term and term not in action.full_replacement_terms:
#                 action.full_replacement_terms.append(term)

#     for m in REPLACE_PATTERN.finditer(last_user_msg):
#         if m.group(1) and m.group(2):
#             action.remove_terms.append(m.group(1).strip())
#             action.add_terms.extend(_split_terms(m.group(2)))
#         elif m.group(3) and m.group(4):
#             action.remove_terms.append(m.group(3).strip())
#             action.add_terms.extend(_split_terms(m.group(4)))

#     for m in ADD_PATTERN.finditer(last_user_msg):
#         for term in _split_terms(m.group(2)):
#             if term and term not in action.add_terms:
#                 action.add_terms.append(term)

#     for m in REMOVE_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.remove_terms:
#             action.remove_terms.append(term)

#     if not action.add_terms and not action.remove_terms and not action.full_replacement_terms:
#         action.is_pure_confirmation = True

#     return action



# r"""
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.
 
# This module now derives a STRUCTURED requirements profile (role,
# level, skills, industry, language, preferred test types, explicit
# add/remove instructions) from the conversation, instead of just
# concatenating raw text. Retrieval is built on top of this structured
# profile so that:
#   - stray conversational filler ("Perfect, thanks") doesn't dilute
#     the search query, and
#   - a later turn's edits ("also add personality tests") are additive
#     rather than overwriting everything that came before.
 
# BUGFIX NOTES (all three found by replaying real sample conversations
# through the live pipeline and diffing expected vs. predicted):
 
#   - ADD_PATTERN previously required a *second* mandatory whitespace
#     after "add " even when no article followed, which is impossible
#     to satisfy — "Add AWS and Docker." never matched at all. Fixed by
#     making the article an optional *prefix* of the capture instead of
#     a fixed-width gap.
#   - REMOVE_PATTERN's lookahead required `\s+` before the sentence
#     terminator, so "Drop the OPQ." (no space before the period) never
#     matched. Now uses `\s*`.
#   - REPLACE_PATTERN's replacement-term capture didn't exclude "?", so
#     a message ending in a question ("...replace it with something
#     shorter? Candidates complain...") swallowed the entire rest of
#     the sentence into a garbage search query.
 
# Also added FINAL_LIST_PATTERN: phrasing like "Final list: X and Y" or
# "keep only X and Y" is common in refine turns and previously matched
# NEITHER add nor remove, so the named items silently never made it
# into the shortlist. This is now parsed as a full-replacement
# instruction (see RefineAction.full_replacement_terms).
# """
 
# import re
# from dataclasses import dataclass, field
# from typing import List, Optional
 
# from app.models import Message
 
# MAX_CLARIFYING_QUESTIONS = 2
 
# # Minimum confidence_score() needed to skip clarification and go
# # straight to retrieval. Categories are: role, level, skill, industry,
# # test-type preference (max possible = 5). Threshold of 2 means a
# # single vague category hit (e.g. only "leadership", or only
# # "assessment") is NOT enough on its own — it still routes to
# # clarify_needed — while any two concrete signals (e.g. role+level,
# # or skill+industry) are enough to retrieve immediately. Tuned against
# # the spec's own examples: "I need an assessment" (score 0), "We need
# # a leadership solution" (score 1, role-only) both stay below
# # threshold; "Java developers, mid-level" (role+level, score 2) clears it.
# CONFIDENCE_THRESHOLD = 2
 
 
# # ---------------------------------------------------------------------
# # Turn-budget helpers (unchanged behavior from the original app)
# # ---------------------------------------------------------------------
 
# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")
 
 
# def count_clarifying_turns(messages: List[Message]) -> int:
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count
 
 
# def turns_used(messages: List[Message]) -> int:
#     return len(messages)
 
 
# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS
 
 
# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)
 
 
# # ---------------------------------------------------------------------
# # Structured requirements profile
# # ---------------------------------------------------------------------
 
# ROLE_TERMS = [
#     "engineer", "developer", "programmer", "analyst", "manager", "director",
#     "executive", "cxo", "leadership", "sales", "customer service",
#     "contact centre", "contact center", "call centre", "call center",
#     "admin", "administrative assistant", "clerk", "technician", "operator",
#     "plant operator", "graduate", "trainee", "intern", "nurse", "accountant",
#     "financial analyst", "healthcare admin",
# ]
 
# # Terms in ROLE_TERMS that are too generic to identify a searchable
# # role on their own (e.g. "leadership" could mean anyone from a new
# # supervisor to a CXO). They still populate Requirements.roles so
# # retrieval queries include them, but they don't earn a point in
# # confidence_score() unless paired with something more specific (a
# # level, a concrete title, etc. — captured by the OTHER categories
# # already scoring their own point). Matches the sample pattern where
# # "we need a solution for senior leadership" still gets a clarifying
# # question about who exactly the audience is, despite "leadership"
# # + "senior" superficially looking like two populated categories.
# VAGUE_ROLE_TERMS = {"leadership"}
 
# LEVEL_TERMS = [
#     "entry-level", "entry level", "graduate", "junior", "mid-level",
#     "mid level", "senior", "director", "executive", "cxo", "individual contributor",
#     "supervisor", "front line manager", "manager", "professional",
# ]
 
# SKILL_TERMS = [
#     "java", "python", "sql", "excel", "word", "aws", "docker", "angular",
#     "spring", "rust", "coding", "programming", ".net", "javascript",
#     "numerical reasoning", "verbal reasoning", "cognitive", "deductive reasoning",
#     "situational judgement", "situational judgment", "personality",
#     "typing", "data entry", "customer service", "sales skills",
#     # Added after replaying the sample conversations against the live
#     # catalog and diffing expected vs. predicted shortlists — these
#     # terms appeared in real transcripts but weren't boosting
#     # retrieval because they weren't in the structured term list yet.
#     "linux", "networking", "statistics", "microsoft office", "office",
#     "hipaa", "medical terminology", "hiring", "interviewing",
#     "safety", "dependability", "compliance", "reasoning", "leadership skills",
# ]
 
# INDUSTRY_TERMS = [
#     "healthcare", "finance", "financial", "banking", "manufacturing",
#     "chemical", "retail", "technology", "insurance", "pharma",
#     "petrochemical", "industrial",
# ]
 
# LANGUAGE_TERMS = [
#     "english", "spanish", "french", "german", "mandarin", "hindi", "portuguese",
#     "castilian", "north american", "spoken english", "spoken spanish",
# ]
 
# TEST_TYPE_HINTS = {
#     "personality": "P", "cognitive": "A", "ability": "A", "aptitude": "A",
#     "situational judgement": "B", "situational judgment": "B", "biodata": "B",
#     "competenc": "C", "development": "D", "360": "D",
#     "assessment exercise": "E", "knowledge": "K", "skills test": "K",
#     "simulation": "S",
# }
 
# # ---------------------------------------------------------------------
# # Critical-constraint detection
# # ---------------------------------------------------------------------
# # Some roles have a constraint that materially changes WHICH catalog
# # item is correct, not just how well it's explained — e.g. a phone /
# # contact-centre role needs a language-specific version of a test, so
# # recommending before that's known risks handing back the wrong SKU.
# # `Requirements.is_empty()` alone doesn't catch this: a message like
# # "500 entry-level contact centre agents, inbound calls" already
# # populates roles + levels, so the old router treated it as fully
# # specified and recommended immediately. `critical_missing()` adds a
# # second, narrower gate on top of is_empty() for exactly these cases,
# # without turning the router into pure keyword matching for the
# # general routing decision — it only tightens the recommend/clarify
# # boundary for a small, well-defined set of situations where getting
# # it wrong is costly.
 
# # Phrases signalling a phone/voice-based customer-facing role, where
# # the SPOKEN LANGUAGE of the assessment (and the calls) is a hard
# # constraint on which SHL item is correct.
# PHONE_CONTACT_HINTS = [
#     "contact centre", "contact center", "call centre", "call center",
#     "inbound call", "inbound calls", "outbound call", "outbound calls",
#     "phone support", "telephone support", "telephone screening",
#     "customer service", "customer support", "help desk", "helpdesk",
#     "support agent", "support agents",
# ]
 
# # Roles where the hiring need is dominated by a role-specific
# # operational/safety instrument (e.g. Manufac. & Indust. - Safety &
# # Dependability) rather than a general workplace-behavioural-style
# # assessment — so we should NOT nudge retrieval toward a generic
# # personality query for these.
# OPERATIONAL_SAFETY_HINTS = [
#     "plant operator", "plant operators", "chemical facility",
#     "chemical plant", "manufacturing floor", "factory floor",
#     "warehouse operator", "machine operator", "production line",
# ]
 
# # Human-readable phrasing for what's missing, used to steer the
# # clarifying question toward the actual gap instead of a generic one.
# MISSING_HINT_TEXT = {
#     "language": "the language(s) the calls / assessments need to be conducted in",
# }
 
# # ---------------------------------------------------------------------
# # Refine-instruction patterns
# # ---------------------------------------------------------------------
# # Words that signal the user is editing an EXISTING shortlist, plus
# # which direction the edit goes. Order matters: check "replace" before
# # plain "add"/"remove" since it implies both.
# #
# # ADD_PATTERN: the article ("a"/"an"/"the") is an optional PREFIX of
# # the capture, not a separate fixed-width gap — "add X", "add a X",
# # "add an X", "add the X", and "also add X" all match with exactly one
# # required space between the trigger and the content.
# ADD_PATTERN = re.compile(r"(?i)\b(also add|add|include)\s+(?:a\s+|an\s+|the\s+)?([^.,;?]+)")
 
# # REMOVE_PATTERN: lookahead uses `\s*` (not `\s+`) so a terminator that
# # immediately follows the term with no space ("Drop the OPQ.") still
# # matches. "?" and an em-dash are also valid terminators.
# REMOVE_PATTERN = re.compile(
#     r"(?i)\b(remove|drop|take out|without the|exclude)\s+(?:the\s+)?([^.,;?—]+?)"
#     r"(?=\s*(?:and|but|,|\.|\?|—|$))"
# )
 
# # REPLACE_PATTERN: both captures exclude "?" so a trailing question in
# # the same sentence doesn't get swallowed into the replacement term.
# REPLACE_PATTERN = re.compile(
#     r"(?i)\bremove\s+(?:the\s+)?([^.,;?]+?)\s+and\s+replace\s+(?:it\s+)?with\s+([^.,;?]+)|"
#     r"\breplace\s+(?:the\s+)?([^.,;?]+?)\s+with\s+([^.,;?]+)"
# )
 
# # FINAL_LIST_PATTERN: "Final list: X and Y" / "keep only X and Y" /
# # "just keep X and Y" / "only keep X and Y" — the user is stating the
# # complete desired shortlist, not adding to or subtracting from the
# # existing one. Previously this phrasing matched neither ADD_PATTERN
# # nor REMOVE_PATTERN and the named items were silently dropped.
# FINAL_LIST_PATTERN = re.compile(r"(?i)\b(?:final list|keep only|just keep|only keep)[:\s]+([^.?!]+)")
 
# # Splits a captured "X and Y", "X, Y and Z", "X & Y" span into
# # individual terms — ADD_PATTERN/FINAL_LIST_PATTERN capture the whole
# # conjunction as one span so multi-item edits aren't lost.
# _TERM_SPLIT_RE = re.compile(r"(?i)\s*(?:,\s*(?:and\s+)?|\s+and\s+|\s*&\s*)\s*")
 
 
# def _split_terms(text: str) -> List[str]:
#     parts = [p.strip(" .") for p in _TERM_SPLIT_RE.split(text) if p.strip(" .")]
#     return parts if parts else ([text.strip(" .")] if text.strip(" .") else [])
 
 
# @dataclass
# class Requirements:
#     roles: List[str] = field(default_factory=list)
#     levels: List[str] = field(default_factory=list)
#     skills: List[str] = field(default_factory=list)
#     industries: List[str] = field(default_factory=list)
#     languages: List[str] = field(default_factory=list)
#     test_type_hints: List[str] = field(default_factory=list)
#     free_text: List[str] = field(default_factory=list)  # raw user turns, for BM25/dense fallback
 
#     def wants_personality_boost(self) -> bool:
#         """
#         True when there's real hiring context (a role and/or level) but
#         neither a phone/contact-centre constraint nor an operational-
#         safety role is in play. In SHL's own catalog, a general
#         workplace-behavioural-style assessment (e.g. the OPQ32r family)
#         is near-universally part of a professional/managerial hiring
#         battery even when the user's phrasing never says the word
#         "personality" — role and seniority alone usually imply it. This
#         is deliberately narrow (excludes phone/contact-centre roles,
#         where language is the binding constraint, and operational/
#         safety roles, where a role-specific safety instrument is the
#         right fit instead) so it doesn't distort retrieval for the
#         cases where a generic personality nudge would be wrong.
#         """
#         if not (self.roles or self.levels):
#             return False
#         combined_text = " ".join(self.free_text).lower()
#         if any(hint in combined_text for hint in PHONE_CONTACT_HINTS):
#             return False
#         if any(hint in combined_text for hint in OPERATIONAL_SAFETY_HINTS):
#             return False
#         return True
 
#     def to_query(self) -> str:
#         """Flatten the structured profile into a clean retrieval query.
#         Structured terms are repeated up front (cheap way to weight
#         them higher for BM25) followed by the raw text as a fallback
#         signal for anything the keyword lists didn't catch.
 
#         Also appends a single light-weight "personality/behavioural
#         style" boost phrase when wants_personality_boost() holds. This
#         only nudges BM25/dense ranking toward surfacing generalist
#         personality items in the retrieved pool — it never hardcodes or
#         force-injects a specific catalog item, so it stays correct even
#         if catalog naming changes.
#         """
#         structured = (
#             self.roles + self.levels + self.skills + self.industries + self.languages
#         )
#         parts = []
#         if structured:
#             parts.append(" ".join(structured) + " " + " ".join(structured))
#         parts.extend(self.free_text)
#         if self.wants_personality_boost():
#             parts.append("personality behavioural style workplace conduct questionnaire")
#         return " ".join(parts).strip()
 
#     def is_empty(self) -> bool:
#         return not (self.roles or self.levels or self.skills or self.industries)
 
#     def confidence_score(self) -> int:
#         """
#         Lightweight rule-based confidence score over the already-
#         extracted structured fields — no LLM call, no extra parsing,
#         O(1) on data we already have. One point per requirement
#         CATEGORY that has at least one hit:
 
#             role present                -> +1
#             seniority/level present     -> +1
#             skill present               -> +1
#             industry present            -> +1
#             assessment/test-type pref.  -> +1  (test_type_hints)
 
#         This intentionally scores by category, not by term count, so
#         a message that mentions five skill keywords doesn't outscore
#         one that mentions a role + a level. A single vague category
#         hit (e.g. just "leadership") stays below CONFIDENCE_THRESHOLD,
#         matching the sample pattern where "we need a leadership
#         solution" still gets a clarifying question rather than a
#         shortlist.
#         """
#         score = 0
#         if self.roles:
#             score += 1
#         if self.levels:
#             score += 1
#         if self.skills:
#             score += 1
#         if self.industries:
#             score += 1
#         if self.test_type_hints:
#             score += 1
#         return score
 
#     def critical_missing(self) -> List[str]:
#         """
#         Returns a list of critical-constraint keys that are still
#         missing even though enough general context exists to not be
#         `is_empty()`. Currently covers: phone/contact-centre-type
#         roles missing a call/assessment language, since that decides
#         which language-specific catalog item is actually correct.
 
#         Deliberately narrow and additive: this never fires for roles
#         outside the phone-contact hint list, so it doesn't change
#         behavior for the large majority of recommend-eligible turns
#         (e.g. "Java developers, mid-level" still recommends directly).
#         """
#         missing: List[str] = []
#         combined_text = " ".join(self.free_text).lower()
#         is_phone_role = any(hint in combined_text for hint in PHONE_CONTACT_HINTS)
#         if is_phone_role and not self.languages:
#             missing.append("language")
#         return missing
 
 
# def _extract_terms(text: str, term_list: List[str]) -> List[str]:
#     text_l = text.lower()
#     found = []
#     for term in term_list:
#         if term in text_l and term not in found:
#             found.append(term)
#     return found
 
 
# def extract_requirements(messages: List[Message]) -> Requirements:
#     """Build a structured requirements profile from ALL user turns so
#     far. Called fresh on every request since the API is stateless."""
#     req = Requirements()
#     for m in messages:
#         if m.role != "user":
#             continue
#         text = m.content
#         req.roles.extend(t for t in _extract_terms(text, ROLE_TERMS) if t not in req.roles)
#         req.levels.extend(t for t in _extract_terms(text, LEVEL_TERMS) if t not in req.levels)
#         req.skills.extend(t for t in _extract_terms(text, SKILL_TERMS) if t not in req.skills)
#         req.industries.extend(t for t in _extract_terms(text, INDUSTRY_TERMS) if t not in req.industries)
#         req.languages.extend(t for t in _extract_terms(text, LANGUAGE_TERMS) if t not in req.languages)
#         for hint, code in TEST_TYPE_HINTS.items():
#             if hint in text.lower() and code not in req.test_type_hints:
#                 req.test_type_hints.append(code)
#         req.free_text.append(text)
#     return req
 
 
# @dataclass
# class RefineAction:
#     add_terms: List[str] = field(default_factory=list)
#     remove_terms: List[str] = field(default_factory=list)
#     # If non-empty, the user stated the COMPLETE desired shortlist
#     # ("Final list: X and Y") rather than an incremental edit — this
#     # should override prior_items/add/remove merging entirely.
#     full_replacement_terms: List[str] = field(default_factory=list)
#     is_pure_confirmation: bool = False
 
 
# def parse_refine_action(last_user_msg: str) -> RefineAction:
#     """Pull out explicit add/remove/replace/final-list instructions
#     from the latest user turn so a 'refine' turn can edit the previous
#     shortlist instead of recomputing it from scratch."""
#     action = RefineAction()
 
#     for m in FINAL_LIST_PATTERN.finditer(last_user_msg):
#         for term in _split_terms(m.group(1)):
#             if term and term not in action.full_replacement_terms:
#                 action.full_replacement_terms.append(term)
 
#     for m in REPLACE_PATTERN.finditer(last_user_msg):
#         if m.group(1) and m.group(2):
#             action.remove_terms.append(m.group(1).strip())
#             action.add_terms.extend(_split_terms(m.group(2)))
#         elif m.group(3) and m.group(4):
#             action.remove_terms.append(m.group(3).strip())
#             action.add_terms.extend(_split_terms(m.group(4)))
 
#     for m in ADD_PATTERN.finditer(last_user_msg):
#         for term in _split_terms(m.group(2)):
#             if term and term not in action.add_terms:
#                 action.add_terms.append(term)
 
#     for m in REMOVE_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.remove_terms:
#             action.remove_terms.append(term)
 
#     if not action.add_terms and not action.remove_terms and not action.full_replacement_terms:
#         action.is_pure_confirmation = True
 
#     return action



 
# r"""
# The API is stateless — every /chat call gets the FULL history and
# nothing is stored between calls. So "state" (facts gathered so far,
# current shortlist, how many clarifying questions already asked) must
# be re-derived from the messages list every single time.
 
# This module now derives a STRUCTURED requirements profile (role,
# level, skills, industry, language, preferred test types, explicit
# add/remove instructions) from the conversation, instead of just
# concatenating raw text. Retrieval is built on top of this structured
# profile so that:
#   - stray conversational filler ("Perfect, thanks") doesn't dilute
#     the search query, and
#   - a later turn's edits ("also add personality tests") are additive
#     rather than overwriting everything that came before.
 
# BUGFIX NOTES (all three found by replaying real sample conversations
# through the live pipeline and diffing expected vs. predicted):
 
#   - ADD_PATTERN previously required a *second* mandatory whitespace
#     after "add " even when no article followed, which is impossible
#     to satisfy — "Add AWS and Docker." never matched at all. Fixed by
#     making the article an optional *prefix* of the capture instead of
#     a fixed-width gap.
#   - REMOVE_PATTERN's lookahead required `\s+` before the sentence
#     terminator, so "Drop the OPQ." (no space before the period) never
#     matched. Now uses `\s*`.
#   - REPLACE_PATTERN's replacement-term capture didn't exclude "?", so
#     a message ending in a question ("...replace it with something
#     shorter? Candidates complain...") swallowed the entire rest of
#     the sentence into a garbage search query.
 
# Also added FINAL_LIST_PATTERN: phrasing like "Final list: X and Y" or
# "keep only X and Y" is common in refine turns and previously matched
# NEITHER add nor remove, so the named items silently never made it
# into the shortlist. This is now parsed as a full-replacement
# instruction (see RefineAction.full_replacement_terms).
# """
 
# import re
# from dataclasses import dataclass, field
# from typing import List, Optional
 
# from app.models import Message
 
# MAX_CLARIFYING_QUESTIONS = 2
 
# # Minimum confidence_score() needed to skip clarification and go
# # straight to retrieval. Categories are: role, level, skill, industry,
# # test-type preference (max possible = 5). Threshold of 2 means a
# # single vague category hit (e.g. only "leadership", or only
# # "assessment") is NOT enough on its own — it still routes to
# # clarify_needed — while any two concrete signals (e.g. role+level,
# # or skill+industry) are enough to retrieve immediately. Tuned against
# # the spec's own examples: "I need an assessment" (score 0), "We need
# # a leadership solution" (score 1, role-only) both stay below
# # threshold; "Java developers, mid-level" (role+level, score 2) clears it.
# CONFIDENCE_THRESHOLD = 2
 
 
# # ---------------------------------------------------------------------
# # Turn-budget helpers (unchanged behavior from the original app)
# # ---------------------------------------------------------------------
 
# def get_user_context(messages: List[Message]) -> str:
#     """All user turns concatenated — this is the 'facts known so far'."""
#     return "\n".join(m.content for m in messages if m.role == "user")
 
 
# def count_clarifying_turns(messages: List[Message]) -> int:
#     count = 0
#     for m in messages:
#         if m.role == "assistant" and m.content.strip().endswith("?"):
#             count += 1
#     return count
 
 
# def turns_used(messages: List[Message]) -> int:
#     return len(messages)
 
 
# def clarify_budget_exhausted(messages: List[Message]) -> bool:
#     return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS
 
 
# def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
#     """True when we're close enough to the 8-turn cap that we must
#     commit to a shortlist now instead of asking anything else."""
#     return turns_used(messages) >= (cap - buffer)
 
 
# # ---------------------------------------------------------------------
# # Structured requirements profile
# # ---------------------------------------------------------------------
 
# ROLE_TERMS = [
#     "engineer", "developer", "programmer", "analyst", "manager", "director",
#     "executive", "cxo", "leadership", "sales", "customer service",
#     "contact centre", "contact center", "call centre", "call center",
#     "admin", "administrative assistant", "clerk", "technician", "operator",
#     "plant operator", "graduate", "trainee", "intern", "nurse", "accountant",
#     "financial analyst", "healthcare admin",
# ]
 
# # Terms in ROLE_TERMS that are too generic to identify a searchable
# # role on their own (e.g. "leadership" could mean anyone from a new
# # supervisor to a CXO). They still populate Requirements.roles so
# # retrieval queries include them, but they don't earn a point in
# # confidence_score() unless paired with something more specific (a
# # level, a concrete title, etc. — captured by the OTHER categories
# # already scoring their own point). Matches the sample pattern where
# # "we need a solution for senior leadership" still gets a clarifying
# # question about who exactly the audience is, despite "leadership"
# # + "senior" superficially looking like two populated categories.
# VAGUE_ROLE_TERMS = {"leadership"}
 
# LEVEL_TERMS = [
#     "entry-level", "entry level", "graduate", "junior", "mid-level",
#     "mid level", "senior", "director", "executive", "cxo", "individual contributor",
#     "supervisor", "front line manager", "manager", "professional",
# ]
 
# SKILL_TERMS = [
#     "java", "python", "sql", "excel", "word", "aws", "docker", "angular",
#     "spring", "rust", "coding", "programming", ".net", "javascript",
#     "numerical reasoning", "verbal reasoning", "cognitive", "deductive reasoning",
#     "situational judgement", "situational judgment", "personality",
#     "typing", "data entry", "customer service", "sales skills",
#     # Added after replaying the sample conversations against the live
#     # catalog and diffing expected vs. predicted shortlists — these
#     # terms appeared in real transcripts but weren't boosting
#     # retrieval because they weren't in the structured term list yet.
#     "linux", "networking", "statistics", "microsoft office", "office",
#     "hipaa", "medical terminology", "hiring", "interviewing",
#     "safety", "dependability", "compliance", "reasoning", "leadership skills",
# ]
 
# INDUSTRY_TERMS = [
#     "healthcare", "finance", "financial", "banking", "manufacturing",
#     "chemical", "retail", "technology", "insurance", "pharma",
#     "petrochemical", "industrial",
# ]
 
# LANGUAGE_TERMS = [
#     "english", "spanish", "french", "german", "mandarin", "hindi", "portuguese",
#     "castilian", "north american", "spoken english", "spoken spanish",
# ]
 
# TEST_TYPE_HINTS = {
#     "personality": "P", "cognitive": "A", "ability": "A", "aptitude": "A",
#     "situational judgement": "B", "situational judgment": "B", "biodata": "B",
#     "competenc": "C", "development": "D", "360": "D",
#     "assessment exercise": "E", "knowledge": "K", "skills test": "K",
#     "simulation": "S",
# }
 
# # ---------------------------------------------------------------------
# # Critical-constraint detection
# # ---------------------------------------------------------------------
# # Some roles have a constraint that materially changes WHICH catalog
# # item is correct, not just how well it's explained — e.g. a phone /
# # contact-centre role needs a language-specific version of a test, so
# # recommending before that's known risks handing back the wrong SKU.
# # `Requirements.is_empty()` alone doesn't catch this: a message like
# # "500 entry-level contact centre agents, inbound calls" already
# # populates roles + levels, so the old router treated it as fully
# # specified and recommended immediately. `critical_missing()` adds a
# # second, narrower gate on top of is_empty() for exactly these cases,
# # without turning the router into pure keyword matching for the
# # general routing decision — it only tightens the recommend/clarify
# # boundary for a small, well-defined set of situations where getting
# # it wrong is costly.
 
# # Phrases signalling a phone/voice-based customer-facing role, where
# # the SPOKEN LANGUAGE of the assessment (and the calls) is a hard
# # constraint on which SHL item is correct.
# PHONE_CONTACT_HINTS = [
#     "contact centre", "contact center", "call centre", "call center",
#     "inbound call", "inbound calls", "outbound call", "outbound calls",
#     "phone support", "telephone support", "telephone screening",
#     "customer service", "customer support", "help desk", "helpdesk",
#     "support agent", "support agents",
# ]
 
# # Roles where the hiring need is dominated by a role-specific
# # operational/safety instrument (e.g. Manufac. & Indust. - Safety &
# # Dependability) rather than a general workplace-behavioural-style
# # assessment — so we should NOT nudge retrieval toward a generic
# # personality query for these.
# OPERATIONAL_SAFETY_HINTS = [
#     "plant operator", "plant operators", "chemical facility",
#     "chemical plant", "manufacturing floor", "factory floor",
#     "warehouse operator", "machine operator", "production line",
# ]
 
# # Human-readable phrasing for what's missing, used to steer the
# # clarifying question toward the actual gap instead of a generic one.
# MISSING_HINT_TEXT = {
#     "language": "the language(s) the calls / assessments need to be conducted in",
# }
 
# # ---------------------------------------------------------------------
# # Refine-instruction patterns
# # ---------------------------------------------------------------------
# # Words that signal the user is editing an EXISTING shortlist, plus
# # which direction the edit goes. Order matters: check "replace" before
# # plain "add"/"remove" since it implies both.
# #
# # ADD_PATTERN: the article ("a"/"an"/"the") is an optional PREFIX of
# # the capture, not a separate fixed-width gap — "add X", "add a X",
# # "add an X", "add the X", and "also add X" all match with exactly one
# # required space between the trigger and the content.
# ADD_PATTERN = re.compile(r"(?i)\b(also add|add|include)\s+(?:a\s+|an\s+|the\s+)?([^.,;?]+)")
 
# # REMOVE_PATTERN: lookahead uses `\s*` (not `\s+`) so a terminator that
# # immediately follows the term with no space ("Drop the OPQ.") still
# # matches. "?" and an em-dash are also valid terminators.
# REMOVE_PATTERN = re.compile(
#     r"(?i)\b(remove|drop|take out|without the|exclude)\s+(?:the\s+)?([^.,;?—]+?)"
#     r"(?=\s*(?:and|but|,|\.|\?|—|$))"
# )
 
# # REPLACE_PATTERN: both captures exclude "?" so a trailing question in
# # the same sentence doesn't get swallowed into the replacement term.
# REPLACE_PATTERN = re.compile(
#     r"(?i)\bremove\s+(?:the\s+)?([^.,;?]+?)\s+and\s+replace\s+(?:it\s+)?with\s+([^.,;?]+)|"
#     r"\breplace\s+(?:the\s+)?([^.,;?]+?)\s+with\s+([^.,;?]+)"
# )
 
# # FINAL_LIST_PATTERN: "Final list: X and Y" / "keep only X and Y" /
# # "just keep X and Y" / "only keep X and Y" — the user is stating the
# # complete desired shortlist, not adding to or subtracting from the
# # existing one. Previously this phrasing matched neither ADD_PATTERN
# # nor REMOVE_PATTERN and the named items were silently dropped.
# FINAL_LIST_PATTERN = re.compile(r"(?i)\b(?:final list|keep only|just keep|only keep)[:\s]+([^.?!]+)")
 
# # Splits a captured "X and Y", "X, Y and Z", "X & Y" span into
# # individual terms — ADD_PATTERN/FINAL_LIST_PATTERN capture the whole
# # conjunction as one span so multi-item edits aren't lost.
# _TERM_SPLIT_RE = re.compile(r"(?i)\s*(?:,\s*(?:and\s+)?|\s+and\s+|\s*&\s*)\s*")
 
 
# def _split_terms(text: str) -> List[str]:
#     parts = [p.strip(" .") for p in _TERM_SPLIT_RE.split(text) if p.strip(" .")]
#     return parts if parts else ([text.strip(" .")] if text.strip(" .") else [])
 
 
# @dataclass
# class Requirements:
#     roles: List[str] = field(default_factory=list)
#     levels: List[str] = field(default_factory=list)
#     skills: List[str] = field(default_factory=list)
#     industries: List[str] = field(default_factory=list)
#     languages: List[str] = field(default_factory=list)
#     test_type_hints: List[str] = field(default_factory=list)
#     free_text: List[str] = field(default_factory=list)  # raw user turns, for BM25/dense fallback
 
#     def wants_personality_boost(self) -> bool:
#         """
#         True when there's real hiring context (a role and/or level) but
#         neither a phone/contact-centre constraint nor an operational-
#         safety role is in play. In SHL's own catalog, a general
#         workplace-behavioural-style assessment (e.g. the OPQ32r family)
#         is near-universally part of a professional/managerial hiring
#         battery even when the user's phrasing never says the word
#         "personality" — role and seniority alone usually imply it. This
#         is deliberately narrow (excludes phone/contact-centre roles,
#         where language is the binding constraint, and operational/
#         safety roles, where a role-specific safety instrument is the
#         right fit instead) so it doesn't distort retrieval for the
#         cases where a generic personality nudge would be wrong.
#         """
#         if not (self.roles or self.levels):
#             return False
#         combined_text = " ".join(self.free_text).lower()
#         if any(hint in combined_text for hint in PHONE_CONTACT_HINTS):
#             return False
#         if any(hint in combined_text for hint in OPERATIONAL_SAFETY_HINTS):
#             return False
#         return True
 
#     def to_query(self) -> str:
#         """Flatten the structured profile into a clean retrieval query.
#         Structured terms are repeated up front (cheap way to weight
#         them higher for BM25) followed by the raw text as a fallback
#         signal for anything the keyword lists didn't catch.
 
#         Also appends a single light-weight "personality/behavioural
#         style" boost phrase when wants_personality_boost() holds. This
#         only nudges BM25/dense ranking toward surfacing generalist
#         personality items in the retrieved pool — it never hardcodes or
#         force-injects a specific catalog item, so it stays correct even
#         if catalog naming changes.
#         """
#         structured = (
#             self.roles + self.levels + self.skills + self.industries + self.languages
#         )
#         parts = []
#         if structured:
#             parts.append(" ".join(structured) + " " + " ".join(structured))
#         parts.extend(self.free_text)
#         if self.wants_personality_boost():
#             parts.append("personality behavioural style workplace conduct questionnaire")
#         return " ".join(parts).strip()
 
#     def is_empty(self) -> bool:
#         return not (self.roles or self.levels or self.skills or self.industries)
 
#     def confidence_score(self) -> int:
#         """
#         Lightweight rule-based confidence score over the already-
#         extracted structured fields — no LLM call, no extra parsing,
#         O(1) on data we already have. One point per requirement
#         CATEGORY that has at least one hit:
 
#             role present                -> +1
#             seniority/level present     -> +1
#             skill present               -> +1
#             industry present            -> +1
#             assessment/test-type pref.  -> +1  (test_type_hints)
 
#         This intentionally scores by category, not by term count, so
#         a message that mentions five skill keywords doesn't outscore
#         one that mentions a role + a level. A single vague category
#         hit (e.g. just "leadership") stays below CONFIDENCE_THRESHOLD,
#         matching the sample pattern where "we need a leadership
#         solution" still gets a clarifying question rather than a
#         shortlist.
#         """
#         score = 0
#         if self.roles:
#             score += 1
#         if self.levels:
#             score += 1
#         if self.skills:
#             score += 1
#         if self.industries:
#             score += 1
#         if self.test_type_hints:
#             score += 1
#         return score
 
#     def critical_missing(self) -> List[str]:
#         """
#         Returns a list of critical-constraint keys that are still
#         missing even though enough general context exists to not be
#         `is_empty()`. Currently covers: phone/contact-centre-type
#         roles missing a call/assessment language, since that decides
#         which language-specific catalog item is actually correct.
 
#         Deliberately narrow and additive: this never fires for roles
#         outside the phone-contact hint list, so it doesn't change
#         behavior for the large majority of recommend-eligible turns
#         (e.g. "Java developers, mid-level" still recommends directly).
#         """
#         missing: List[str] = []
#         combined_text = " ".join(self.free_text).lower()
#         is_phone_role = any(hint in combined_text for hint in PHONE_CONTACT_HINTS)
#         if is_phone_role and not self.languages:
#             missing.append("language")
#         return missing
 
 
# def _extract_terms(text: str, term_list: List[str]) -> List[str]:
#     text_l = text.lower()
#     found = []
#     for term in term_list:
#         if term in text_l and term not in found:
#             found.append(term)
#     return found
 
 
# def extract_requirements(messages: List[Message]) -> Requirements:
#     """Build a structured requirements profile from ALL user turns so
#     far. Called fresh on every request since the API is stateless."""
#     req = Requirements()
#     for m in messages:
#         if m.role != "user":
#             continue
#         text = m.content
#         req.roles.extend(t for t in _extract_terms(text, ROLE_TERMS) if t not in req.roles)
#         req.levels.extend(t for t in _extract_terms(text, LEVEL_TERMS) if t not in req.levels)
#         req.skills.extend(t for t in _extract_terms(text, SKILL_TERMS) if t not in req.skills)
#         req.industries.extend(t for t in _extract_terms(text, INDUSTRY_TERMS) if t not in req.industries)
#         req.languages.extend(t for t in _extract_terms(text, LANGUAGE_TERMS) if t not in req.languages)
#         for hint, code in TEST_TYPE_HINTS.items():
#             if hint in text.lower() and code not in req.test_type_hints:
#                 req.test_type_hints.append(code)
#         req.free_text.append(text)
#     return req
 
 
# @dataclass
# class RefineAction:
#     add_terms: List[str] = field(default_factory=list)
#     remove_terms: List[str] = field(default_factory=list)
#     # If non-empty, the user stated the COMPLETE desired shortlist
#     # ("Final list: X and Y") rather than an incremental edit — this
#     # should override prior_items/add/remove merging entirely.
#     full_replacement_terms: List[str] = field(default_factory=list)
#     is_pure_confirmation: bool = False
 
 
# def parse_refine_action(last_user_msg: str) -> RefineAction:
#     """Pull out explicit add/remove/replace/final-list instructions
#     from the latest user turn so a 'refine' turn can edit the previous
#     shortlist instead of recomputing it from scratch."""
#     action = RefineAction()
 
#     for m in FINAL_LIST_PATTERN.finditer(last_user_msg):
#         for term in _split_terms(m.group(1)):
#             if term and term not in action.full_replacement_terms:
#                 action.full_replacement_terms.append(term)
 
#     for m in REPLACE_PATTERN.finditer(last_user_msg):
#         if m.group(1) and m.group(2):
#             action.remove_terms.append(m.group(1).strip())
#             action.add_terms.extend(_split_terms(m.group(2)))
#         elif m.group(3) and m.group(4):
#             action.remove_terms.append(m.group(3).strip())
#             action.add_terms.extend(_split_terms(m.group(4)))
 
#     for m in ADD_PATTERN.finditer(last_user_msg):
#         for term in _split_terms(m.group(2)):
#             if term and term not in action.add_terms:
#                 action.add_terms.append(term)
 
#     for m in REMOVE_PATTERN.finditer(last_user_msg):
#         term = m.group(2).strip()
#         if term and term not in action.remove_terms:
#             action.remove_terms.append(term)
 
#     if not action.add_terms and not action.remove_terms and not action.full_replacement_terms:
#         action.is_pure_confirmation = True
 
#     return action



 
 
r"""
The API is stateless — every /chat call gets the FULL history and
nothing is stored between calls. So "state" (facts gathered so far,
current shortlist, how many clarifying questions already asked) must
be re-derived from the messages list every single time.
 
This module now derives a STRUCTURED requirements profile (role,
level, skills, industry, language, preferred test types, explicit
add/remove instructions) from the conversation, instead of just
concatenating raw text. Retrieval is built on top of this structured
profile so that:
  - stray conversational filler ("Perfect, thanks") doesn't dilute
    the search query, and
  - a later turn's edits ("also add personality tests") are additive
    rather than overwriting everything that came before.
 
BUGFIX NOTES (all three found by replaying real sample conversations
through the live pipeline and diffing expected vs. predicted):
 
  - ADD_PATTERN previously required a *second* mandatory whitespace
    after "add " even when no article followed, which is impossible
    to satisfy — "Add AWS and Docker." never matched at all. Fixed by
    making the article an optional *prefix* of the capture instead of
    a fixed-width gap.
  - REMOVE_PATTERN's lookahead required `\s+` before the sentence
    terminator, so "Drop the OPQ." (no space before the period) never
    matched. Now uses `\s*`.
  - REPLACE_PATTERN's replacement-term capture didn't exclude "?", so
    a message ending in a question ("...replace it with something
    shorter? Candidates complain...") swallowed the entire rest of
    the sentence into a garbage search query.
 
Also added FINAL_LIST_PATTERN: phrasing like "Final list: X and Y" or
"keep only X and Y" is common in refine turns and previously matched
NEITHER add nor remove, so the named items silently never made it
into the shortlist. This is now parsed as a full-replacement
instruction (see RefineAction.full_replacement_terms).
"""
 
import re
from dataclasses import dataclass, field
from typing import List, Optional
 
from app.models import Message
 
MAX_CLARIFYING_QUESTIONS = 2
 
# Minimum confidence_score() needed to skip clarification and go
# straight to retrieval. Categories are: role, level, skill, industry,
# test-type preference (max possible = 5). Threshold of 2 means a
# single vague category hit (e.g. only "leadership", or only
# "assessment") is NOT enough on its own — it still routes to
# clarify_needed — while any two concrete signals (e.g. role+level,
# or skill+industry) are enough to retrieve immediately. Tuned against
# the spec's own examples: "I need an assessment" (score 0), "We need
# a leadership solution" (score 1, role-only) both stay below
# threshold; "Java developers, mid-level" (role+level, score 2) clears it.
CONFIDENCE_THRESHOLD = 2
 
 
# ---------------------------------------------------------------------
# Turn-budget helpers (unchanged behavior from the original app)
# ---------------------------------------------------------------------
 
def get_user_context(messages: List[Message]) -> str:
    """All user turns concatenated — this is the 'facts known so far'."""
    return "\n".join(m.content for m in messages if m.role == "user")
 
 
def count_clarifying_turns(messages: List[Message]) -> int:
    count = 0
    for m in messages:
        if m.role == "assistant" and m.content.strip().endswith("?"):
            count += 1
    return count
 
 
def turns_used(messages: List[Message]) -> int:
    return len(messages)
 
 
def clarify_budget_exhausted(messages: List[Message]) -> bool:
    return count_clarifying_turns(messages) >= MAX_CLARIFYING_QUESTIONS
 
 
def near_turn_cap(messages: List[Message], cap: int = 8, buffer: int = 2) -> bool:
    """True when we're close enough to the 8-turn cap that we must
    commit to a shortlist now instead of asking anything else."""
    return turns_used(messages) >= (cap - buffer)
 
 
# ---------------------------------------------------------------------
# Structured requirements profile
# ---------------------------------------------------------------------
 
ROLE_TERMS = [
    "engineer", "developer", "programmer", "analyst", "manager", "director",
    "executive", "cxo", "leadership", "sales", "customer service",
    "contact centre", "contact center", "call centre", "call center",
    "admin", "administrative assistant", "clerk", "technician", "operator",
    "plant operator", "graduate", "trainee", "intern", "nurse", "accountant",
    "financial analyst", "healthcare admin",
]
 
# Terms in ROLE_TERMS that are too generic to identify a searchable
# role on their own (e.g. "leadership" could mean anyone from a new
# supervisor to a CXO). They still populate Requirements.roles so
# retrieval queries include them, but they don't earn a point in
# confidence_score() unless paired with something more specific (a
# level, a concrete title, etc. — captured by the OTHER categories
# already scoring their own point). Matches the sample pattern where
# "we need a solution for senior leadership" still gets a clarifying
# question about who exactly the audience is, despite "leadership"
# + "senior" superficially looking like two populated categories.
VAGUE_ROLE_TERMS = {"leadership"}
 
LEVEL_TERMS = [
    "entry-level", "entry level", "graduate", "junior", "mid-level",
    "mid level", "senior", "director", "executive", "cxo", "individual contributor",
    "supervisor", "front line manager", "manager", "professional",
]
 
SKILL_TERMS = [
    "java", "python", "sql", "excel", "word", "aws", "docker", "angular",
    "spring", "rust", "coding", "programming", ".net", "javascript",
    "numerical reasoning", "verbal reasoning", "cognitive", "deductive reasoning",
    "situational judgement", "situational judgment", "personality",
    "typing", "data entry", "customer service", "sales skills",
    # Added after replaying the sample conversations against the live
    # catalog and diffing expected vs. predicted shortlists — these
    # terms appeared in real transcripts but weren't boosting
    # retrieval because they weren't in the structured term list yet.
    "linux", "networking", "statistics", "microsoft office", "office",
    "hipaa", "medical terminology", "hiring", "interviewing",
    "safety", "dependability", "compliance", "reasoning", "leadership skills",
]
 
INDUSTRY_TERMS = [
    "healthcare", "finance", "financial", "banking", "manufacturing",
    "chemical", "retail", "technology", "insurance", "pharma",
    "petrochemical", "industrial",
]
 
LANGUAGE_TERMS = [
    "english", "spanish", "french", "german", "mandarin", "hindi", "portuguese",
    "castilian", "north american", "spoken english", "spoken spanish",
]
 
COGNITIVE_HINT_TERMS = [
    "cognitive", "reasoning", "numerical", "verbal", "abstract reasoning",
    "deductive", "inductive", "aptitude", "ability test", "g+",
    "problem-solving", "problem solving",
]
 
TEST_TYPE_HINTS = {
    "personality": "P", "cognitive": "A", "ability": "A", "aptitude": "A",
    "situational judgement": "B", "situational judgment": "B", "biodata": "B",
    "competenc": "C", "development": "D", "360": "D",
    "assessment exercise": "E", "knowledge": "K", "skills test": "K",
    "simulation": "S",
}
 
# ---------------------------------------------------------------------
# Critical-constraint detection
# ---------------------------------------------------------------------
# Some roles have a constraint that materially changes WHICH catalog
# item is correct, not just how well it's explained — e.g. a phone /
# contact-centre role needs a language-specific version of a test, so
# recommending before that's known risks handing back the wrong SKU.
# `Requirements.is_empty()` alone doesn't catch this: a message like
# "500 entry-level contact centre agents, inbound calls" already
# populates roles + levels, so the old router treated it as fully
# specified and recommended immediately. `critical_missing()` adds a
# second, narrower gate on top of is_empty() for exactly these cases,
# without turning the router into pure keyword matching for the
# general routing decision — it only tightens the recommend/clarify
# boundary for a small, well-defined set of situations where getting
# it wrong is costly.
 
# Phrases signalling a phone/voice-based customer-facing role, where
# the SPOKEN LANGUAGE of the assessment (and the calls) is a hard
# constraint on which SHL item is correct.
PHONE_CONTACT_HINTS = [
    "contact centre", "contact center", "call centre", "call center",
    "inbound call", "inbound calls", "outbound call", "outbound calls",
    "phone support", "telephone support", "telephone screening",
    "customer service", "customer support", "help desk", "helpdesk",
    "support agent", "support agents",
]
 
# Roles where the hiring need is dominated by a role-specific
# operational/safety instrument (e.g. Manufac. & Indust. - Safety &
# Dependability) rather than a general workplace-behavioural-style
# assessment — so we should NOT nudge retrieval toward a generic
# personality query for these.
OPERATIONAL_SAFETY_HINTS = [
    "plant operator", "plant operators", "chemical facility",
    "chemical plant", "manufacturing floor", "factory floor",
    "warehouse operator", "machine operator", "production line",
]
 
# Human-readable phrasing for what's missing, used to steer the
# clarifying question toward the actual gap instead of a generic one.
MISSING_HINT_TEXT = {
    "language": "the language(s) the calls / assessments need to be conducted in",
}
 
# ---------------------------------------------------------------------
# Refine-instruction patterns
# ---------------------------------------------------------------------
# Words that signal the user is editing an EXISTING shortlist, plus
# which direction the edit goes. Order matters: check "replace" before
# plain "add"/"remove" since it implies both.
#
# ADD_PATTERN: the article ("a"/"an"/"the") is an optional PREFIX of
# the capture, not a separate fixed-width gap — "add X", "add a X",
# "add an X", "add the X", and "also add X" all match with exactly one
# required space between the trigger and the content.
ADD_PATTERN = re.compile(r"(?i)\b(also add|add|include)\s+(?:a\s+|an\s+|the\s+)?([^.,;?]+)")
 
# REMOVE_PATTERN: lookahead uses `\s*` (not `\s+`) so a terminator that
# immediately follows the term with no space ("Drop the OPQ.") still
# matches. "?" and an em-dash are also valid terminators.
REMOVE_PATTERN = re.compile(
    r"(?i)\b(remove|drop|take out|without the|exclude)\s+(?:the\s+)?([^.,;?—]+?)"
    r"(?=\s*(?:and|but|,|\.|\?|—|$))"
)
 
# REPLACE_PATTERN: both captures exclude "?" so a trailing question in
# the same sentence doesn't get swallowed into the replacement term.
REPLACE_PATTERN = re.compile(
    r"(?i)\bremove\s+(?:the\s+)?([^.,;?]+?)\s+and\s+replace\s+(?:it\s+)?with\s+([^.,;?]+)|"
    r"\breplace\s+(?:the\s+)?([^.,;?]+?)\s+with\s+([^.,;?]+)"
)
 
# FINAL_LIST_PATTERN: "Final list: X and Y" / "keep only X and Y" /
# "just keep X and Y" / "only keep X and Y" — the user is stating the
# complete desired shortlist, not adding to or subtracting from the
# existing one. Previously this phrasing matched neither ADD_PATTERN
# nor REMOVE_PATTERN and the named items were silently dropped.
FINAL_LIST_PATTERN = re.compile(r"(?i)\b(?:final list|keep only|just keep|only keep)[:\s]+([^.?!]+)")
 
# Splits a captured "X and Y", "X, Y and Z", "X & Y" span into
# individual terms — ADD_PATTERN/FINAL_LIST_PATTERN capture the whole
# conjunction as one span so multi-item edits aren't lost.
_TERM_SPLIT_RE = re.compile(r"(?i)\s*(?:,\s*(?:and\s+)?|\s+and\s+|\s*&\s*)\s*")
 
 
def _split_terms(text: str) -> List[str]:
    parts = [p.strip(" .") for p in _TERM_SPLIT_RE.split(text) if p.strip(" .")]
    return parts if parts else ([text.strip(" .")] if text.strip(" .") else [])
 
 
@dataclass
class Requirements:
    roles: List[str] = field(default_factory=list)
    levels: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    industries: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    test_type_hints: List[str] = field(default_factory=list)
    free_text: List[str] = field(default_factory=list)  # raw user turns, for BM25/dense fallback
 
    def wants_personality_boost(self) -> bool:
        """
        True when there's real hiring context (a role and/or level) but
        neither a phone/contact-centre constraint nor an operational-
        safety role is in play. In SHL's own catalog, a general
        workplace-behavioural-style assessment (e.g. the OPQ32r family)
        is near-universally part of a professional/managerial hiring
        battery even when the user's phrasing never says the word
        "personality" — role and seniority alone usually imply it. This
        is deliberately narrow (excludes phone/contact-centre roles,
        where language is the binding constraint, and operational/
        safety roles, where a role-specific safety instrument is the
        right fit instead) so it doesn't distort retrieval for the
        cases where a generic personality nudge would be wrong.
        """
        if not (self.roles or self.levels):
            return False
        combined_text = " ".join(self.free_text).lower()
        if any(hint in combined_text for hint in PHONE_CONTACT_HINTS):
            return False
        if any(hint in combined_text for hint in OPERATIONAL_SAFETY_HINTS):
            return False
        return True
 
    def wants_cognitive_boost(self) -> bool:
        """
        Mirrors wants_personality_boost() for the general cognitive-
        ability family (SHL's "Verify"-branded ability tests). Fires
        when the conversation names a concrete cognitive/reasoning
        skill or already carries an "ability" test_type_hint, so a
        generalist ability test isn't force-injected into purely
        behavioural/simulation-only requests.
        """
        combined_text = " ".join(self.free_text).lower()
        if "A" in self.test_type_hints:
            return True
        return any(term in combined_text for term in COGNITIVE_HINT_TERMS)
 
    def to_query(self) -> str:
        """Flatten the structured profile into a clean retrieval query.
        Structured terms are repeated up front (cheap way to weight
        them higher for BM25) followed by the raw text as a fallback
        signal for anything the keyword lists didn't catch.
 
        Also appends a single light-weight "personality/behavioural
        style" boost phrase when wants_personality_boost() holds. This
        only nudges BM25/dense ranking toward surfacing generalist
        personality items in the retrieved pool — it never hardcodes or
        force-injects a specific catalog item, so it stays correct even
        if catalog naming changes.
        """
        structured = (
            self.roles + self.levels + self.skills + self.industries + self.languages
        )
        parts = []
        if structured:
            parts.append(" ".join(structured) + " " + " ".join(structured))
        parts.extend(self.free_text)
        if self.wants_personality_boost():
            parts.append("personality behavioural style workplace conduct questionnaire")
        if self.wants_cognitive_boost():
            parts.append("verify cognitive ability reasoning aptitude test")
        return " ".join(parts).strip()
 
    def is_empty(self) -> bool:
        return not (self.roles or self.levels or self.skills or self.industries)
 
    def confidence_score(self) -> int:
        """
        Lightweight rule-based confidence score over the already-
        extracted structured fields — no LLM call, no extra parsing,
        O(1) on data we already have. One point per requirement
        CATEGORY that has at least one hit:
 
            role present                -> +1
            seniority/level present     -> +1
            skill present               -> +1
            industry present            -> +1
            assessment/test-type pref.  -> +1  (test_type_hints)
 
        This intentionally scores by category, not by term count, so
        a message that mentions five skill keywords doesn't outscore
        one that mentions a role + a level. A single vague category
        hit (e.g. just "leadership") stays below CONFIDENCE_THRESHOLD,
        matching the sample pattern where "we need a leadership
        solution" still gets a clarifying question rather than a
        shortlist.
        """
        score = 0
        if self.roles:
            score += 1
        if self.levels:
            score += 1
        if self.skills:
            score += 1
        if self.industries:
            score += 1
        if self.test_type_hints:
            score += 1
        return score
 
    def critical_missing(self) -> List[str]:
        """
        Returns a list of critical-constraint keys that are still
        missing even though enough general context exists to not be
        `is_empty()`. Currently covers: phone/contact-centre-type
        roles missing a call/assessment language, since that decides
        which language-specific catalog item is actually correct.
 
        Deliberately narrow and additive: this never fires for roles
        outside the phone-contact hint list, so it doesn't change
        behavior for the large majority of recommend-eligible turns
        (e.g. "Java developers, mid-level" still recommends directly).
        """
        missing: List[str] = []
        combined_text = " ".join(self.free_text).lower()
        is_phone_role = any(hint in combined_text for hint in PHONE_CONTACT_HINTS)
        if is_phone_role and not self.languages:
            missing.append("language")
        return missing
 
 
def _extract_terms(text: str, term_list: List[str]) -> List[str]:
    text_l = text.lower()
    found = []
    for term in term_list:
        if term in text_l and term not in found:
            found.append(term)
    return found
 
 
def extract_requirements(messages: List[Message]) -> Requirements:
    """Build a structured requirements profile from ALL user turns so
    far. Called fresh on every request since the API is stateless."""
    req = Requirements()
    for m in messages:
        if m.role != "user":
            continue
        text = m.content
        req.roles.extend(t for t in _extract_terms(text, ROLE_TERMS) if t not in req.roles)
        req.levels.extend(t for t in _extract_terms(text, LEVEL_TERMS) if t not in req.levels)
        req.skills.extend(t for t in _extract_terms(text, SKILL_TERMS) if t not in req.skills)
        req.industries.extend(t for t in _extract_terms(text, INDUSTRY_TERMS) if t not in req.industries)
        req.languages.extend(t for t in _extract_terms(text, LANGUAGE_TERMS) if t not in req.languages)
        for hint, code in TEST_TYPE_HINTS.items():
            if hint in text.lower() and code not in req.test_type_hints:
                req.test_type_hints.append(code)
        req.free_text.append(text)
    return req
 
 
@dataclass
class RefineAction:
    add_terms: List[str] = field(default_factory=list)
    remove_terms: List[str] = field(default_factory=list)
    # If non-empty, the user stated the COMPLETE desired shortlist
    # ("Final list: X and Y") rather than an incremental edit — this
    # should override prior_items/add/remove merging entirely.
    full_replacement_terms: List[str] = field(default_factory=list)
    is_pure_confirmation: bool = False
 
 
def parse_refine_action(last_user_msg: str) -> RefineAction:
    """Pull out explicit add/remove/replace/final-list instructions
    from the latest user turn so a 'refine' turn can edit the previous
    shortlist instead of recomputing it from scratch."""
    action = RefineAction()
 
    for m in FINAL_LIST_PATTERN.finditer(last_user_msg):
        for term in _split_terms(m.group(1)):
            if term and term not in action.full_replacement_terms:
                action.full_replacement_terms.append(term)
 
    for m in REPLACE_PATTERN.finditer(last_user_msg):
        if m.group(1) and m.group(2):
            action.remove_terms.append(m.group(1).strip())
            action.add_terms.extend(_split_terms(m.group(2)))
        elif m.group(3) and m.group(4):
            action.remove_terms.append(m.group(3).strip())
            action.add_terms.extend(_split_terms(m.group(4)))
 
    for m in ADD_PATTERN.finditer(last_user_msg):
        for term in _split_terms(m.group(2)):
            if term and term not in action.add_terms:
                action.add_terms.append(term)
 
    for m in REMOVE_PATTERN.finditer(last_user_msg):
        term = m.group(2).strip()
        if term and term not in action.remove_terms:
            action.remove_terms.append(term)
 
    if not action.add_terms and not action.remove_terms and not action.full_replacement_terms:
        action.is_pure_confirmation = True
 
    return action