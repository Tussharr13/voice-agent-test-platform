import base64
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http import cookies
from typing import Any, Dict, Optional, Tuple

from backend import storage


COOKIE_NAME = "botqa_session"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
_request_context = threading.local()


def current_user() -> Optional[Dict[str, Any]]:
    return getattr(_request_context, "user", None)


def set_current_user(user: Optional[Dict[str, Any]]) -> None:
    _request_context.user = user


def clear_current_user() -> None:
    _request_context.user = None


def user_state_id(user: Optional[Dict[str, Any]] = None) -> Optional[str]:
    target = user or current_user()
    if not target or not target.get("id"):
        return None
    return "user_" + str(target["id"]).replace("-", "")


def should_seed_from_default(user: Optional[Dict[str, Any]] = None) -> bool:
    target = user or current_user()
    configured_owner = os.environ.get("SUPABASE_APP_USER_ID", "").strip()
    return bool(target and configured_owner and target.get("id") == configured_owner)


def session_secret() -> bytes:
    secret = os.environ.get("APP_SESSION_SECRET", "").strip() or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not secret:
        secret = "yellow-ai-chat-qa-local-session"
    return secret.encode("utf-8")


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def sign_payload(payload: Dict[str, Any]) -> str:
    encoded = b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(session_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{b64url_encode(signature)}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    if "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    expected = b64url_encode(hmac.new(session_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(b64url_decode(encoded).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    if not payload.get("id") or not payload.get("email"):
        return None
    return {"id": payload["id"], "email": payload["email"]}


def parse_cookie(header: str) -> Optional[str]:
    if not header:
        return None
    jar = cookies.SimpleCookie()
    try:
        jar.load(header)
    except cookies.CookieError:
        return None
    item = jar.get(COOKIE_NAME)
    return item.value if item else None


def user_from_handler(handler: Any) -> Optional[Dict[str, Any]]:
    token = parse_cookie(handler.headers.get("Cookie", ""))
    return verify_token(token) if token else None


def create_cookie(user: Dict[str, Any]) -> str:
    payload = {
        "id": user["id"],
        "email": user["email"],
        "iat": int(time.time()),
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    }
    token = sign_payload(payload)
    return f"{COOKIE_NAME}={token}; Max-Age={SESSION_TTL_SECONDS}; Path=/; HttpOnly; SameSite=Lax"


def clear_cookie() -> str:
    return f"{COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"


def auth_url(path: str, query: str = "") -> str:
    config = storage.supabase_config()
    clean_path = path.lstrip("/")
    base = f"{config['url']}/auth/v1/{clean_path}"
    return f"{base}?{query}" if query else base


def require_supabase_auth() -> None:
    config = storage.supabase_config()
    if not config["url"] or not config["key"]:
        raise ValueError("Supabase URL and service-role key are required for login.")


def request_auth(method: str, path: str, payload: Dict[str, Any], query: str = "") -> Dict[str, Any]:
    require_supabase_auth()
    data = json.dumps(storage.sanitize_for_jsonb(payload)).encode("utf-8")
    request = urllib.request.Request(
        auth_url(path, query),
        data=data,
        headers=storage.supabase_headers(),
        method=method,
    )
    with urllib.request.urlopen(request, timeout=float(os.environ.get("SUPABASE_TIMEOUT", "25"))) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def normalize_auth_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            return parsed.get("msg") or parsed.get("message") or parsed.get("error_description") or parsed.get("error") or "Authentication failed"
        except json.JSONDecodeError:
            return body[:240] or "Authentication failed"
    return str(exc) or "Authentication failed"


def validate_credentials(email: str, password: str) -> Tuple[str, str]:
    clean_email = str(email or "").strip().lower()
    clean_password = str(password or "")
    if "@" not in clean_email or len(clean_email) > 254:
        raise ValueError("Enter a valid email address.")
    if len(clean_password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    return clean_email, clean_password


def login(email: str, password: str) -> Dict[str, Any]:
    email, password = validate_credentials(email, password)
    try:
        result = request_auth(
            "POST",
            "token",
            {"email": email, "password": password},
            query="grant_type=password",
        )
    except Exception as exc:
        raise ValueError(normalize_auth_error(exc)) from exc
    user = result.get("user") or {}
    if not user.get("id"):
        raise ValueError("Login failed.")
    return {"id": user["id"], "email": user.get("email") or email}


def signup(email: str, password: str, full_name: str = "") -> Dict[str, Any]:
    email, password = validate_credentials(email, password)
    payload = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"full_name": str(full_name or "").strip()} if full_name else {},
    }
    try:
        request_auth("POST", "admin/users", payload)
    except Exception as exc:
        raise ValueError(normalize_auth_error(exc)) from exc
    return login(email, password)
