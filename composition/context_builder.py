"""
Stage 6 — Memory Context Builder.

Converts the governed MemoryPackage into concise natural-language
memory context for the LLM.

Important:
- Only governed/approved memories reach this layer.
- MemoryPackage is the source of truth.
- No raw RetrievalResult should be passed here.
- Memory is treated as data, not instructions.
"""

from composition.memory_models import MemoryPackage


def _render_memory(memory) -> str:
    """
    Convert one MemoryItem into a natural-language sentence.

    This keeps the LLM prompt readable while preserving the
    meaning of the structured memory.
    """

    predicate = memory.predicate
    value = memory.object_value

    templates = {
        "prefers_genre": f"User prefers {value} genre music.",
        "prefers_activity_context": (
            f"User listens to music while {value}."
        ),
        "prefers_vocal_style": (
            f"User prefers {value} music."
        ),
        "prefers_time_of_day": (
            f"User tends to listen to music in the {value}."
        ),
        "prefers_mood": (
            f"User prefers {value} music."
        ),
        "excludes_genre": (
            f"User does not want {value} music recommended."
        ),
    }

    if predicate in templates:
        return templates[predicate]

    # Generic fallback for predicates not explicitly mapped.
    return f"User {predicate.replace('_', ' ')}: {value}."


def build_memory_context(
    memory_package: MemoryPackage,
    max_facts: int = 5,
) -> str:
    """
    Convert a governed MemoryPackage into LLM-ready memory context.

    The MemoryPackage already contains only memories that survived:
        Retrieval → Reranking → Governance → Composition

    Therefore this function does not perform additional filtering.
    """

    if not memory_package.memory_available:
        return "No relevant memories found for this user."

    if not memory_package.memories:
        return "No relevant memories found for this user."

    rendered = []

    for memory in memory_package.memories[:max_facts]:
        sentence = _render_memory(memory)

        if sentence not in rendered:
            rendered.append(sentence)

    if not rendered:
        return "No relevant memories found for this user."

    return "\n".join(
        f"- {sentence}"
        for sentence in rendered
    )