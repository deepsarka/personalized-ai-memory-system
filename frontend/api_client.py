

import requests

import uuid


class APIClient:
    """Client for the Personalized AI Memory System FastAPI backend."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")
        self.access_token: str | None = None

    # ================================================================
    # AUTH
    # ================================================================

    def set_token(self, token: str) -> None:
        """Set JWT access token."""
        self.access_token = token

    def clear_token(self) -> None:
        """Clear JWT access token."""
        self.access_token = None

    def _headers(self) -> dict:
        """Return headers for authenticated requests."""
        if not self.access_token:
            return {}

        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def register(
        self,
        email: str,
        display_name: str,
        password: str,
    ) -> dict:
        """Register a new user."""

        response = requests.post(
            f"{self.base_url}/auth/register",
            json={
                "email": email,
                "display_name": display_name,
                "password": password,
            },
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "Invalid registration response from backend."
            )

        return data

    def login(
        self,
        email: str,
        password: str,
    ) -> dict:
        """Authenticate an existing user."""

        response = requests.post(
            f"{self.base_url}/auth/login",
            json={
                "email": email,
                "password": password,
            },
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "Invalid login response from backend."
            )

        return data

    # ================================================================
    # HEALTH
    # ================================================================

    def health(self) -> dict:
        """Check backend liveness."""

        response = requests.get(
            f"{self.base_url}/health",
            timeout=5,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "Invalid health response from backend."
            )

        return data

    
    # ================================================================
    # CHAT
    # ================================================================

    def chat(
        self,
        subject_id: str,
        query: str,
        session_id: str | None = None,
        top_k: int = 5,
        idempotency_key: str | None = None,
    ) -> dict:
        """Send an authenticated chat request to the backend.

        A unique idempotency key is generated automatically when the
        caller does not provide one.
        """

        if not subject_id:
            raise ValueError("subject_id is required.")

        if not query or not query.strip():
            raise ValueError("query is required.")

        if idempotency_key is None:
            idempotency_key = f"chat-{uuid.uuid4().hex}"

        response = requests.post(
            f"{self.base_url}/chat",
            headers=self._headers(),
            json={
                "subject_id": subject_id,
                "query": query.strip(),
                "session_id": session_id,
                "top_k": top_k,
                "idempotency_key": idempotency_key,
            },
            timeout=120,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError("Invalid chat response from backend.")

        return data



    # ================================================================
    # OBSERVATION
    # ================================================================

    def get_observation(
        self,
        request_id: str,
    ) -> dict:
        """Retrieve the stored observation for a chat request."""

        if not self.access_token:
            raise RuntimeError(
                "Authentication required."
            )

        response = requests.get(
            f"{self.base_url}/chat/observation/{request_id}",
            headers=self._headers(),
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "Invalid observation response from backend."
            )

        return data

    # ================================================================
    # FEEDBACK
    # ================================================================

    def submit_feedback(
        self,
        request_id: str,
        feedback: str,
    ) -> dict:
        """Submit feedback for a chat observation."""

        if not self.access_token:
            raise RuntimeError(
                "Authentication required."
            )

        if not request_id:
            raise ValueError(
                "request_id is required."
            )

        if not feedback or not feedback.strip():
            raise ValueError(
                "feedback must not be empty."
            )

        response = requests.post(
            f"{self.base_url}/chat/feedback",
            headers=self._headers(),
            json={
                "request_id": request_id,
                "feedback": feedback,
            },
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "Invalid feedback response from backend."
            )

        return data

    # ================================================================
    # MEMORY SEARCH
    # ================================================================

    def search_memory(
        self,
        subject_id: str,
        query: str,
        top_k: int = 5,
    ) -> dict:
        """
        Search memory.

        subject_id remains here because retrieval has its own API
        contract. Do not remove it unless the retrieval endpoint
        itself is changed.
        """

        if not self.access_token:
            raise RuntimeError(
                "Authentication required."
            )

        response = requests.post(
            f"{self.base_url}/retrieval/query",
            headers=self._headers(),
            json={
                "subject_id": subject_id,
                "query": query,
                "top_k": top_k,
            },
            timeout=120,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "Invalid memory search response from backend."
            )

        return data

    # ================================================================
    # INGESTION
    # ================================================================

    def ingest_event(
        self,
        event_payload: dict,
    ) -> dict:
        """Submit an interaction event to the ingestion API."""

        if not self.access_token:
            raise RuntimeError(
                "Authentication required."
            )

        response = requests.post(
            f"{self.base_url}/ingest/event",
            headers=self._headers(),
            json=event_payload,
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "Invalid ingestion response from backend."
            )

        return data

