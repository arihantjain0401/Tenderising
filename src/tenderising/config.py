"""Configuration: endpoints, politeness, enums, and verified mappings.

Every endpoint and mapping below was revalidated live on 2026-09-19 and is
recorded in docs/revalidation-2026-09-19.md. Per §3, re-verify against the live
source before changing any of the fetch contracts.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "curated.db"

# --- GeM endpoints (revalidated 2026-09-19) ---
BASE = "https://bidplus.gem.gov.in"
LIST_URL = f"{BASE}/all-bids"
DATA_URL = f"{BASE}/all-bids-data"
SHOWBID_DOCUMENT = f"{BASE}/showbidDocument/"
GET_BID_RESULT_VIEW = f"{BASE}/bidding/bid/getBidResultView/"
GET_SINGLE_PACKET_RESULT_VIEW = f"{BASE}/bidding/bid/getSinglePacketResultView/"
GET_BID_RESULT_VIEW_SCHEDULE = f"{BASE}/bidding/bid/getBidResultViewSchedule/"
# Corrigendum endpoints (anonymous CSRF, revalidated 2026-09-19).
PUBLIC_BID_OTHER_DETAILS = f"{BASE}/public-bid-other-details/"
VIEW_CORRIGENDUM = f"{BASE}/bidding/bid/viewCorrigendum/"
GET_PUBLIC_TC_HTML = f"{BASE}/bidding/bid/getPublicTchtml/"
VIEW_CONTRACTS = "https://gem.gov.in/view_contracts"  # captcha-gated (§3: no bypass)


# --- Enums (stored as their .value strings) ---
class DisclosureState(enum.StrEnum):
    FULL = "full"
    MASKED = "masked"
    PARTIAL = "partial"
    MISSING = "missing"
    UNPUBLISHED = "unpublished"


class ParseStatus(enum.StrEnum):
    PARSED = "parsed"
    PARTIAL = "partial"
    FAILED = "failed"


class RunType(enum.StrEnum):
    FULL = "full"
    DELTA = "delta"
    CORRIGENDUM = "corrigendum"
    DOCUMENT = "document"
    ON_DEMAND = "on_demand"


class RawKind(enum.StrEnum):
    HTML = "html"
    JSON = "json"
    PDF = "pdf"
    API = "api"


class Stage(enum.StrEnum):
    TECHNICAL = "technical"
    FINANCIAL = "financial"
    AUCTION = "auction"
    AWARD = "award"


class BuyerLevel(enum.StrEnum):
    MINISTRY = "ministry"
    DEPARTMENT = "department"
    ORGANISATION = "organisation"
    OFFICE = "office"


class AwardSource(enum.StrEnum):
    BID_AWARD = "bid_award"
    RA_AWARD = "ra_award"


class OrderType(enum.StrEnum):
    DIRECT_PURCHASE = "direct_purchase"
    L1_PURCHASE = "l1_purchase"


class ScopeType(enum.StrEnum):
    OEM = "OEM"
    RESELLER = "reseller"
    SERVICE = "service"


# --- Verified mappings (dated; re-verify before change) ---
# b_buyer_status -> label (0..3); verified 2026-09-19, matches gem-scraper 2026-08-31.
BUYER_STATUS_LABELS = [
    "Not Evaluated",
    "Technical Evaluation",
    "Financial Evaluation",
    "Bid Award",
]
STATUS_MAP_VERSION = "buyer_status_v1"

# b_status (bid active/closed) observed values, 2026-09-19.
BID_STATUS_ACTIVE = "1"
BID_STATUS_CLOSED = "2"

# b_bid_type: only 5=RA is confirmed (site JS). Others stored raw.
BID_TYPE_RA = "5"

FINGERPRINT_ALGO_VERSION = "fp_v1"

# --- searchBid filter values (revalidated 2026-09-19) ---
FILTER_ONGOING = "ongoing_bids"
FILTER_BY_STATUS = "bidrastatus"
BY_STATUS = {
    "tech": "tech_evaluated",
    "financial": "fin_evaluated",
    "awarded": "bid_awarded",
}


# --- Politeness (§7): no rate-limit evasion ---
@dataclass
class Politeness:
    request_delay_seconds: float = 1.5
    timeout_seconds: float = 30.0
    max_retries: int = 3
    page_size: int = 10
    max_pages_delta: int = 400
    max_pages_full: int = 6000
    convergence_pages: int = 5
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )


POLITENESS = Politeness()


# --- LLM / chat / RAG (local Ollama + cloud DeepSeek) ---
OLLAMA_BASE_URL = "http://127.0.0.1:11435"
CHAT_PROVIDER = "deepseek"  # "ollama" | "deepseek"
CHAT_MODEL = "qwen3:8b"  # local model, used only when CHAT_PROVIDER == "ollama"
# Chat conversation history lives in its own sqlite file, kept out of the
# curated procurement DB (mirrors the standalone data/rag_index.sqlite pattern).
CHAT_DB_PATH = DATA_DIR / "chat.db"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
EMBED_MODEL = "nomic-embed-text"
RAG_TOP_K = 5
SQL_MAX_ROWS = 500


def deepseek_api_key() -> str:
    """DeepSeek API key from the environment, else credentials/deepseek.env (never hardcoded)."""
    import os

    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    env_file = PROJECT_ROOT / "credentials" / "deepseek.env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# --- Google OAuth (Workspace sign-in) ---
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_SCOPES = "openid email profile"


def google_credentials() -> dict:
    """Google OAuth client id/secret/redirect. Environment overrides the file."""
    import os

    keys = {
        "client_id": "GOOGLE_CLIENT_ID",
        "client_secret": "GOOGLE_CLIENT_SECRET",
        "redirect_uri": "GOOGLE_REDIRECT_URI",
    }
    out = {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        "redirect_uri": os.environ.get(
            "GOOGLE_REDIRECT_URI", "http://localhost:5173/api/auth/callback"
        ),
    }
    env_file = PROJECT_ROOT / "credentials" / "google.env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            for key, env_name in keys.items():
                if line.startswith(f"{env_name}=") and not out[key]:
                    out[key] = line.split("=", 1)[1].strip().strip('"').strip("'")
    return out


def tester_credentials() -> tuple[str, str]:
    """Entry-gate tester credentials from env, else credentials/tester.env (never hardcoded)."""
    import os

    user = os.environ.get("TENDERISING_TESTER_USER", "").strip()
    pw = os.environ.get("TENDERISING_TESTER_PASS", "")
    env_file = PROJECT_ROOT / "credentials" / "tester.env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TENDERISING_TESTER_USER=") and not user:
                user = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("TENDERISING_TESTER_PASS=") and not pw:
                pw = line.split("=", 1)[1].strip().strip('"').strip("'")
    return user, pw
