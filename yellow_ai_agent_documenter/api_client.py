#!/usr/bin/env python3
"""
Small Yellow.ai sync-message client used by documenter.py.

The API reference describes a synchronous "send message/event to bot" body with
botId, sender, data, and message fields. Yellow.ai deployments can vary by
region and route, so YELLOW_AI_SYNC_URL is the preferred explicit endpoint.
"""

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(ROOT / ".env")
load_env_file(ROOT.parent / ".env")

BOT_ID = os.environ.get("YELLOW_AI_BOT_ID", "").strip()
API_KEY = os.environ.get("YELLOW_AI_API_KEY", "").strip()
BASE_URL = os.environ.get("YELLOW_AI_BASE_URL", "https://cloud.yellow.ai").strip().rstrip("/")
SYNC_URL = os.environ.get("YELLOW_AI_SYNC_URL", "").strip()
CHANNEL = os.environ.get("YELLOW_AI_CHANNEL", "api").strip() or "api"
SENDER_ID = os.environ.get("YELLOW_AI_SENDER_ID", f"doc_probe_{uuid.uuid4().hex[:12]}").strip()
SENDER_STRATEGY = os.environ.get("YELLOW_AI_SENDER_STRATEGY", "per_probe").strip().lower()
FETCH_VARIABLES = [
    item.strip()
    for item in os.environ.get("YELLOW_AI_FETCH_VARIABLES", "").split(",")
    if item.strip()
][:5]

_working_endpoint = ""


def configured() -> bool:
    return bool(BOT_ID and API_KEY and BASE_URL)


def mask_secret(value: str) -> str:
    if not value:
        return "not configured"
    return "configured"


def endpoint_candidates() -> List[str]:
    if SYNC_URL:
        return [format_endpoint(SYNC_URL)]
    return [
        f"{BASE_URL}/api/integrations/send-message-event-to-bot",
        f"{BASE_URL}/api/engagements/bot/{BOT_ID}/messages",
        f"{BASE_URL}/api/engagements/bots/{BOT_ID}/messages",
    ]


def format_endpoint(url: str) -> str:
    return url.format(bot_id=BOT_ID, bot=BOT_ID, base_url=BASE_URL).rstrip()


def build_payload(prompt: str, sender: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "botId": BOT_ID,
        "sender": sender,
        "data": {
            "message": prompt,
            "source": "documenter",
            "channel": CHANNEL,
        },
        "message": prompt,
    }
    if FETCH_VARIABLES:
        payload["fetchVariables"] = FETCH_VARIABLES
    return payload


def request_headers() -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-api-key": API_KEY,
        "User-Agent": "yellow-ai-agent-documenter/1.0",
    }
    auth_scheme = os.environ.get("YELLOW_AI_AUTH_SCHEME", "").strip().lower()
    if auth_scheme == "bearer":
        headers["Authorization"] = f"Bearer {API_KEY}"
    return headers


def sender_for_prompt() -> str:
    if SENDER_STRATEGY == "session":
        return SENDER_ID
    return f"{SENDER_ID}_{uuid.uuid4().hex[:8]}"


def post_json(url: str, payload: Dict[str, Any], timeout: float) -> Tuple[int, Dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=request_headers(), method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
        if not raw:
            return response.status, {}
        try:
            return response.status, json.loads(raw)
        except json.JSONDecodeError:
            return response.status, {"raw_text": raw}


def ask_bot(prompt: str, delay: float = 1.5) -> Dict[str, Any]:
    if delay > 0:
        time.sleep(delay)

    if not configured():
        return {
            "input": prompt,
            "response": "YELLOW_AI_BOT_ID, YELLOW_AI_API_KEY, and YELLOW_AI_BASE_URL are required.",
            "success": False,
            "raw": {},
        }

    payload = build_payload(prompt, sender_for_prompt())
    errors = []
    global _working_endpoint
    candidates = [_working_endpoint] if _working_endpoint else endpoint_candidates()
    if _working_endpoint:
        candidates += [url for url in endpoint_candidates() if url != _working_endpoint]

    for endpoint in candidates:
        if not endpoint:
            continue
        try:
            status, data = post_json(endpoint, payload, timeout=float(os.environ.get("YELLOW_AI_TIMEOUT", "35")))
            text = extract_response_text(data)
            _working_endpoint = endpoint
            return {
                "input": prompt,
                "response": text or f"HTTP {status}: empty response body",
                "success": 200 <= status < 300 and bool(text or data),
                "raw": data,
                "endpoint": endpoint,
            }
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            errors.append(f"{endpoint} -> HTTP {exc.code}: {raw[:300]}")
        except Exception as exc:
            errors.append(f"{endpoint} -> {exc}")

    return {
        "input": prompt,
        "response": "All sync-message endpoint attempts failed. Set YELLOW_AI_SYNC_URL explicitly. " + " | ".join(errors),
        "success": False,
        "raw": {"errors": errors, "payload_shape": list(payload.keys())},
    }


def extract_response_text(data: Any) -> str:
    candidates: List[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key in ["text", "message", "body", "content", "reply", "response", "answer", "title"]:
                item = value.get(key)
                if isinstance(item, str) and item.strip():
                    candidates.append(item.strip())
            for item in value.values():
                if isinstance(item, (dict, list)):
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    unique = []
    seen = set()
    for text in candidates:
        normalized = " ".join(text.split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(text)
    return "\n\n".join(unique[:8])
