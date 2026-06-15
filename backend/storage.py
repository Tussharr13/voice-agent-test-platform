import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional


_last_error = ""


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def supabase_config(state_id: str = "") -> Dict[str, str]:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return {
        "url": os.environ.get("SUPABASE_URL", "").strip().rstrip("/"),
        "key": key,
        "table": os.environ.get("SUPABASE_TABLE", "bot_qa_state").strip() or "bot_qa_state",
        "state_id": state_id or os.environ.get("SUPABASE_STATE_ID", "default").strip() or "default",
    }


def supabase_enabled() -> bool:
    config = supabase_config()
    explicit = os.environ.get("SUPABASE_ENABLED", "").strip()
    if explicit:
        return env_bool("SUPABASE_ENABLED", False)
    return bool(config["url"] and config["key"])


def public_status(state_path: Path) -> Dict[str, Any]:
    config = supabase_config()
    configured = bool(config["url"] and config["key"])
    enabled = supabase_enabled()
    status = {
        "provider": "supabase" if enabled else "local_json",
        "configured": True,
        "enabled": enabled,
        "supabase_configured": configured,
        "url_configured": bool(config["url"]),
        "key_configured": bool(config["key"]),
        "table": config["table"] if configured else "",
        "state_id": config["state_id"] if configured else "",
        "local_path": str(state_path),
        "last_error": _last_error,
    }
    try:
        from backend import supabase_product

        status["product"] = supabase_product.public_status()
    except Exception as exc:
        status["product"] = {"enabled": False, "configured": False, "last_error": str(exc)[:500]}
    return status


def load_state(
    state_path: Path,
    default_factory: Callable[[], Dict[str, Any]],
    state_id: str = "",
    seed_from_default: bool = False,
) -> Dict[str, Any]:
    if supabase_enabled():
        try:
            state = load_supabase_state(state_id=state_id)
            if state is not None:
                return state
            if state_id and seed_from_default:
                default_row = load_supabase_state()
                if default_row is not None:
                    save_supabase_state(default_row, state_id=state_id)
                    return default_row
            seed = default_factory() if state_id else load_local_state(state_path, default_factory)
            save_supabase_state(seed, state_id=state_id)
            return seed
        except Exception as exc:
            remember_error(exc)
            if env_bool("SUPABASE_STRICT", False):
                raise
    return load_local_state(state_path, default_factory)


def save_state(
    state_path: Path,
    state: Dict[str, Any],
    state_id: str = "",
    user_id: str = "",
    user_email: str = "",
) -> None:
    if supabase_enabled():
        try:
            save_supabase_state(state, state_id=state_id)
            from backend import supabase_product

            supabase_product.sync_state_if_enabled(state, user_id=user_id, email=user_email)
            return
        except Exception as exc:
            remember_error(exc)
            if env_bool("SUPABASE_STRICT", False):
                raise
    save_local_state(state_path, state)


def load_local_state(state_path: Path, default_factory: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    state_path.parent.mkdir(exist_ok=True)
    if not state_path.exists():
        return default_factory()
    with state_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_local_state(state_path: Path, state: Dict[str, Any]) -> None:
    state_path.parent.mkdir(exist_ok=True)
    tmp_path = state_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    tmp_path.replace(state_path)


def supabase_headers(extra: Dict[str, str] = None) -> Dict[str, str]:
    config = supabase_config()
    headers = {
        "apikey": config["key"],
        "Authorization": f"Bearer {config['key']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def supabase_table_url(query: str = "", state_id: str = "") -> str:
    config = supabase_config(state_id=state_id)
    table = urllib.parse.quote(config["table"], safe="")
    base = f"{config['url']}/rest/v1/{table}"
    return f"{base}?{query}" if query else base


def load_supabase_state(state_id: str = "") -> Optional[Dict[str, Any]]:
    config = supabase_config(state_id=state_id)
    state_id = urllib.parse.quote(config["state_id"], safe="")
    query = f"id=eq.{state_id}&select=data"
    request = urllib.request.Request(supabase_table_url(query, state_id=config["state_id"]), headers=supabase_headers(), method="GET")
    with urllib.request.urlopen(request, timeout=float(os.environ.get("SUPABASE_TIMEOUT", "20"))) as response:
        rows = json.loads(response.read().decode("utf-8") or "[]")
    if not rows:
        return None
    data = rows[0].get("data", {})
    if not isinstance(data, dict):
        raise ValueError("Supabase state row data must be a JSON object")
    return data


def save_supabase_state(state: Dict[str, Any], state_id: str = "") -> None:
    config = supabase_config(state_id=state_id)
    payload = [
        {
            "id": config["state_id"],
            "data": sanitize_for_jsonb(state),
            "updated_at": now_iso(),
        }
    ]
    body = json.dumps(payload).encode("utf-8")
    query = "on_conflict=id"
    headers = supabase_headers({"Prefer": "resolution=merge-duplicates,return=minimal"})
    request = urllib.request.Request(supabase_table_url(query, state_id=config["state_id"]), data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=float(os.environ.get("SUPABASE_TIMEOUT", "20"))) as response:
        if response.status not in {200, 201, 204}:
            raise RuntimeError(f"Supabase save failed with HTTP {response.status}")


def remember_error(exc: Exception) -> None:
    global _last_error
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read().decode("utf-8", errors="replace")[:500]
        _last_error = f"HTTP {exc.code}: {body}"
    else:
        _last_error = str(exc)[:500]
    print(f"[storage] Supabase unavailable, using local state fallback: {_last_error}")


def sanitize_for_jsonb(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [sanitize_for_jsonb(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize_for_jsonb(item) for key, item in value.items()}
    return value
