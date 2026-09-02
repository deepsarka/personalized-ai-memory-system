import re

# Block common prompt injection or code extraction phrases
JAILBREAK_PATTERNS = [
    r"(ignore|disregard)\s+(previous|above|all)\s+(instructions|prompts)",
    r"(repeat|show|print|display)\s+(your|the)\s+(system|initial)\s+(prompt|instructions)",
    r"(reveal|show)\s+(source|code|backend|files)",
    r"what\s+are\s+your\s+(instructions|rules)",
]

# Detect leaked code or secrets in output
LEAK_PATTERNS = [
    r"```(python|javascript|json|html|css|sql|bash)?[\s\S]*?```", # Markdown code blocks
    r"def\s+\w+\(.*\):",                                         # Python function signatures
    r"import\s+(spotify|spotipy|pinecone|langchain|openai)",     # Python imports
    r"(sk-[a-zA-Z0-9]{20,})|(spotify_client_secret)",            # API Secrets
]

def validate_input(user_prompt: str) -> bool:
    """Returns True if input is safe, False if malicious."""
    for pattern in JAILBREAK_PATTERNS:
        if re.search(pattern, user_prompt, re.IGNORECASE):
            return False
    return True

def sanitize_output(response_text: str) -> str:
    """Blocks response if it contains code or system leaks."""
    for pattern in LEAK_PATTERNS:
        if re.search(pattern, response_text, re.IGNORECASE):
            return "I am only authorized to assist with Spotify playback and listening context."
    return response_text