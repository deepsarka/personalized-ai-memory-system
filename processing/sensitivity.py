"""
Stage 2 — deterministic sensitivity & minimization validator.

Per your spec: "Deterministic validators reject unsupported or unsafe fields."
This is intentionally NOT an LLM call — sensitive-content filtering needs to
be auditable and reproducible, not subject to model variance. Keyword/category
based rules are crude but explainable, which is what a governed pilot needs.
"""

import re
from processing.schemas import PolicyClass

# Categories that push a fact to RESTRICTED (filtered out) rather than stored.
# Deliberately broad/conservative for a pilot — false positives (over-filtering)
# are the safe failure mode here, not false negatives.
#
# NOTE: stem-style keywords (depress, pregnan, diagnos, politic) use a
# trailing \w* instead of a bare \b. Without it, \bdepress\b does NOT match
# "depression" — the trailing \b requires a word boundary immediately after
# "depress", but "ion" continues the word, so there's no boundary there.
# This was silently letting real matches (e.g. "depression") through.
_SENSITIVE_PATTERNS = [
    r"\b(health|medical|diagnos\w*|therapy|medication|illness|disease)\b",
    r"\b(pregnan\w*|mental health|depress\w*|anxiety|addiction)\b",
    r"\b(religion|religious|politic\w*|sexual orientation|gender identity)\b",
    r"\b(income|salary|debt|credit score|bank account)\b",
    r"\b(ssn|social security|passport|driver'?s? licen[sc]e)\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SENSITIVE_PATTERNS]


def classify_sensitivity(raw_text: str | None, predicate: str, object_value: str) -> PolicyClass:
    """
    Deterministic pass over the fact's text. Returns RESTRICTED if any
    sensitive-category pattern matches; otherwise STANDARD.
    Momentary/behavioral signals (not explicit statements) get SHORT_LIVED
    by the caller, not here — this function only handles sensitivity.
    """
    text_to_check = " ".join(filter(None, [raw_text, predicate, object_value]))
    for pattern in _COMPILED:
        if pattern.search(text_to_check):
            return PolicyClass.RESTRICTED
    return PolicyClass.STANDARD


def is_safe_to_persist(policy_class: PolicyClass) -> bool:
    """Single choke point for the 'don't persist sensitive/ambiguous inferences' rule."""
    return policy_class != PolicyClass.RESTRICTED


def validate_required_fields(subject_id: str, predicate: str, object_value: str) -> list[str]:
    """
    Deterministic structural validation. Returns a list of rejection reasons
    (empty list = valid). Runs before anything is considered for the graph.
    """
    reasons = []
    if not subject_id or not subject_id.strip():
        reasons.append("missing_subject_id")
    if not predicate or not predicate.strip():
        reasons.append("missing_predicate")
    if not object_value or not object_value.strip():
        reasons.append("missing_object_value")
    if predicate and len(predicate) > 100:
        reasons.append("predicate_too_long")
    if object_value and len(object_value) > 500:
        reasons.append("object_value_too_long")
    return reasons