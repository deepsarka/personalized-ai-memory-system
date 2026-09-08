"""
Stage 2 — LLM-based extraction (Gemini version).

Responsibilities:
1. Extract candidate preference/behavior facts using Gemini.
2. Validate the model output against the application's fixed schema.
3. Normalize correction/exclusion semantics deterministically.
4. Apply deterministic sensitivity/policy filtering.
5. Build ExtractedFact objects for Stage 3.

Important production rule:
The LLM proposes facts; application code owns the final semantics.
In particular, correction language is normalized after extraction so that
phrases such as:

    "I no longer prefer energetic music"

do not accidentally become:

    correction -> prefers_tempo = energetic

which would create another current "energetic" fact.

Instead, the correction is converted into an exclusion:

    excludes_tempo = energetic

or, when the schema does not contain a dedicated exclusion predicate,
the existing preference predicate is retained with fact_type=correction
and the graph layer can supersede the old fact.

The current graph schema supports excludes_mood / excludes_genre /
excludes_artist but does not have excludes_tempo. Therefore tempo
corrections are represented as:

    predicate = prefers_tempo
    object_value = energetic
    fact_type = correction

ONLY when the user's message actually means "replace energetic with X".

For explicit "no longer like X" statements, the extractor instead uses
general_exclusion when there is no dedicated exclusion predicate.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from processing.schemas import (
    ExtractedFact,
    FactSource,
    FactType,
    PolicyClass,
    ProcessingResult,
)
from processing.sensitivity import (
    classify_sensitivity,
    is_safe_to_persist,
    validate_required_fields,
)

logger = logging.getLogger("processing.extractor")


_ALLOWED_PREDICATES = {
    "prefers_mood",
    "excludes_mood",
    "prefers_genre",
    "excludes_genre",
    "prefers_artist",
    "excludes_artist",
    "prefers_time_of_day",
    "prefers_activity_context",
    "prefers_tempo",
    "prefers_vocal_style",
    "general_preference",
    "general_exclusion",
}


_EXTRACTION_PROMPT = """You extract structured preference/behavior facts from a user's message for a memory system.

Given the raw text, identify 0-3 distinct facts.

IMPORTANT SEMANTIC RULES:

1. A positive preference:
   "I like calm music"
   -> preference / prefers_mood / calm

2. A dislike or explicit rejection:
   "I don't like energetic music"
   -> exclusion
   -> use the matching excludes_* predicate when available.

3. A correction/replacement:
   "I used to prefer energetic music, but now I prefer calm music"
   -> DO NOT create a current correction whose object_value is "energetic".
   The correction must represent the NEW value:
   -> correction / prefers_mood / calm

4. A statement that something is no longer preferred:
   "I no longer prefer energetic music"
   -> exclusion semantics.
   If a dedicated excludes_* predicate exists, use it.
   Otherwise use general_exclusion.
   DO NOT output:
   correction / prefers_tempo / energetic
   because that would incorrectly recreate energetic as the current preference.

5. When a sentence contains both an old preference and a new preference:
   "I no longer prefer energetic music. I prefer calm music when I work out"
   extract the semantic result:
   - energetic is rejected/no longer preferred
   - calm is preferred
   - working out is the activity context

6. Corrections should describe the replacement/new truth, not merely repeat
   the old value being corrected.

Respond with a JSON array.

Each item MUST have exactly these fields:
- "predicate": MUST be one of this exact fixed list:
  ["prefers_mood", "excludes_mood",
   "prefers_genre", "excludes_genre",
   "prefers_artist", "excludes_artist",
   "prefers_time_of_day",
   "prefers_activity_context",
   "prefers_tempo",
   "prefers_vocal_style",
   "general_preference", "general_exclusion"]

- "object_value": the value, short and specific.
- "fact_type": one of:
  "preference", "exclusion", "behavior", "correction", "deletion_request"

- "confidence": float 0.0-1.0
- "source": one of:
  "explicit", "inferred", "correction"

If nothing is extractable, return [].

