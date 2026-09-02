from datetime import datetime, timezone


class MemoryGovernance:

    def filter(
        self,
        subject_id: str,
        facts: list,
    ) -> tuple[list, list]:

        approved = []
        rejected = []

        for fact, score, reasons in facts:

            # --------------------------------------------------
            # 1. Subject isolation
            # --------------------------------------------------

            fact_subject = getattr(
                fact,
                "subject_id",
                None,
            )

            if fact_subject != subject_id:
                rejected.append((fact, "subject_mismatch"))
                continue

            # --------------------------------------------------
            # 2. Policy check
            # --------------------------------------------------

            policy_class = (
                getattr(fact, "policy_class", "") or ""
            ).lower()

            if policy_class in {
                "blocked",
                "prohibited",
                "sensitive_blocked",
            }:
                rejected.append((fact, "policy_blocked"))
                continue

            # --------------------------------------------------
            # 3. Temporal validity
            # --------------------------------------------------

            valid_until = getattr(
                fact,
                "valid_until",
                None,
            )

            if valid_until:
                try:
                    val_str = (
                        valid_until.isoformat()
                        if isinstance(valid_until, datetime)
                        else str(valid_until)
                    )
                    expiry = datetime.fromisoformat(
                        val_str.replace("Z", "+00:00")
                    )
                    if expiry <= datetime.now(timezone.utc):
                        rejected.append((fact, "expired"))
                        continue
                except (ValueError, TypeError):
                    pass

            # --------------------------------------------------
            # 4. Minimum relevance threshold
            # --------------------------------------------------

            if score < 0.20:
                rejected.append((fact, "low_relevance"))
                continue

            approved.append(
                (
                    fact,
                    score,
                    reasons,
                )
            )

        return approved, rejected