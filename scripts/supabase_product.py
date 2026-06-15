#!/usr/bin/env python3
"""
Seed/check the normalized Supabase product schema.

The app currently runs on the bridge table (bot_qa_state). This script migrates
that state into the product tables once a Supabase Auth user exists.
"""

import argparse
import json
import os
import secrets
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import storage  # noqa: E402
from backend import supabase_product as product_store  # noqa: E402


STATE_PATH = ROOT / "data" / "state.json"


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
        if key and value and key not in os.environ:
            os.environ[key] = value


def auth_url(path: str, query: str = "") -> str:
    config = storage.supabase_config()
    clean_path = path.lstrip("/")
    base = f"{config['url']}/auth/v1/{clean_path}"
    return f"{base}?{query}" if query else base


def request_auth(method: str, path: str, payload: Any = None, query: str = "") -> Any:
    data = None if payload is None else json.dumps(storage.sanitize_for_jsonb(payload)).encode("utf-8")
    request = urllib.request.Request(
        auth_url(path, query),
        data=data,
        headers=storage.supabase_headers(),
        method=method,
    )
    with urllib.request.urlopen(request, timeout=float(os.environ.get("SUPABASE_TIMEOUT", "25"))) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else None


def require_supabase() -> None:
    config = storage.supabase_config()
    if not config["url"] or not config["key"]:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env first.")


def load_state(source: str) -> Dict[str, Any]:
    if source == "supabase":
        state = storage.load_supabase_state()
        if state is None:
            raise SystemExit("No bridge state found in Supabase.")
        return state
    with STATE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def append_env_value(key: str, value: str) -> None:
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    prefix = f"{key}="
    next_line = f"{key}={value}"
    updated = False
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = next_line
            updated = True
            break
    if not updated:
        lines.append(next_line)
    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def generated_password() -> str:
    return f"BotQA-{secrets.token_urlsafe(24)}-2026"


def simplify_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "created_at": user.get("created_at"),
        "confirmed_at": user.get("confirmed_at") or user.get("email_confirmed_at"),
        "last_sign_in_at": user.get("last_sign_in_at"),
    }


def list_auth_users(save_first: bool = False) -> None:
    require_supabase()
    result = request_auth("GET", "admin/users", query="page=1&per_page=50")
    users = result.get("users", []) if isinstance(result, dict) else []
    simplified = [simplify_user(user) for user in users]
    if save_first and simplified:
        first = simplified[0]
        append_env_value("SUPABASE_APP_USER_ID", first["id"])
        if first.get("email"):
            append_env_value("SUPABASE_APP_USER_EMAIL", first["email"])
    print(json.dumps({"count": len(simplified), "saved_first": bool(save_first and simplified), "users": simplified}, indent=2))


def create_auth_user(
    email: str,
    password: str,
    full_name: str = "",
    save_env: bool = False,
    generate_password: bool = False,
) -> None:
    require_supabase()
    if generate_password and not password:
        password = generated_password()
    if not email or not password:
        raise SystemExit("Pass --email and --password, or use --generate-password, to create a Supabase Auth user.")
    payload = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"full_name": full_name} if full_name else {},
    }
    user = request_auth("POST", "admin/users", payload=payload)
    simplified = simplify_user(user or {})
    if save_env and simplified.get("id"):
        append_env_value("SUPABASE_APP_USER_ID", simplified["id"])
        append_env_value("SUPABASE_APP_USER_EMAIL", simplified.get("email") or email)
        if generate_password:
            append_env_value("SUPABASE_APP_USER_PASSWORD", password)
    print(
        json.dumps(
            {
                "created": simplified,
                "saved_env": bool(save_env),
                "generated_password": bool(generate_password),
                "password_saved_to_env": bool(save_env and generate_password),
            },
            indent=2,
        )
    )


def check() -> None:
    require_supabase()
    print(json.dumps(product_store.check_tables(), indent=2))


def seed(user_id: str, email: str, source: str) -> None:
    require_supabase()
    state = load_state(source)
    result = product_store.sync_state(state, user_id=user_id, email=email)
    result["source"] = source
    print(json.dumps(result, indent=2))


def main() -> None:
    load_env_file(ROOT / ".env")
    load_env_file(ROOT / ".env.example")

    parser = argparse.ArgumentParser(description="Manage normalized Supabase product tables")
    parser.add_argument("command", choices=["check", "users", "create-user", "seed"])
    parser.add_argument("--user-id", default=os.environ.get("SUPABASE_APP_USER_ID", ""))
    parser.add_argument("--email", default=os.environ.get("SUPABASE_APP_USER_EMAIL", ""))
    parser.add_argument("--password", default="")
    parser.add_argument("--full-name", default="")
    parser.add_argument("--save-env", action="store_true")
    parser.add_argument("--save-first", action="store_true")
    parser.add_argument("--generate-password", action="store_true")
    parser.add_argument("--source", choices=["supabase", "local"], default="supabase")
    args = parser.parse_args()

    if args.command == "check":
        check()
    elif args.command == "users":
        list_auth_users(save_first=args.save_first)
    elif args.command == "create-user":
        create_auth_user(
            args.email,
            args.password,
            full_name=args.full_name,
            save_env=args.save_env,
            generate_password=args.generate_password,
        )
    elif args.command == "seed":
        if not args.user_id:
            raise SystemExit("Pass --user-id <supabase-auth-user-uuid> or set SUPABASE_APP_USER_ID.")
        seed(args.user_id, args.email, args.source)


if __name__ == "__main__":
    main()
