from composition.governance import MemoryGovernance
from composition.memory_composer import MemoryComposer


# ============================================================
# Helper
# ============================================================

class FakeFact:
    def __init__(
        self,
        fact_id,
        subject_id,
        predicate="prefers_genre",
        object_value="classical",
        fact_type="preference",
        policy_class="standard",
        valid_until=None,
        source="explicit",
        valid_from=None,
    ):
        from datetime import datetime, timezone

        self.fact_id = fact_id
        self.subject_id = subject_id
        self.predicate = predicate
        self.object_value = object_value
        self.fact_type = fact_type
        self.policy_class = policy_class
        self.valid_until = valid_until
        self.source = source
        self.valid_from = valid_from or datetime.now(timezone.utc)


# ============================================================
# TEST 1
# Subject isolation
# ============================================================

def test_subject_isolation():
    """
    A memory belonging to user-002 must never be approved
    for user-001.
    """

    governance = MemoryGovernance()

    user_002_fact = FakeFact(
        fact_id="test-fact-001",
        subject_id="test-user-002",
    )

    candidates = [
        (
            user_002_fact,
            0.90,
            [],
        )
    ]

    approved, rejected = governance.filter(
        "test-user-001",
        candidates,
    )

    assert approved == []

    assert len(rejected) == 1
    assert rejected[0][0].fact_id == "test-fact-001"
    assert rejected[0][1] == "subject_mismatch"


# ============================================================
# TEST 2
# Correct subject memory is allowed
# ============================================================

def test_correct_subject_memory_allowed():
    """
    A user should be able to retrieve/use their own memory.
    """

    governance = MemoryGovernance()

    fact = FakeFact(
        fact_id="test-fact-002",
        subject_id="test-user-002",
    )

    candidates = [
        (
            fact,
            0.90,
            [],
        )
    ]

    approved, rejected = governance.filter(
        "test-user-002",
        candidates,
    )

    assert len(approved) == 1
    assert approved[0][0].fact_id == "test-fact-002"

    assert rejected == []


# ============================================================
# TEST 3
# Composer uses approved memories
# ============================================================

def test_composer_uses_approved_memories():
    """
    MemoryComposer should compose only the memories
    explicitly passed as approved.
    """

    composer = MemoryComposer()

    fact = FakeFact(
        fact_id="rock-fact-001",
        subject_id="test-user-001",
        predicate="prefers_genre",
        object_value="rock",
    )

    approved = [
        (
            fact,
            0.95,
            [],
        )
    ]

    package = composer.compose(
        subject_id="test-user-001",
        query="What music should I listen to?",
        approved=approved,
    )

    assert package.memory_available is True
    assert len(package.memories) == 1

    memory = package.memories[0]

    assert memory.fact_id == "rock-fact-001"
    assert memory.subject_id == "test-user-001"
    assert memory.predicate == "prefers_genre"
    assert memory.object_value == "rock"
    assert memory.relevance_score == 0.95


# ============================================================
# TEST 4
# No-memory fallback
# ============================================================

def test_no_memory_fallback():
    """
    When there are no approved memories, the memory package
    should contain zero memories and indicate fallback.
    """

    composer = MemoryComposer()

    package = composer.compose(
        subject_id="test-user-001",
        query="Recommend some music",
        approved=[],
    )

    assert package.memories == []
    assert package.memory_available is False

    assert (
        package.fallback_reason
        == "No relevant governed memories available."
    )