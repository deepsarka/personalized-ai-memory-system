import streamlit as st


def apply_styles():

    st.markdown(
        """
        <style>

        @import url(
            'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap'
        );


        /* =========================================================
           VARIABLES
        ========================================================= */

        :root {

            --spotify-black: #000000;

            --spotify-bg: #121212;

            --spotify-card: #181818;

            --spotify-card-hover: #282828;

            --spotify-green: #1DB954;

            --spotify-green-bright: #1ED760;

            --spotify-text: #FFFFFF;

            --spotify-text-dim: #B3B3B3;

            --spotify-text-faint: #8A8A8A;

            --spotify-border: #2A2A2A;

            --spotify-red: #E91429;
        }


        /* =========================================================
           GLOBAL
        ========================================================= */

        html,
        body,
        .stApp {

            background:
                var(--spotify-bg) !important;
        }


        html,
        body,
        .stApp,
        .stApp * {

            font-family:
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                "Inter",
                "Helvetica Neue",
                Arial,
                sans-serif !important;
        }


        [data-testid*="Icon"],
        [class*="material-symbols"],
        [class*="material-icons"] {

            font-family:
                "Material Symbols Rounded",
                "Material Icons",
                sans-serif !important;
        }


        .main {

            padding-top: 0.5rem;
        }


        section.main > div {

            padding-bottom: 6rem;
        }


        div[data-testid="stAppViewContainer"],
        section.main {

            background:
                var(--spotify-bg) !important;
        }


        /* =========================================================
           HEADER
        ========================================================= */

        [data-testid="stHeader"] {

            background:
                var(--spotify-bg) !important;
        }


        [data-testid="stToolbar"],
        #MainMenu,
        footer {

            visibility: hidden !important;
        }


        /* =========================================================
           SIDEBAR
        ========================================================= */

        section[data-testid="stSidebar"] {

            background:
                var(--spotify-black) !important;

            border-right:
                1px solid var(--spotify-border) !important;

            min-width: 280px !important;

            max-width: 320px !important;
        }


        section[data-testid="stSidebar"] > div {

            background:
                var(--spotify-black) !important;
        }


        section[data-testid="stSidebar"] .block-container {

            padding-top: 1.5rem !important;

            padding-left: 1rem !important;

            padding-right: 1rem !important;

            width: 100% !important;

            max-width: 100% !important;
        }


        section[data-testid="stSidebar"] p {

            color:
                var(--spotify-text) !important;
        }


        /* =========================================================
           BRAND
        ========================================================= */

        .brand-lockup {

            width: 100%;

            margin-bottom: 8px;
        }


        .brand-name {

            font-size: 1.5rem;

            font-weight: 800;

            color:
                var(--spotify-text);

            letter-spacing: -0.03em;

            line-height: 1.1;
        }


        .brand-tagline {

            font-size: 0.68rem;

            font-weight: 700;

            color:
                var(--spotify-green-bright);

            letter-spacing: 0.08em;

            text-transform: uppercase;

            line-height: 1.35;

            max-width: 230px;
        }


        /* =========================================================
           SIDEBAR HEADINGS
        ========================================================= */

        .sidebar-heading {

            font-size: 0.72rem;

            font-weight: 700;

            letter-spacing: 0.08em;

            text-transform: uppercase;

            color:
                var(--spotify-text-dim);

            margin:
                18px 0 10px 0;
        }


        /* =========================================================
           APP HEADER
        ========================================================= */

        .app-title {

            font-size: 1.9rem;

            font-weight: 800;

            color:
                var(--spotify-text);

            letter-spacing: -0.02em;

            line-height: 1.1;
        }


        .app-title span {

            color:
                var(--spotify-green);
        }


        .app-subtitle {

            color:
                var(--spotify-text-dim);

            font-size: 0.85rem;

            margin-top: 4px;
        }


        /* =========================================================
           STATUS
        ========================================================= */

        .status-wrapper {

            text-align: right;

            margin-top: 10px;
        }


        .status-pill {

            display: inline-flex;

            align-items: center;

            gap: 7px;

            padding: 6px 14px;

            border-radius: 999px;

            font-size: 0.78rem;

            font-weight: 600;

            background:
                var(--spotify-card);

            border:
                1px solid var(--spotify-border);
        }


        .status-dot {

            width: 8px;

            height: 8px;

            border-radius: 50%;
        }


        .status-online {

            color:
                var(--spotify-green-bright);
        }


        .status-online .status-dot {

            background:
                var(--spotify-green);

            box-shadow:
                0 0 8px var(--spotify-green);
        }


        .status-offline {

            color:
                #ff8080;
        }


        .status-offline .status-dot {

            background:
                var(--spotify-red);
        }


        /* =========================================================
           INPUTS
        ========================================================= */

        div[data-testid="stTextInput"] input {

            background:
                var(--spotify-card) !important;

            color:
                var(--spotify-text) !important;

            border:
                1px solid var(--spotify-border) !important;

            border-radius:
                24px !important;
        }


        div[data-testid="stTextInput"] input::placeholder {

            color:
                var(--spotify-text-faint) !important;
        }


        div[data-testid="stTextInput"] input:focus {

            border-color:
                var(--spotify-green) !important;
        }


        /* =========================================================
           BUTTONS
        ========================================================= */

        .stButton > button {

            border-radius:
                999px !important;

            background:
                var(--spotify-card) !important;

            border:
                1px solid var(--spotify-border) !important;

            color:
                var(--spotify-text) !important;

            font-weight:
                600 !important;
        }


        .stButton > button:hover {

            border-color:
                var(--spotify-green) !important;

            color:
                var(--spotify-green-bright) !important;

            background:
                var(--spotify-card-hover) !important;
        }


        button[kind="primary"] {

            background:
                var(--spotify-green) !important;

            color:
                #000000 !important;

            border:
                none !important;

            font-weight:
                700 !important;
        }


        button[kind="primary"]:hover {

            background:
                var(--spotify-green-bright) !important;

            color:
                #000000 !important;
        }


        /* =========================================================
           LOGIN
        ========================================================= */

        .login-page {

            min-height:
                32vh;

            display:
                flex;

            align-items:
                center;

            justify-content:
                center;

            padding:
                30px 20px 10px;
        }


        .login-card {

            width:
                100%;

            max-width:
                460px;

            text-align:
                center;

            padding:
                25px 30px 10px;
        }


        .login-logo {

            font-size:
                58px;

            line-height:
                1;

            margin-bottom:
                18px;
        }


        .login-title {

            color:
                #FFFFFF;

            font-size:
                2.5rem;

            font-weight:
                800;

            letter-spacing:
                -0.04em;

            margin-bottom:
                8px;
        }


        .login-subtitle {

            color:
                var(--spotify-green-bright);

            font-size:
                0.9rem;

            font-weight:
                700;

            letter-spacing:
                0.04em;

            margin-bottom:
                14px;
        }


        .login-description {

            color:
                var(--spotify-text-dim);

            font-size:
                0.9rem;

            line-height:
                1.5;
        }


        /* =========================================================
           LOGIN FORM
        ========================================================= */

        div[data-testid="stForm"] {

            max-width:
                460px;

            margin-left:
                auto;

            margin-right:
                auto;

            background:
                transparent !important;

            border:
                none !important;
        }


        /* =========================================================
           TABS
        ========================================================= */

        button[data-baseweb="tab"] {

            color:
                var(--spotify-text-dim) !important;

            font-weight:
                600 !important;
        }


        button[data-baseweb="tab"][aria-selected="true"] {

            color:
                var(--spotify-green-bright) !important;
        }


        /* =========================================================
           MEMORY
        ========================================================= */

        .now-remembering-card {

            background:
                linear-gradient(
                    180deg,
                    #1a2e22 0%,
                    var(--spotify-card) 100%
                );

            border:
                1px solid var(--spotify-border);

            border-radius:
                12px;

            padding:
                14px;
        }


        .now-remembering-empty {

            color:
                var(--spotify-text-faint);

            font-size:
                0.82rem;

            font-style:
                italic;

            line-height:
                1.4;
        }


        .memory-chip {

            display:
                block;

            width:
                100%;

            box-sizing:
                border-box;

            background:
                rgba(29, 185, 84, 0.08);

            border:
                1px solid rgba(29, 185, 84, 0.25);

            border-radius:
                8px;

            padding:
                7px 10px;

            margin-bottom:
                6px;

            font-size:
                0.78rem;

            color:
                #cfeede;

            overflow-wrap:
                anywhere;
        }


        .memory-card {

            background:
                var(--spotify-card);

            border-radius:
                12px;

            padding:
                18px;

            margin-bottom:
                12px;

            border:
                1px solid var(--spotify-border);
        }


        .memory-card-title {

            color:
                var(--spotify-text);

            font-size:
                0.95rem;

            font-weight:
                700;

            margin-bottom:
                8px;
        }


        .memory-card-value {

            color:
                var(--spotify-text);

            font-size:
                0.9rem;

            line-height:
                1.5;

            margin-bottom:
                10px;

            overflow-wrap:
                anywhere;
        }


        .memory-card-meta {

            color:
                var(--spotify-text-dim);

            font-size:
                0.75rem;
        }


        .memory-card-meta strong {

            color:
                var(--spotify-text);
        }


        /* =========================================================
           EMPTY STATE
        ========================================================= */

        .empty-state {

            display:
                flex;

            flex-direction:
                column;

            align-items:
                center;

            justify-content:
                center;

            text-align:
                center;

            min-height:
                420px;

            padding:
                30px 20px;
        }


        .empty-state-title {

            color:
                var(--spotify-text);

            font-size:
                1.1rem;

            font-weight:
                600;

            margin-bottom:
                8px;
        }


        .empty-state-subtitle {

            color:
                var(--spotify-text-dim);

            font-size:
                0.85rem;
        }


        /* =========================================================
           CHAT
        ========================================================= */

        div[data-testid="stChatMessage"] {

            background:
                transparent !important;

            padding:
                4px 0 !important;
        }


        .msg-row {

            display:
                flex;

            width:
                100%;

            margin-bottom:
                8px;
        }


        .msg-row.user {

            justify-content:
                flex-end;
        }


        .msg-user {

            background:
                var(--spotify-green);

            color:
                #000000;

            padding:
                12px 16px;

            border-radius:
                18px 18px 4px 18px;

            max-width:
                78%;

            font-size:
                0.93rem;

            line-height:
                1.5;

            font-weight:
                500;

            overflow-wrap:
                anywhere;
        }


        /* =========================================================
           CHAT INPUT
        ========================================================= */

        div[data-testid="stChatInput"],
        div[data-testid="stBottomBlockContainer"] {

            background:
                var(--spotify-bg) !important;
        }


        div[data-testid="stChatInput"] textarea {

            background:
                var(--spotify-card) !important;

            color:
                var(--spotify-text) !important;

            border:
                1px solid var(--spotify-border) !important;

            border-radius:
                24px !important;
        }


        div[data-testid="stChatInput"] textarea::placeholder {

            color:
                var(--spotify-text-faint) !important;
        }


        /* =========================================================
           EXPANDER
        ========================================================= */

        div[data-testid="stExpander"] {

            background:
                var(--spotify-card) !important;

            border:
                1px solid var(--spotify-border) !important;

            border-radius:
                12px !important;
        }


        div[data-testid="stExpander"] summary {

            color:
                var(--spotify-text) !important;
        }


        /* =========================================================
           RESPONSIVE
        ========================================================= */

        @media (max-width: 768px) {

            .msg-user {

                max-width:
                    88%;
            }

            .empty-state {

                min-height:
                    300px;
            }

            .app-title {

                font-size:
                    1.6rem;
            }
        }

        </style>
        """,
        unsafe_allow_html=True,
    )