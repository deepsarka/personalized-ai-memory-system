from datetime import datetime, timezone


class MemoryReranker:

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    def rerank(self, facts: list, query: str) -> list:
        """
        Rerank retrieved memories using:
        - semantic similarity
        - source explicitness
        - correction precedence
        - recency
        """

        scored = []

        for fact in facts:

            similarity = float(
                getattr(fact, "similarity", 0.0) or 0.0
            )

            source = (
                getattr(fact, "source", "") or ""
            ).lower()

            score = similarity
            reasons = [
                f"semantic similarity={similarity:.3f}"
            ]

            # Explicit user statements are stronger
            if source == "explicit":
                score += 0.15
                reasons.append("explicit user statement")

            # Corrections have highest precedence
            elif source == "correction":
                score += 0.25
                reasons.append("explicit user correction")

            # Inferred memories get no bonus
            elif source == "inferred":
                reasons.append("inferred memory")

            # Recency bonus
            valid_from = getattr(fact, "valid_from", None)

            if valid_from:
                try:
                    timestamp = datetime.fromisoformat(
                        valid_from.replace("Z", "+00:00")
                    )

                    age_days = (
                        datetime.now(timezone.utc) - timestamp
                    ).total_seconds() / 86400

                    if age_days <= 1:
                        score += 0.10
                        reasons.append("very recent")

                    elif age_days <= 7:
                        score += 0.05
                        reasons.append("recent")

                except (ValueError, TypeError):
                    pass

            scored.append(
                (
                    score,
                    fact,
                    reasons,
                )
            )

        # Highest score first
        scored.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return [
            (fact, score, reasons)
            for score, fact, reasons
            in scored[:self.max_results]
        ]