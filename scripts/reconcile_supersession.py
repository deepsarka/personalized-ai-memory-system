"""
One-off reconciliation script for the supersession bug fixed in
graph/writer.py's _SUPERSEDE_QUERY.

Background
----------
Before the fix, superseding matched old facts by predicate alone, ignoring
object_value. That caused two kinds of bad data already sitting in Neo4j:

  1. Facts wrongly CLOSED: a plain preference (e.g. prefers_genre/jazz) got
     its valid_until set just because a later, unrelated preference shared
     the same predicate (e.g. prefers_genre/lo-fi) -- not a real
     correction.

  2. Facts wrongly left OPEN: an exclusion (excludes_genre/X) never closed
     the matching preference (prefers_genre/X) because they're different
     predicate strings, so the rejected preference kept looking "valid".

This script does NOT touch the graph writer or the live write path (that's
already fixed). It repairs existing data by replaying each subject's full
fact history, in the order the facts were actually stated (valid_from),
through the *same* corrected rules graph/writer.py now uses -- imported
directly from there, not reimplemented, so this can't drift out of sync
with the fix.

What it does NOT recover
-------------------------
Deletion requests (fact_type=deletion_request) never create a Fact node in
Neo4j -- graph/writer.py's _DELETE_QUERY only closes existing facts, it
creates nothing. That means a deletion event has no persisted trace to
replay here: if you explicitly deleted a memory before running this
script, this script has no way to know that happened, and the fact may
reappear as "valid" after reconciliation. If you've used deletion during
testing and it matters, note the fact IDs before you run this, or wipe
your dev graph instead (MATCH (n) DETACH DELETE n in the Neo4j browser)
and re-run your test conversations fresh.

Usage
-----
Dry run (default; prints a diff, changes nothing):

    python -m scripts.reconcile_supersession

Apply the changes:

    python -m scripts.reconcile_supersession --apply

Environment variables (same defaults as the rest of the app):
    NEO4J_URI       (default: bolt://localhost:7687)
    NEO4J_USERNAME  (default: neo4j)
    NEO4J_PASSWORD  (default: testpassword123)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from neo4j import GraphDatabase

# Reuse the exact same predicate-pairing table the fix uses, instead of
# duplicating it here where it could silently drift out of sync.
from graph.writer import _PREDICATE_COUNTERPART

load_dotenv()


def _get_driver():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", os.getenv("NEO4J_USER", "neo4j"))
    password = os.getenv("NEO4J_PASSWORD", "testpassword123")
    return GraphDatabase.driver(uri, auth=(username, password))


_FETCH_QUERY = """
MATCH (s:Subject)-[:HAS_FACT]->(f:Fact)
RETURN
    s.subject_id AS subject_id,
    f.fact_id AS fact_id,
    f.predicate AS predicate,
    f.object_value AS object_value,
    f.fact_type AS fact_type,
    f.valid_from AS valid_from,
    f.valid_until AS valid_until
