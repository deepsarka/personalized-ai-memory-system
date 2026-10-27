
from functools import lru_cache
from sentence_transformers import SentenceTransformer


class QueryEmbedder:

    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            self._model = _get_model()
        return self._model

    def embed(self, text: str) -> list[float]:
        vector = self.model.encode(
            text,
            normalize_embeddings=True
        )
        return vector.tolist()


@lru_cache(maxsize=1)
def _get_model():
    return SentenceTransformer("all-MiniLM-L6-v2")
