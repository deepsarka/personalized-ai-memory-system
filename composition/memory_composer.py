from composition.memory_models import (
    MemoryItem,
    MemoryPackage,
)


class MemoryComposer:

    def __init__(self, max_facts: int = 5):
        self.max_facts = max_facts

    def compose(
        self,
        subject_id: str,
        query: str,
        approved: list,
    ) -> MemoryPackage:

        memories = []

        for fact, score, reasons in approved[:self.max_facts]:

            item = MemoryItem(
                  fact_id=fact.fact_id,
                  subject_id=fact.subject_id,
                  fact_type=getattr(fact.fact_type, "value", fact.fact_type),  # Ensure string value
                  predicate=fact.predicate,
                  object_value=fact.object_value,
                  source=getattr(fact.source, "value", fact.source),           # Ensure string value
                  policy_class=getattr(fact.policy_class, "value", fact.policy_class),
                  valid_from=str(fact.valid_from) if fact.valid_from else None,
                  valid_until=str(fact.valid_until) if getattr(fact, "valid_until", None) else None,
                  relevance_score=score,
)

            memories.append(item)

        if not memories:

            return MemoryPackage(
                subject_id=subject_id,
                query=query,
                memories=[],
                memory_available=False,
                fallback_reason="No relevant governed memories available.",
            )

        return MemoryPackage(
            subject_id=subject_id,
            query=query,
            memories=memories,
            memory_available=True,
        )