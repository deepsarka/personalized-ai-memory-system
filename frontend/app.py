
from datetime import datetime, timezone
import html
import logging
import re
import uuid

import requests
import streamlit as st

from api_client import APIClient
from styles import apply_styles


# ====================================================================
# LOGGING
# ====================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("frontend.app")


# ====================================================================
# PAGE CONFIGURATION
# ====================================================================

st.set_page_config(
    page_title="Spotify | Personalized AI Memory Assistant",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ====================================================================
# STYLES
# ====================================================================

apply_styles()


# ====================================================================
# API CLIENT
# ====================================================================

client = APIClient(
    base_url="http://127.0.0.1:8000"
)


# ====================================================================
# SESSION STATE INITIALIZATION
# ====================================================================

DEFAULTS = {
    "authenticated": False,
    "access_token": None,
    "user": None,
    "subject_id": None,
    "session_id": str(uuid.uuid4()),
    "messages": [],
    "last_memory_context": None,
    "observations": {},
    "memory_search_results": None,
}

for key, default_value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


# ====================================================================
# RESTORE AUTH TOKEN
# ====================================================================

if st.session_state.access_token:
    client.set_token(
        st.session_state.access_token
    )


# ====================================================================
# AUTH HELPERS
# ====================================================================

def complete_login(result: dict) -> None:
    """
    Store authentication response in Streamlit session state.
    """

    if not isinstance(result, dict):
        raise ValueError(
            "Backend returned an invalid authentication response."
        )

    access_token = result.get("access_token")
    user = result.get("user")

    if not access_token:
        raise ValueError(
            "Backend authentication response does not contain access_token."
        )

    if not isinstance(user, dict):
        raise ValueError(
            "Backend authentication response does not contain a valid user object."
        )

    user_id = (
        user.get("id")
        or user.get("user_id")
        or user.get("subject_id")
    )

    if not user_id:
        raise ValueError(
            "Backend authentication response does not contain a user ID."
        )

    # ---------------------------------------------------------------
    # Save authentication
    # ---------------------------------------------------------------

    st.session_state.authenticated = True
    st.session_state.access_token = str(access_token)
    st.session_state.user = user
    st.session_state.subject_id = str(user_id)

    # ---------------------------------------------------------------
    # Configure API client immediately
    # ---------------------------------------------------------------

    client.set_token(str(access_token))

    # ---------------------------------------------------------------
    # Create fresh conversation
    # ---------------------------------------------------------------

    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.last_memory_context = None
    st.session_state.observations = {}
    st.session_state.memory_search_results = None


def logout_user() -> None:
    """
    Clear authentication and conversation state.
    """

    client.clear_token()

    st.session_state.authenticated = False
    st.session_state.access_token = None
    st.session_state.user = None
    st.session_state.subject_id = None
    st.session_state.messages = []
    st.session_state.last_memory_context = None
    st.session_state.observations = {}
    st.session_state.memory_search_results = None
    st.session_state.session_id = str(uuid.uuid4())


# ====================================================================
# AUTH ERROR HELPER
# ====================================================================

def get_backend_error(
    error: Exception,
    default_message: str,
) -> str:

    if isinstance(error, requests.HTTPError):

        response = getattr(
            error,
            "response",
            None,
        )

        if response is not None:

            try:
                data = response.json()

                if isinstance(data, dict):

                    detail = data.get("detail")

                    if detail:
                        return str(detail)

            except Exception:
                pass

        return default_message

    return str(error)


# ====================================================================
# AUTH PAGE
# ====================================================================

def show_auth_page() -> None:

    # ---------------------------------------------------------------
    # LOGIN HEADER / BRAND
    # ---------------------------------------------------------------

    st.html(
        """
        <div class="login-page">
            <div class="login-card">

                <div class="login-logo">
                    🟢
                </div>

                <div class="login-title">
                    Spotify
                </div>

                <div class="login-subtitle">
                    Personalized AI Memory Assistant
                </div>

                <div class="login-description">
                    Your music assistant that remembers your taste.
                </div>

            </div>
        </div>
        """
    )

    login_tab, signup_tab = st.tabs(
        ["Log in", "Sign up"]
    )

    # ================================================================
    # LOGIN
    # ================================================================

    with login_tab:

        with st.form(
            "login_form",
            clear_on_submit=False,
        ):

            email = st.text_input(
                "Email",
                placeholder="you@example.com",
                key="login_email",
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder="Your password",
                key="login_password",
            )

            submitted = st.form_submit_button(
                "Log in",
                type="primary",
                use_container_width=True,
            )

        if submitted:

            email = email.strip()

            if not email:

                st.error(
                    "Please enter your email."
                )

            elif not password:

                st.error(
                    "Please enter your password."
                )

            else:

                try:

                    with st.spinner(
                        "Signing you in..."
                    ):

                        result = client.login(
                            email=email,
                            password=password,
                        )

                        complete_login(result)

                    st.rerun()

                except Exception as e:

                    logger.exception(
                        "Login failed"
                    )

                    st.error(
                        get_backend_error(
                            e,
                            "Invalid email or password.",
                        )
                    )

    # ================================================================
    # SIGN UP
    # ================================================================

    with signup_tab:

        with st.form(
            "signup_form",
            clear_on_submit=False,
        ):

            display_name = st.text_input(
                "Display name",
                placeholder="Your name",
                key="signup_display_name",
            )

            email = st.text_input(
                "Email",
                placeholder="you@example.com",
                key="signup_email",
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder="Minimum 8 characters",
                key="signup_password",
            )

            confirm_password = st.text_input(
                "Confirm password",
                type="password",
                placeholder="Repeat your password",
                key="signup_confirm_password",
            )

            submitted = st.form_submit_button(
                "Create account",
                type="primary",
                use_container_width=True,
            )

        if submitted:

            display_name = display_name.strip()
            email = email.strip()

            if not display_name:

                st.error(
                    "Please enter your name."
                )

            elif not email:

                st.error(
                    "Please enter your email."
                )

            elif len(password) < 8:

                st.error(
                    "Password must contain at least 8 characters."
                )

            elif password != confirm_password:

                st.error(
                    "Passwords do not match."
                )

            else:

                try:

                    with st.spinner(
                        "Creating your account..."
                    ):

                        result = client.register(
                            email=email,
                            display_name=display_name,
                            password=password,
                        )

                        complete_login(result)

                    st.rerun()

                except Exception as e:

                    logger.exception(
                        "Registration failed"
                    )

                    st.error(
                        get_backend_error(
                            e,
                            "Registration failed.",
                        )
                    )


# ====================================================================
# SHOW AUTH PAGE
# ====================================================================

if not st.session_state.authenticated:

    show_auth_page()
    st.stop()


# ====================================================================
# AUTHENTICATED USER
# ====================================================================

user = st.session_state.user

if not isinstance(user, dict):

    st.error(
        "Invalid authentication state."
    )

    logout_user()
    st.stop()


# ====================================================================
# USER INFORMATION
# ====================================================================

subject_id = st.session_state.subject_id

if not subject_id:

    subject_id = (
        user.get("id")
        or user.get("user_id")
        or user.get("subject_id")
    )

if not subject_id:

    st.error(
        "Authenticated successfully, but no user ID was returned by the backend."
    )

    logout_user()
    st.stop()

subject_id = str(subject_id)


display_name = (
    user.get("display_name")
    or user.get("name")
    or "Listener"
)

display_email = user.get(
    "email",
    "",
)


# ====================================================================
# CONVERSATION
# ====================================================================

def start_new_conversation() -> None:

    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.last_memory_context = None
    st.session_state.observations = {}
    st.session_state.memory_search_results = None


# ====================================================================
# MEMORY INGESTION
# ====================================================================

def ingest_user_event(
    subject_id: str,
    raw_text: str,
) -> None:

    event_payload = {
        "schema_version": "1.0",
        "service_id": "spotify_chat_ui",
        "subject_id": subject_id,
        "consent_state": "granted",
        "idempotency_key": f"evt_{uuid.uuid4().hex}",
        "surface": "chat_assistant",
        "event_type": "explicit_statement",
        "raw_text": raw_text,
        "content_entity_id": f"msg_{uuid.uuid4().hex}",
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    try:

        client.ingest_event(
            event_payload
        )

    except Exception as e:

        # Do NOT kill chat if ingestion fails.
        logger.warning(
            "Memory ingestion failed: %s",
            e,
        )


# ====================================================================
# FEEDBACK
# ====================================================================

def send_feedback(
    request_id: str,
    feedback: str,
    msg_index: int,
) -> None:

    try:

        client.submit_feedback(
            request_id=request_id,
            feedback=feedback,
        )

        st.session_state.messages[
            msg_index
        ]["feedback"] = feedback

        st.toast(
            f"Feedback recorded: {feedback}",
            icon="✅",
        )

    except Exception as e:

        logger.exception(
            "Feedback failed"
        )

        st.toast(
            f"Couldn't send feedback: {e}",
            icon="⚠️",
        )


# ====================================================================
# OBSERVATION
# ====================================================================

def load_observation(
    request_id: str,
) -> None:

    try:

        observation = client.get_observation(
            request_id
        )

        st.session_state.observations[
            request_id
        ] = observation

    except Exception as e:

        logger.exception(
            "Observation loading failed"
        )

        st.toast(
            f"Couldn't load observation: {e}",
            icon="⚠️",
        )


# ====================================================================
# RESPONSE CLEANING
# ====================================================================

def clean_response(
    text: str,
) -> str:

    if not text:
        return ""

    cleaned = str(text)

    # ---------------------------------------------------------------
    # Remove Markdown SVG blocks
    # ---------------------------------------------------------------

    cleaned = re.sub(
        r"```svg.*?```",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # ---------------------------------------------------------------
    # Remove raw SVG blocks
    # ---------------------------------------------------------------

    cleaned = re.sub(
        r"<svg\b[^>]*>.*?</svg>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # ---------------------------------------------------------------
    # Remove lines containing only SVG markers
    # ---------------------------------------------------------------

    cleaned = re.sub(
        r"(?im)^\s*```?svg```?\s*$",
        "",
        cleaned,
    )

    # ---------------------------------------------------------------
    # Remove accidental div-only lines
    # ---------------------------------------------------------------

    cleaned = re.sub(
        r"(?im)^\s*</?div[^>]*>\s*$",
        "",
        cleaned,
    )

    # ---------------------------------------------------------------
    # Collapse excessive blank lines
    # ---------------------------------------------------------------

    cleaned = re.sub(
        r"\n{3,}",
        "\n\n",
        cleaned,
    )

    return cleaned.strip()


# ====================================================================
# MESSAGE RENDERING
# ====================================================================

def render_assistant_message(
    text: str,
) -> None:

    with st.chat_message("assistant"):

        st.markdown(
            clean_response(text)
        )


def render_user_message(
    text: str,
) -> None:

    safe_text = html.escape(
        str(text)
    )

    st.html(
        f"""
        <div class="msg-row user">
            <div class="msg-user">
                {safe_text}
            </div>
        </div>
        """
    )


# ====================================================================
# SIDEBAR
# ====================================================================

with st.sidebar:

    st.html(
        """
        <div class="brand-lockup">

            <div class="brand-name">
                Spotify
            </div>

            <div class="brand-tagline">
                Personalized AI Memory Assistant
            </div>

        </div>
        """
    )

    st.html(
        """
        <div class="sidebar-heading">
            Listener
        </div>
        """
    )

    st.markdown(
        f"**{html.escape(str(display_name))}**"
    )

    st.caption(
        display_email
    )

    st.caption(
        f"Memory ID: {subject_id[:8]}..."
    )

    st.divider()

    if st.button(
        "Start new conversation",
        use_container_width=True,
    ):

        start_new_conversation()
        st.rerun()

    if st.button(
        "Log out",
        use_container_width=True,
    ):

        logout_user()
        st.rerun()

    st.html(
        """
        <div class="sidebar-heading">
            Memory Limit
        </div>
        """
    )

    top_k = st.slider(
        "Memories to retrieve per response",
        min_value=1,
        max_value=20,
        value=5,
        label_visibility="collapsed",
    )

    st.html(
        """
        <div class="sidebar-heading">
            Now Remembering
        </div>
        """
    )

    memory_context = (
        st.session_state.last_memory_context
    )

    if (
        memory_context
        and "No relevant memories"
        not in str(memory_context)
    ):

        lines = [
            line.strip("- ").strip()
            for line in str(
                memory_context
            ).split("\n")
            if line.strip()
        ]

        st.html(
            '<div class="now-remembering-card">'
        )

        for line in lines:

            safe_line = html.escape(
                line
            )

            st.html(
                f"""
                <div class="memory-chip">
                    {safe_line}
                </div>
                """
            )

        st.html(
            "</div>"
        )

    else:

        st.html(
            """
            <div class="now-remembering-empty">
                Memories the assistant is using
                will show up here as you chat.
            </div>
            """
        )


# ====================================================================
# MAIN HEADER
# ====================================================================

col_title, col_status = st.columns(
    [4, 1]
)


with col_title:

    st.html(
        f"""
        <div class="app-title">
            Chat<span>.</span>
        </div>

        <div class="app-subtitle">
            Personalized, memory-aware responses
            for {html.escape(str(display_name))}
        </div>
        """
    )


with col_status:

    try:

        client.health()

        st.html(
            """
            <div class="status-wrapper">

                <span class="status-pill status-online">
                    <span class="status-dot"></span>
                    Online
                </span>

            </div>
            """
        )

    except Exception:

        st.html(
            """
            <div class="status-wrapper">

                <span class="status-pill status-offline">
                    <span class="status-dot"></span>
                    Offline
                </span>

            </div>
            """
        )


# ====================================================================
# EMPTY STATE
# ====================================================================

if not st.session_state.messages:

    st.html(
        """
        <div class="empty-state">

            <div class="empty-state-title">
                Ask for a playlist, a mood,
                or a recommendation.
            </div>

            <div class="empty-state-subtitle">
                The assistant remembers your taste
                as you go.
            </div>

        </div>
        """
    )


# ====================================================================
# CHAT HISTORY
# ====================================================================

for i, msg in enumerate(
    st.session_state.messages
):

    if msg.get("role") == "user":

        render_user_message(
            msg.get("text", "")
        )

        continue

    render_assistant_message(
        msg.get("text", "")
    )

    request_id = msg.get(
        "request_id"
    )

    if not request_id:
        continue

    feedback_given = msg.get(
        "feedback"
    )

    fcol1, fcol2, fcol3 = st.columns(
        [1, 1, 10]
    )

    with fcol1:

        if st.button(
            "👍"
            if feedback_given != "positive"
            else "👍 ✓",
            key=f"up_{i}",
            disabled=(
                feedback_given is not None
            ),
        ):

            send_feedback(
                request_id,
                "positive",
                i,
            )

            st.rerun()

    with fcol2:

        if st.button(
            "👎"
            if feedback_given != "negative"
            else "👎 ✓",
            key=f"down_{i}",
            disabled=(
                feedback_given is not None
            ),
        ):

            send_feedback(
                request_id,
                "negative",
                i,
            )

            st.rerun()

    with fcol3:

        with st.expander(
            "Details"
        ):

            facts = msg.get(
                "facts_used",
                [],
            )

            st.metric(
                "Memories used",
                len(facts),
            )

            st.code(
                request_id,
                language="text",
            )

            memory_used = msg.get(
                "memory_context_used"
            )

            if memory_used:

                st.markdown(
                    "**Long-term memory used**"
                )

                st.info(
                    memory_used
                )

            conversation_used = msg.get(
                "conversation_history_used"
            )

            if conversation_used:

                st.markdown(
                    "**Conversation history used**"
                )

                st.text(
                    conversation_used
                )

            st.markdown(
                "**Observation**"
            )

            if st.button(
                "Load observation",
                key=f"obs_{i}",
            ):

                load_observation(
                    request_id
                )

                st.rerun()

            observation = (
                st.session_state.observations.get(
                    request_id
                )
            )

            if observation:

                o1, o2, o3, o4 = st.columns(
                    4
                )

                with o1:

                    st.metric(
                        "Model",
                        observation.get(
                            "model",
                            "—",
                        ),
                    )

                with o2:

                    latency = observation.get(
                        "latency_ms",
                        "—",
                    )

                    st.metric(
                        "Latency",
                        f"{latency} ms",
                    )

                with o3:

                    st.metric(
                        "Fallback",
                        str(
                            observation.get(
                                "fallback_used",
                                "—",
                            )
                        ),
                    )

                with o4:

                    st.metric(
                        "Feedback",
                        observation.get(
                            "feedback"
                        )
                        or "None",
                    )


# ====================================================================
# CHAT INPUT
# ====================================================================

user_input = st.chat_input(
    "Ask for something to listen to..."
)


if user_input:

    user_input = user_input.strip()

    if user_input:

        # ------------------------------------------------------------
        # Add user message immediately
        # ------------------------------------------------------------

        st.session_state.messages.append(
            {
                "role": "user",
                "text": user_input,
                "request_id": None,
            }
        )

        with st.spinner(
            "Remembering your preferences and thinking..."
        ):

            try:

                # ====================================================
                # 1. INGEST MEMORY
                # ====================================================

                ingest_user_event(
                    subject_id=subject_id,
                    raw_text=user_input,
                )

                # ====================================================
                # 2. CHAT BACKEND
                # ====================================================

                
                result = client.chat(
                    subject_id=subject_id,
                    query=user_input,
                    session_id=(
                        st.session_state.session_id
                    ),
                    top_k=top_k,
                    idempotency_key=(
                        f"chat-{uuid.uuid4().hex}"
                    ),
                )



                # ====================================================
                # 3. SESSION ID
                # ====================================================

                returned_session_id = result.get(
                    "session_id"
                )

                if returned_session_id:

                    st.session_state.session_id = str(
                        returned_session_id
                    )

                # ====================================================
                # 4. MEMORY CONTEXT
                # ====================================================

                st.session_state.last_memory_context = (
                    result.get(
                        "memory_context_used"
                    )
                )

                # ====================================================
                # 5. ASSISTANT MESSAGE
                # ====================================================

                assistant_text = result.get(
                    "response",
                    "",
                )

                if not assistant_text:

                    assistant_text = (
                        "The assistant returned an empty response."
                    )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "text": assistant_text,
                        "request_id": result.get(
                            "request_id"
                        ),
                        "session_id": result.get(
                            "session_id"
                        ),
                        "facts_used": result.get(
                            "facts_used",
                            [],
                        ),
                        "memory_context_used": result.get(
                            "memory_context_used"
                        ),
                        "conversation_history_used": result.get(
                            "conversation_history_used"
                        ),
                        "feedback": None,
                    }
                )

            except requests.HTTPError as e:

                logger.exception(
                    "Chat HTTP request failed"
                )

                error_message = get_backend_error(
                    e,
                    "The backend rejected the chat request.",
                )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "text": (
                            f"⚠️ {error_message}"
                        ),
                        "request_id": None,
                        "session_id": (
                            st.session_state.session_id
                        ),
                        "facts_used": [],
                        "memory_context_used": None,
                        "conversation_history_used": None,
                        "feedback": None,
                    }
                )

            except Exception as e:

                logger.exception(
                    "Chat request failed"
                )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "text": (
                            "⚠️ Something went wrong "
                            "while reaching the assistant:\n\n"
                            f"{e}"
                        ),
                        "request_id": None,
                        "session_id": (
                            st.session_state.session_id
                        ),
                        "facts_used": [],
                        "memory_context_used": None,
                        "conversation_history_used": None,
                        "feedback": None,
                    }
                )

        st.rerun()


