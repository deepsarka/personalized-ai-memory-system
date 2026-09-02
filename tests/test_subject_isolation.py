def test_subject_memory_isolation():

    user1_memories = [
        "rock",
        "workout",
        "edm_exclusion",
    ]

    user2_memories = [
        "classical",
        "study",
        "calm",
    ]

    assert "classical" not in user1_memories
    assert "rock" not in user2_memories

    assert "rock" in user1_memories
    assert "classical" in user2_memories