Text: "{raw_text}"
"""


_RETRYABLE_STATUS_CODES = {429, 503}


class FactExtractor:
    def __init__(self, api_key: str | None = None):
        self.client = genai.Client(
            api_key=api_key or os.getenv("GEMINI_API_KEY")
        )
        self.model = "gemini-3.5-flash"

    def extract(
        self,
        raw_text: str,
        subject_id: str,
        source_event_idempotency_key: str,
        content_entity_id: str | None = None,
    ) -> ProcessingResult:

        result = ProcessingResult(
            source_event_idempotency_key=source_event_idempotency_key
        )

        if not raw_text or not raw_text.strip():
            result.rejected_reasons.append("empty_raw_text")
            return result

        try:
            candidates = self._call_llm(raw_text)

            if not isinstance(candidates, list):
                logger.warning(
                    "Gemini returned non-list extraction result; rejecting output"
                )
                result.rejected_reasons.append("invalid_llm_output")
                return result

            # Deterministic semantic normalization happens AFTER the LLM.
            candidates = self._normalize_candidates(candidates, raw_text)

        except Exception as e:
            logger.error(
                f"LLM extraction failed for {source_event_idempotency_key}: {e}"
            )
            result.rejected_reasons.append(
                f"llm_extraction_failed:{type(e).__name__}"
            )
            return result

        for i, candidate in enumerate(candidates):
            fact = self._validate_and_build(
                candidate,
                subject_id,
                source_event_idempotency_key,
                raw_text,
                content_entity_id,
                i,
            )

            if fact is None:
                continue

            result.accepted_facts.append(fact)

        if not result.accepted_facts and not result.rejected_reasons:
            result.rejected_reasons.append("no_extractable_facts")

        return result

    def _call_llm(
        self,
        raw_text: str,
        max_retries: int = 3,
    ) -> list[dict]:

        last_error = None

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=_EXTRACTION_PROMPT.format(raw_text=raw_text),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=4096,
                        temperature=0.2,
                    ),
                )

                text = (response.text or "").strip()

                text = re.sub(
                    r"^```(?:json)?\s*",
                    "",
                    text,
                    flags=re.IGNORECASE,
                )
                text = re.sub(
                    r"\s*```$",
                    "",
                    text,
                )

                parsed = json.loads(text)

                if not isinstance(parsed, list):
                    raise ValueError(
                        "Gemini extraction output must be a JSON array"
                    )

                return parsed

            except genai_errors.APIError as e:
                last_error = e

                if (
                    any(
                        str(code) in str(e)
                        for code in _RETRYABLE_STATUS_CODES
                    )
                    and attempt < max_retries - 1
                ):
                    wait_time = 7 * (attempt + 1)

                    logger.warning(
                        f"Extractor API error ({e}). "
                        f"Retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{max_retries})..."
                    )

                    time.sleep(wait_time)
                    continue

                raise

            except json.JSONDecodeError:
                logger.error(
                    f"Gemini returned non-JSON text: {text[:300]!r}"
                )
                raise

            except Exception:
                raise

        if last_error:
            raise last_error

        return []

    # ------------------------------------------------------------------
    # Deterministic semantic normalization
    # ------------------------------------------------------------------

    def _normalize_candidates(
        self,
        candidates: list[dict],
        raw_text: str,
    ) -> list[dict]:
        """
        Normalize model output before validation.

        The model is not trusted as the sole authority for correction
        semantics. We use lightweight deterministic checks for explicit
        "no longer / don't / dislike / stop preferring" language.

        This prevents the dangerous case where:

            "I no longer prefer energetic music"

        becomes:

            correction + prefers_tempo + energetic

        which would leave energetic as the current fact.

        We deliberately keep this conservative. We do not attempt to
        implement a complete NLP system here.
        """

        normalized: list[dict] = []

        lowered = raw_text.lower().strip()

        explicit_rejection = bool(
            re.search(
                r"\b("
                r"no longer|"
                r"don't like|"
                r"do not like|"
                r"doesn't like|"
                r"does not like|"
                r"dislike|"
                r"dislikes|"
                r"stop preferring|"
                r"stopped preferring|"
                r"not into|"
                r"hate"
                r")\b",
                lowered,
            )
        )

        for candidate in candidates:
            if not isinstance(candidate, dict):
                logger.warning(
                    "Ignoring malformed Gemini candidate: %r",
                    candidate,
                )
                continue

            item = dict(candidate)

            predicate = item.get("predicate", "")
            object_value = str(item.get("object_value", "")).strip()
            fact_type = item.get("fact_type", "preference")

            # ----------------------------------------------------------
            # Critical correction guard
            # ----------------------------------------------------------
            #
            # If the user's text explicitly rejects something and Gemini
            # labels that same old value as a correction, do NOT allow it
            # to remain a current correction.
            #
            # Example:
            #   "I no longer prefer energetic music"
            #
            # Bad model output:
            #   correction / prefers_tempo / energetic
            #
            # We convert it to exclusion semantics.
            #
            if (
                explicit_rejection
                and fact_type == "correction"
                and object_value
            ):
                exclusion_predicate = self._to_exclusion_predicate(
                    predicate
                )

                item["predicate"] = exclusion_predicate
                item["fact_type"] = "exclusion"
                item["source"] = "correction"

                logger.info(
                    "Normalized rejection correction: "
                    "%s/%s -> %s/%s",
                    predicate,
                    object_value,
                    exclusion_predicate,
                    object_value,
                )

            # ----------------------------------------------------------
            # Second guard:
            # explicit rejection + positive preference
            #
            # Sometimes the model may ignore "no longer" completely and
            # return:
            #
            #   preference / prefers_tempo / energetic
            #
            # That is also unsafe.
            # ----------------------------------------------------------
            elif (
                explicit_rejection
                and fact_type == "preference"
                and object_value
                and self._object_is_explicitly_rejected(
                    raw_text,
                    object_value,
                )
            ):
                exclusion_predicate = self._to_exclusion_predicate(
                    predicate
                )

                item["predicate"] = exclusion_predicate
                item["fact_type"] = "exclusion"
                item["source"] = "correction"

                logger.info(
                    "Normalized explicit rejection preference: "
                    "%s/%s -> %s/%s",
                    predicate,
                    object_value,
                    exclusion_predicate,
                    object_value,
                )

            normalized.append(item)

        return normalized

    @staticmethod
    def _to_exclusion_predicate(predicate: str) -> str:
        """
        Map a preference predicate to its corresponding exclusion
        predicate where the schema supports one.

        Tempo/activity/time/vocal-style currently have no dedicated
        excludes_* predicate, so they fall back to general_exclusion.
        """

        mapping = {
            "prefers_mood": "excludes_mood",
            "prefers_genre": "excludes_genre",
            "prefers_artist": "excludes_artist",
        }

        return mapping.get(predicate, "general_exclusion")

    @staticmethod
    def _object_is_explicitly_rejected(
        raw_text: str,
        object_value: str,
    ) -> bool:
        """
        Conservative check that the candidate value appears near an
        explicit rejection phrase.

        This is intentionally simple. It is a safety guard against
        accidentally persisting an explicitly rejected value as a
        positive preference.
        """

        text = raw_text.lower()
        value = object_value.lower().strip()

        if not value:
            return False

        rejection_patterns = [
            rf"(no longer|don't|do not|doesn't|does not|dislike|hate)"
            rf".{{0,80}}\b{re.escape(value)}\b",

            rf"\b{re.escape(value)}\b.{{0,80}}"
            rf"(no longer|don't|do not|doesn't|does not|dislike|hate)",
        ]

        return any(
            re.search(pattern, text, flags=re.IGNORECASE)
            for pattern in rejection_patterns
        )

    # ------------------------------------------------------------------
    # Validation + ExtractedFact construction
    # ------------------------------------------------------------------

    def _validate_and_build(
        self,
        candidate: dict,
        subject_id: str,
        source_event_idempotency_key: str,
        raw_text: str,
        content_entity_id: str | None,
        index: int,
    ) -> ExtractedFact | None:

        predicate = candidate.get("predicate", "")
        object_value = str(candidate.get("object_value", "")).strip()

        if predicate not in _ALLOWED_PREDICATES:
            fact_type_hint = candidate.get(
                "fact_type",
                "preference",
            )

            coerced = (
                "general_exclusion"
                if fact_type_hint == "exclusion"
                else "general_preference"
            )

            logger.warning(
                f"Candidate {index} used off-vocabulary predicate "
                f"{predicate!r}, coercing to {coerced!r}"
            )

            predicate = coerced

        structural_errors = validate_required_fields(
            subject_id,
            predicate,
            object_value,
        )

        if structural_errors:
            logger.warning(
                f"Rejected candidate {index}: {structural_errors}"
            )
            return None

        policy_class = classify_sensitivity(
            raw_text,
            predicate,
            object_value,
        )

        if not is_safe_to_persist(policy_class):
            logger.info(
                f"Filtered sensitive candidate {index} "
                f"(policy_class={policy_class})"
            )
            return None

        try:
            fact_type = FactType(
                candidate.get(
                    "fact_type",
                    "preference",
                )
            )

            source = FactSource(
                candidate.get(
                    "source",
                    "explicit",
                )
            )

        except ValueError as e:
            logger.warning(
                f"Rejected candidate {index}: invalid enum value ({e})"
            )
            return None

        try:
            confidence = float(
                candidate.get("confidence", 0.5)
            )
        except (TypeError, ValueError):
            confidence = 0.5

        confidence = max(
            0.0,
            min(1.0, confidence),
        )

        if (
            source == FactSource.INFERRED
            and policy_class == PolicyClass.STANDARD
        ):
            policy_class = PolicyClass.SHORT_LIVED

        return ExtractedFact(
            fact_id=f"{source_event_idempotency_key}-fact{index}",
            subject_id=subject_id,
            source=source,
            confidence=confidence,
            policy_class=policy_class,
            fact_type=fact_type,
            predicate=predicate,
            object_value=object_value,
            content_entity_id=content_entity_id,
            valid_from=datetime.now(timezone.utc),
            source_event_idempotency_key=source_event_idempotency_key,
            raw_text=raw_text,
        )