# ====================================================================
# MEMORY EXPLORER
# ====================================================================

with st.expander(
    "🔎 Memory Explorer — search this listener's memory directly"
):

    st.caption(
        "Search the governed long-term memory store "
        "without going through chat."
    )

    memory_query = st.text_input(
        "Memory search query",
        placeholder=(
            "e.g. What music do I like while working?"
        ),
        key="memory_search_input",
    )

    if st.button(
        "Search memory",
        key="memory_search_button",
    ):

        memory_query = memory_query.strip()

        if not memory_query:

            st.warning(
                "Enter a memory search query first."
            )

        else:

            try:

                st.session_state.memory_search_results = (
                    client.search_memory(
                        subject_id=subject_id,
                        query=memory_query,
                        top_k=top_k,
                    )
                )

            except Exception as e:

                logger.exception(
                    "Memory search failed"
                )

                st.error(
                    f"Memory search failed: {e}"
                )

    search_results = (
        st.session_state.memory_search_results
    )

    if search_results:

        facts = search_results.get(
            "facts",
            [],
        )

        if not facts:

            st.info(
                "No matching memories found."
            )

        else:

            for fact in facts:

                predicate = fact.get(
                    "predicate",
                    "Unknown",
                )

                object_value = fact.get(
                    "object_value",
                    "Unknown",
                )

                similarity = fact.get(
                    "similarity",
                    0,
                )

                source = fact.get(
                    "source",
                    "Unknown",
                )

                try:

                    similarity_value = float(
                        similarity
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    similarity_value = 0.0

                safe_predicate = html.escape(
                    str(predicate)
                )

                safe_object_value = html.escape(
                    str(object_value)
                )

                safe_source = html.escape(
                    str(source)
                )

                st.html(
                    f"""
                    <div class="memory-card">

                        <div class="memory-card-title">
                            🧠 {safe_predicate}
                        </div>

                        <div class="memory-card-value">
                            {safe_object_value}
                        </div>

                        <div class="memory-card-meta">
                            Similarity:
                            <strong>
                                {similarity_value:.3f}
                            </strong>

                            &nbsp; | &nbsp;

                            Source:
                            <strong>
                                {safe_source}
                            </strong>
                        </div>

                    </div>
                    """
                )