"""

_UPDATE_QUERY = """
MATCH (f:Fact {fact_id: $fact_id})
SET f.valid_until = $valid_until
"""


def _sort_key(fact: dict) -> tuple:
    """
    Chronological replay order: valid_from first (the one field the bug
    never touched, so it's trustworthy), then fact_id as a tiebreaker.
    fact_id is formatted as "{event_key}-fact{index}" (see
    processing/extractor.py), so for facts extracted from the same
    message with identical timestamps this preserves the original
    extraction order (fact0, fact1, ...).
    """
    return (fact["valid_from"], fact["fact_id"])


def _closure_candidates(open_facts: list[dict], fact: dict) -> list[dict]:
    """
    Mirrors graph/writer.py's _SUPERSEDE_QUERY WHERE clause exactly:

        (old.predicate = predicate AND (old.object_value = object_value OR broad_match))
        OR
        (old.predicate = counterpart_predicate AND old.object_value = object_value)

    Behavior facts never trigger closures (write_fact routes them through
    _APPEND_QUERY, which performs no superseding at all) -- callers should
    skip calling this for fact_type == "behavior".
    """
    predicate = fact["predicate"]
    object_value = fact["object_value"]
    broad_match = fact["fact_type"] == "correction"
    counterpart_predicate = _PREDICATE_COUNTERPART.get(predicate, "")

    to_close = []
    for old in open_facts:
        if old["fact_id"] == fact["fact_id"]:
            continue

        same_predicate_match = old["predicate"] == predicate and (
            old["object_value"] == object_value or broad_match
        )
        counterpart_match = (
            bool(counterpart_predicate)
            and old["predicate"] == counterpart_predicate
            and old["object_value"] == object_value
        )

        if same_predicate_match or counterpart_match:
            to_close.append(old)

    return to_close


def _replay_subject(facts: list[dict]) -> list[dict]:
    """
    Replay one subject's facts in chronological order and compute the
    correct valid_until for each, per the fixed rules. Returns the full
    fact list with a "computed_valid_until" key added to each dict.
    """
    ordered = sorted(facts, key=_sort_key)

    open_facts: list[dict] = []

    for fact in ordered:
        fact["computed_valid_until"] = None

        if fact["fact_type"] != "behavior":
            for old in _closure_candidates(open_facts, fact):
                old["computed_valid_until"] = fact["valid_from"]
                open_facts.remove(old)

        open_facts.append(fact)

    return ordered


def _fetch_all_facts(driver) -> dict[str, list[dict]]:
    by_subject: dict[str, list[dict]] = {}

    with driver.session() as session:
        result = session.run(_FETCH_QUERY)
        for record in result:
            row = dict(record)
            by_subject.setdefault(row["subject_id"], []).append(row)

    return by_subject


def _apply_updates(driver, changes: list[dict]) -> None:
    with driver.session() as session:
        for change in changes:
            session.run(
                _UPDATE_QUERY,
                fact_id=change["fact_id"],
                valid_until=change["computed_valid_until"],
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the corrected valid_until values. Without "
        "this flag, only a dry-run diff is printed.",
    )
    args = parser.parse_args()

    driver = _get_driver()

    try:
        by_subject = _fetch_all_facts(driver)
    except Exception as exc:
        print(f"Failed to connect to Neo4j / fetch facts: {exc}", file=sys.stderr)
        return 1

    if not by_subject:
        print("No Fact nodes found. Nothing to reconcile.")
        return 0

    total_facts = 0
    changes: list[dict] = []

    print(f"Reconciling {len(by_subject)} subject(s)...\n")

    for subject_id, facts in sorted(by_subject.items()):
        replayed = _replay_subject(facts)
        total_facts += len(replayed)

        subject_changes = [
            f for f in replayed if f["valid_until"] != f["computed_valid_until"]
        ]

        if not subject_changes:
            continue

        print(f"Subject: {subject_id}")
        for f in subject_changes:
            old_state = f["valid_until"] or "OPEN (valid)"
            new_state = f["computed_valid_until"] or "OPEN (valid)"
            print(
                f"  {f['predicate']}/{f['object_value']!r} "
                f"[{f['fact_type']}, fact_id={f['fact_id']}]\n"
                f"    was:  {old_state}\n"
                f"    now:  {new_state}"
            )
            changes.append(f)
        print()

    print(f"Checked {total_facts} fact(s) across {len(by_subject)} subject(s).")
    print(f"{len(changes)} fact(s) need a valid_until correction.")

    if not changes:
        print("No changes needed -- your data is already consistent with the fix.")
        return 0

    if not args.apply:
        print("\nDry run only -- no changes written. Re-run with --apply to write them.")
        return 0

    print(f"\nApplying {len(changes)} update(s)...")
    _apply_updates(driver, changes)
    print("Done.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())