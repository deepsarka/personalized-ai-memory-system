from langsmith import traceable

from retrieval.embedding import QueryEmbedder
from retrieval.retrieval_models import RetrievalQuery, RetrievalResult
from retrieval.retriever import FactRetriever


class RetrievalService:

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_username: str,
        neo4j_password: str
    ):

        self.embedder = QueryEmbedder()

        self.retriever = FactRetriever(
            neo4j_uri,
            neo4j_username,
            neo4j_password
        )

    @traceable(
        name="Memory Retrieval",
        run_type="retriever",
    )
    def retrieve(
        self,
        request: RetrievalQuery
    ) -> RetrievalResult:

        # 1. Convert user query → 384-dimensional vector
        query_embedding = self.embedder.embed(
            request.query
        )

        # 2. Search Neo4j
        facts = self.retriever.retrieve(
            query_embedding,
            request
        )

        # 3. Return structured result
        return RetrievalResult(
            query=request.query,
            subject_id=request.subject_id,
            facts=facts
        )