from datetime import datetime, timezone

from neo4j import GraphDatabase

from retrieval.retrieval_models import RetrievalQuery, RetrievedFact


class FactRetriever:

    def __init__(self, uri, username, password):
        self.driver = GraphDatabase.driver(
            uri,
            auth=(username, password)
        )

    def close(self):
        self.driver.close()

    def retrieve(
        self,
        query_embedding: list[float],
        request: RetrievalQuery
    ):

        cypher = """
        CALL db.index.vector.queryNodes(
            'fact_embedding_index',
            $candidate_k,
            $embedding
        )
        YIELD node, score

        MATCH (s:Subject {subject_id: $subject_id})-[:HAS_FACT]->(node)

        WHERE
            node.valid_from <= $now
            AND (
                node.valid_until IS NULL
                OR node.valid_until >= $now
            )

        RETURN
            node.fact_id AS fact_id,
            s.subject_id AS subject_id,
            node.fact_type AS fact_type,
            node.predicate AS predicate,
            node.object_value AS object_value,
            node.source AS source,
            node.policy_class AS policy_class,
            node.raw_text AS raw_text,
            node.valid_from AS valid_from,
            node.valid_until AS valid_until,
            score

        ORDER BY score DESC
        LIMIT $top_k
        """

        with self.driver.session() as session:

            # The Neo4j vector procedure ranks the whole Fact index before
            # the subject MATCH is applied. Querying only request.top_k
            # global candidates can therefore discard the user's own facts
            # when another subject has highly similar memories. Overfetch,
            # then apply subject + temporal eligibility and finally enforce
            # the requested top_k.
            candidate_k = min(max(request.top_k * 20, 100), 1000)

            # valid_from/valid_until are stored by graph/writer.py as plain
            # ISO-8601 strings (fact.valid_from.isoformat()), not Neo4j's
            # native temporal type. Comparing them against Cypher's
            # datetime() would compare String <= DateTime, which Cypher
            # evaluates to null — silently dropping every row from the
            # WHERE clause regardless of actual validity. Compare against
            # a same-format ISO string instead, computed the same way
            # (datetime.now(timezone.utc).isoformat()) so lexicographic
            # and chronological order agree.
            now = datetime.now(timezone.utc).isoformat()

            result = session.run(
                cypher,
                embedding=query_embedding,
                subject_id=request.subject_id,
                candidate_k=candidate_k,
                top_k=request.top_k,
                now=now,
            )

            facts = []

            for record in result:

                facts.append(
                    RetrievedFact(
                        fact_id=record["fact_id"],
                        subject_id=record["subject_id"],
                        fact_type=record["fact_type"],
                        predicate=record["predicate"],
                        object_value=record["object_value"],
                        source=record["source"],
                        policy_class=record["policy_class"],
                        raw_text=record["raw_text"],
                        valid_from=record["valid_from"],
                        valid_until=record["valid_until"],
                        similarity=record["score"]
                    )
                )

            return facts