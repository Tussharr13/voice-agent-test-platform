#!/usr/bin/env python3
"""
Supabase state helper for the Bot QA Workbench.

This does not create tables. First run supabase/schema.sql in Supabase SQL
editor, then use this helper to inspect, seed, or pull the app state row.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import storage  # noqa: E402


STATE_PATH = ROOT / "data" / "state.json"
BRIDGE_SCHEMA_PATH = ROOT / "supabase" / "schema.sql"
PRODUCT_SCHEMA_PATH = ROOT / "supabase" / "product_schema.sql"


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


def require_supabase() -> None:
    config = storage.supabase_config()
    missing = [key for key in ["url", "key"] if not config[key]]
    if missing:
        raise SystemExit(
            "Supabase is not configured. Set SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY in .env first."
        )


def read_local_state() -> dict:
    if not STATE_PATH.exists():
        raise SystemExit(f"Local state not found: {STATE_PATH}")
    with STATE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def status() -> None:
    print(json.dumps(storage.public_status(STATE_PATH), indent=2))


def print_schema(product: bool = False) -> None:
    path = PRODUCT_SCHEMA_PATH if product else BRIDGE_SCHEMA_PATH
    print(path.read_text(encoding="utf-8"))


def seed() -> None:
    require_supabase()
    state = read_local_state()
    storage.save_supabase_state(state)
    print(
        json.dumps(
            {
                "ok": True,
                "action": "seed",
                "state_id": storage.supabase_config()["state_id"],
                "projects": len(state.get("projects", [])),
                "chats": len(state.get("chats", [])),
                "suites": len(state.get("suites", [])),
                "runs": len(state.get("runs", [])),
                "reports": len(state.get("reports", [])),
            },
            indent=2,
        )
    )


def pull(output: str) -> None:
    require_supabase()
    state = storage.load_supabase_state()
    if state is None:
        raise SystemExit("No Supabase state row found.")
    target = Path(output).expanduser() if output else STATE_PATH.with_suffix(".from_supabase.json")
    if not target.is_absolute():
        target = ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    print(json.dumps({"ok": True, "action": "pull", "output": str(target)}, indent=2))


def main() -> None:
    load_env_file(ROOT / ".env")
    load_env_file(ROOT / ".env.example")

    parser = argparse.ArgumentParser(description="Manage Bot QA Supabase state")
    parser.add_argument("command", choices=["status", "schema", "product-schema", "seed", "pull"])
    parser.add_argument("--output", default="", help="Output path for pull command")
    args = parser.parse_args()

    if args.command == "status":
        status()
    elif args.command == "schema":
        print_schema()
    elif args.command == "product-schema":
        print_schema(product=True)
    elif args.command == "seed":
        seed()
    elif args.command == "pull":
        pull(args.output)


if __name__ == "__main__":
    main()
