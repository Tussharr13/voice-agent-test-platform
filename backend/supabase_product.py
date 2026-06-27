from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List

from backend import storage


NAMESPACE = uuid.UUID("33d9018d-3e13-4aef-8c4c-3b6d6b80fb3c")
REQUIRED_TABLES = [
    "profiles",
    "projects",
    "chats",
    "chat_messages",
    "documents",
    "change_plans",
    "test_suites",
    "test_cases",
    "test_runs",
    "reports",
    "voice_calls",
    "voice_sync_runs",
    "user_settings",
]
UPSERT_ORDER = [
    ("profiles", "id"),
    ("projects", "id"),
    ("chats", "id"),
    ("chat_messages", "id"),
    ("documents", "id"),
    ("change_plans", "id"),
    ("test_suites", "id"),
    ("test_cases", "id"),
    ("test_runs", "id"),
    ("reports", "id"),
    ("voice_calls", "id"),
    ("voice_sync_runs", "id"),
    ("user_settings", "user_id"),
]
OPTIONAL_SYNC_COLUMNS = {
    "projects": {"goal_test_brief", "goal_test_briefs"},
    "test_suites": {"app_suite_id"},
    "test_cases": {"app_case_id", "app_suite_id"},
    "test_runs": {"app_run_id", "app_suite_id", "app_report_id"},
    "reports": {"app_report_id", "app_run_id", "app_suite_id"},
}

_last_error = ""
_last_sync = ""


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def clean_timestamp(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        return text
    return text


def clean_date(value: Any) -> str | None:
    text = str(value or "").strip()[:10]
    return text if text else None


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value in [None, ""]:
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def config() -> Dict[str, str]:
    return {
        "user_id": os.environ.get("SUPABASE_APP_USER_ID", "").strip(),
        "email": os.environ.get("SUPABASE_APP_USER_EMAIL", "").strip(),
    }


def sync_enabled(user_id: str = "") -> bool:
    explicit = os.environ.get("SUPABASE_PRODUCT_SYNC", "").strip()
    if explicit:
        return storage.env_bool("SUPABASE_PRODUCT_SYNC", False)
    product = config()
    return bool(storage.supabase_enabled() and (user_id or product["user_id"]))


def public_status() -> Dict[str, Any]:
    product = config()
    return {
        "enabled": sync_enabled(),
        "configured": bool(product["user_id"]),
        "user_id_configured": bool(product["user_id"]),
        "email": product["email"],
        "tables": REQUIRED_TABLES,
        "last_sync": _last_sync,
        "last_error": _last_error,
    }


def coerce_user_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise ValueError("SUPABASE_APP_USER_ID must be a valid Supabase Auth user UUID.") from exc


def legacy_uuid(kind: str, legacy_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{legacy_id or 'missing'}"))


def table_url(table: str, query: str = "") -> str:
    supabase = storage.supabase_config()
    table_name = urllib.parse.quote(table, safe="")
    base = f"{supabase['url']}/rest/v1/{table_name}"
    return f"{base}?{query}" if query else base


def request_json(method: str, table: str, payload: Any = None, query: str = "", extra_headers: Dict[str, str] = None) -> Any:
    data = None if payload is None else json.dumps(storage.sanitize_for_jsonb(payload)).encode("utf-8")
    request = urllib.request.Request(
        table_url(table, query),
        data=data,
        headers=storage.supabase_headers(extra_headers or {}),
        method=method,
    )
    with urllib.request.urlopen(request, timeout=float(os.environ.get("SUPABASE_TIMEOUT", "25"))) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else None


def check_tables() -> Dict[str, str]:
    results: Dict[str, str] = {}
    for table in REQUIRED_TABLES:
        try:
            request_json("GET", table, query="select=*&limit=1")
            results[table] = "ok"
        except urllib.error.HTTPError as exc:
            results[table] = f"HTTP {exc.code}"
        except Exception as exc:
            results[table] = str(exc)
    return results


def chunked(items: List[Dict[str, Any]], size: int = 100) -> Iterable[List[Dict[str, Any]]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def clean_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in row.items() if value is not None}


def upsert(table: str, rows: List[Dict[str, Any]], conflict: str = "id") -> int:
    if not rows:
        return 0
    count = 0
    headers = {"Prefer": "resolution=merge-duplicates,return=minimal"}
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        cleaned = clean_row(row)
        group_key = "\x1f".join(sorted(cleaned.keys()))
        groups.setdefault(group_key, []).append(cleaned)
    for group_rows in groups.values():
        for batch in chunked(group_rows):
            query = f"on_conflict={urllib.parse.quote(conflict, safe=',')}"
            try:
                request_json("POST", table, batch, query=query, extra_headers=headers)
                count += len(batch)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                stripped_batch = strip_optional_columns(table, batch)
                if stripped_batch != batch and is_missing_optional_column_error(body):
                    request_json("POST", table, stripped_batch, query=query, extra_headers=headers)
                    count += len(stripped_batch)
                    continue
                raise RuntimeError(f"{table} upsert failed: HTTP {exc.code} {body[:1000]}") from exc
    return count


def strip_optional_columns(table: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    optional = OPTIONAL_SYNC_COLUMNS.get(table, set())
    if not optional:
        return rows
    return [{key: value for key, value in row.items() if key not in optional} for row in rows]


def is_missing_optional_column_error(body: str) -> bool:
    lower = body.lower()
    return "column" in lower and ("does not exist" in lower or "could not find" in lower)


def normalize_plan_status(status: str) -> str:
    value = (status or "pending").strip().lower()
    if value in {"approved"}:
        return "approved"
    if value in {"rejected"}:
        return "rejected"
    return "pending"


def project_id_map(state: Dict[str, Any]) -> Dict[str, str]:
    return {project["id"]: legacy_uuid("project", project["id"]) for project in state.get("projects", [])}


def fallback_project_id(mapping: Dict[str, str]) -> str:
    if mapping:
        return next(iter(mapping.values()))
    return legacy_uuid("project", "project_voice_agent_test_platform")


def build_rows(state: Dict[str, Any], user_id: str, email: str = "") -> Dict[str, List[Dict[str, Any]]]:
    user_id = coerce_user_id(user_id)
    project_map = project_id_map(state)
    default_project = fallback_project_id(project_map)
    doc_map = {doc["id"]: legacy_uuid("document", doc["id"]) for doc in state.get("documents", [])}
    suite_map = {suite["id"]: legacy_uuid("suite", suite["id"]) for suite in state.get("suites", [])}
    run_map = {run["id"]: legacy_uuid("run", run["id"]) for run in state.get("runs", [])}

    rows: Dict[str, List[Dict[str, Any]]] = {table: [] for table in REQUIRED_TABLES}
    rows["profiles"].append({"id": user_id, "email": email or None})
    rows["user_settings"].append({"user_id": user_id, "settings": state.get("settings", {})})

    for project in state.get("projects", []):
        rows["projects"].append(
            {
                "id": project_map[project["id"]],
                "user_id": user_id,
                "name": project.get("name") or "Untitled project",
                "description": project.get("description", ""),
                "bot_profile": project.get("bot_profile", {}),
                "yellow_ai_target": project.get("yellow_ai_target", {}),
                "goal_test_brief": project.get("goal_test_brief", {}),
                "goal_test_briefs": project.get("goal_test_briefs", []),
                "created_at": project.get("created_at"),
                "updated_at": project.get("updated_at"),
            }
        )

    for chat in state.get("chats", []):
        project_id = project_map.get(chat.get("project_id"), default_project)
        chat_id = legacy_uuid("chat", chat.get("id", ""))
        rows["chats"].append(
            {
                "id": chat_id,
                "user_id": user_id,
                "project_id": project_id,
                "title": chat.get("title") or "New chat",
                "mode": chat.get("mode") if chat.get("mode") in {"analyzer", "docs"} else "analyzer",
                "attached_artifacts": chat.get("attached_artifacts", {}),
                "created_at": chat.get("created_at"),
                "updated_at": chat.get("updated_at"),
            }
        )
        for index, message in enumerate(chat.get("messages", [])):
            message_id = message.get("id") or f"{chat.get('id')}_{index}"
            role = message.get("role") if message.get("role") in {"user", "assistant", "system"} else "user"
            rows["chat_messages"].append(
                {
                    "id": legacy_uuid("message", message_id),
                    "user_id": user_id,
                    "project_id": project_id,
                    "chat_id": chat_id,
                    "role": role,
                    "content": str(message.get("content", "")),
                    "metadata": {"legacy_id": message.get("id"), "legacy_chat_id": chat.get("id")},
                    "created_at": message.get("created_at") or chat.get("created_at"),
                }
            )

    for doc in state.get("documents", []):
        project_id = project_map.get(doc.get("project_id"), default_project)
        rows["documents"].append(
            {
                "id": doc_map[doc["id"]],
                "user_id": user_id,
                "project_id": project_id,
                "filename": doc.get("filename", "document"),
                "content_type": doc.get("content_type"),
                "size_bytes": int(doc.get("size_bytes", 0) or 0),
                "storage_path": doc.get("stored_path"),
                "text_preview": doc.get("text_preview", ""),
                "extracted_text": doc.get("extracted_text", ""),
                "analysis_status": doc.get("analysis_status", "uploaded"),
                "metadata": {
                    "legacy_id": doc.get("id"),
                    "text_length": doc.get("text_length"),
                    "last_plan_id": doc.get("last_plan_id"),
                },
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at") or doc.get("created_at"),
            }
        )

    for plan in state.get("change_plans", []):
        project_id = project_map.get(plan.get("project_id"), default_project)
        rows["change_plans"].append(
            {
                "id": legacy_uuid("plan", plan.get("id", "")),
                "user_id": user_id,
                "project_id": project_id,
                "document_id": doc_map.get(plan.get("document_id")),
                "title": plan.get("document_name") or "Change plan",
                "summary": plan.get("summary", ""),
                "status": normalize_plan_status(plan.get("status", "")),
                "suggested_changes": plan.get("suggested_changes", []),
                "suggested_test_cases": plan.get("suggested_test_cases", []),
                "execution_status": plan.get("execution_status"),
                "execution_note": plan.get("execution_note"),
                "approved_at": plan.get("approved_at"),
                "created_at": plan.get("created_at"),
                "updated_at": plan.get("updated_at") or plan.get("created_at"),
            }
        )

    for suite in state.get("suites", []):
        project_id = project_map.get(suite.get("project_id"), default_project)
        suite_id = suite_map[suite["id"]]
        test_cases = suite.get("test_cases", [])
        rows["test_suites"].append(
            {
                "id": suite_id,
                "app_suite_id": suite.get("id"),
                "user_id": user_id,
                "project_id": project_id,
                "name": suite.get("name") or "Test suite",
                "source": suite.get("source"),
                "bot_profile": suite.get("bot_profile", {}),
                "coverage_matrix": suite.get("coverage_matrix", {}),
                "metadata": {
                    "legacy_id": suite.get("id"),
                    "yellow_ai_target": suite.get("yellow_ai_target", {}),
                    "test_case_count": len(test_cases),
                },
                "created_at": suite.get("created_at"),
                "updated_at": suite.get("updated_at") or suite.get("created_at"),
            }
        )
        for case in test_cases:
            legacy_case_id = case.get("id") or f"{suite.get('id')}_{len(rows['test_cases'])}"
            rows["test_cases"].append(
                {
                    "id": legacy_uuid("case", f"{suite.get('id')}:{legacy_case_id}"),
                    "app_case_id": legacy_case_id,
                    "app_suite_id": suite.get("id"),
                    "user_id": user_id,
                    "project_id": project_id,
                    "suite_id": suite_id,
                    "name": case.get("name") or case.get("flow_name") or "Test case",
                    "channel": "chat",
                    "scenario_type": case.get("scenario_type"),
                    "persona": case.get("persona"),
                    "goal": case.get("goal"),
                    "steps": case.get("steps", []),
                    "expected_outcome": case.get("expected_outcome"),
                    "evaluator_instructions": case.get("instructions"),
                    "metrics": case.get("metrics", {}),
                    "yellow_ai": case.get("yellow_ai", {}),
                    "created_at": suite.get("created_at"),
                    "updated_at": suite.get("updated_at") or suite.get("created_at"),
                }
            )

    for run in state.get("runs", []):
        project_id = project_map.get(run.get("project_id"), default_project)
        rows["test_runs"].append(
            {
                "id": run_map[run["id"]],
                "app_run_id": run.get("id"),
                "app_suite_id": run.get("suite_id"),
                "app_report_id": run.get("report_id"),
                "user_id": user_id,
                "project_id": project_id,
                "suite_id": suite_map.get(run.get("suite_id")),
                "channel_filter": run.get("channel_filter", "all"),
                "status": run.get("status", "completed"),
                "average_score": run.get("average_score"),
                "total_cases": int(run.get("total_cases", 0) or 0),
                "run_summary": {"legacy_id": run.get("id"), "legacy_report_id": run.get("report_id")},
                "created_at": run.get("created_at"),
            }
        )

    for report in state.get("reports", []):
        project_id = project_map.get(report.get("project_id"), default_project)
        rows["reports"].append(
            {
                "id": legacy_uuid("report", report.get("id", "")),
                "app_report_id": report.get("id"),
                "app_run_id": report.get("run_id"),
                "app_suite_id": report.get("suite_id"),
                "user_id": user_id,
                "project_id": project_id,
                "run_id": run_map.get(report.get("run_id")),
                "suite_id": suite_map.get(report.get("suite_id")),
                "summary": report.get("summary", {}),
                "case_results": report.get("case_results", []),
                "yellow_ai_recommendations": report.get("yellow_ai_recommendations", []),
                "metadata": {"legacy_id": report.get("id")},
                "created_at": report.get("created_at"),
            }
        )

    for call in state.get("voice_calls", []):
        project_id = project_map.get(call.get("project_id"), default_project)
        rows["voice_calls"].append(
            {
                "id": legacy_uuid("voice_call", call.get("id", "")),
                "app_call_id": call.get("id"),
                "user_id": user_id,
                "project_id": project_id,
                "bot_id": call.get("bot_id"),
                "started_at": clean_timestamp(call.get("started_at")),
                "ended_at": clean_timestamp(call.get("ended_at")),
                "uid": call.get("uid"),
                "from_number": call.get("from_number"),
                "to_number": call.get("to_number"),
                "direction": call.get("direction"),
                "status": call.get("status"),
                "hangup_reason": call.get("hangup_reason"),
                "hangup_source": call.get("hangup_source"),
                "severity": call.get("severity"),
                "classification_status": call.get("classification_status"),
                "primary_issue": call.get("primary_issue"),
                "summary": call.get("summary"),
                "turns": call.get("turns", []),
                "traces": call.get("traces", []),
                "issues": call.get("issues", []),
                "raw_cdr": call.get("raw_cdr", {}),
                "metrics": {
                    "ring_duration_s": safe_int(call.get("ring_duration_s")),
                    "call_duration_s": safe_int(call.get("call_duration_s")),
                    "bot_duration_s": safe_int(call.get("bot_duration_s")),
                    "bill_duration_s": safe_int(call.get("bill_duration_s")),
                },
                "metadata": {
                    "legacy_id": call.get("id"),
                    "recording_url": call.get("recording_url"),
                    "analysis_notes": call.get("analysis_notes", []),
                    "language": call.get("language"),
                },
                "created_at": clean_timestamp(call.get("created_at")),
                "updated_at": clean_timestamp(call.get("updated_at") or call.get("created_at")),
            }
        )

    for sync_run in state.get("voice_sync_runs", []):
        project_id = project_map.get(sync_run.get("project_id"), default_project)
        rows["voice_sync_runs"].append(
            {
                "id": legacy_uuid("voice_sync", sync_run.get("id", "")),
                "app_sync_id": sync_run.get("id"),
                "user_id": user_id,
                "project_id": project_id,
                "bot_id": sync_run.get("bot_id"),
                "range_mode": sync_run.get("range_mode") or "preset",
                "date_from": clean_date(sync_run.get("date_from")),
                "date_to": clean_date(sync_run.get("date_to")),
                "range_label": sync_run.get("range_label"),
                "days_back": safe_int(sync_run.get("days_back"), 0) or None,
                "calls_pulled": safe_int(sync_run.get("calls_pulled")),
                "failed_calls": safe_int(sync_run.get("failed_calls")),
                "messages_loaded": safe_int(sync_run.get("messages_loaded")),
                "pending_deep_analysis": safe_int(sync_run.get("pending_deep_analysis")),
                "status": sync_run.get("status") or "ok",
                "message": sync_run.get("message"),
                "message_errors": sync_run.get("message_errors", []),
                "metadata": {"legacy_id": sync_run.get("id")},
                "created_at": clean_timestamp(sync_run.get("created_at")),
            }
        )

    return rows


def sync_state(state: Dict[str, Any], user_id: str = "", email: str = "") -> Dict[str, Any]:
    product = config()
    owner_id = user_id or product["user_id"]
    if not owner_id:
        raise ValueError("SUPABASE_APP_USER_ID is required for product-table sync.")
    rows = build_rows(state, owner_id, email or product["email"])
    counts = {}
    for table, conflict in UPSERT_ORDER:
        counts[table] = upsert(table, rows[table], conflict=conflict)
    global _last_error, _last_sync
    _last_error = ""
    _last_sync = now_iso()
    return {"ok": True, "user_id": owner_id, "counts": counts, "synced_at": _last_sync}


def sync_state_if_enabled(state: Dict[str, Any], user_id: str = "", email: str = "") -> None:
    if not sync_enabled(user_id=user_id):
        return
    try:
        sync_state(state, user_id=user_id, email=email)
    except Exception as exc:
        remember_error(exc)
        if storage.env_bool("SUPABASE_PRODUCT_STRICT", False):
            raise


def remember_error(exc: Exception) -> None:
    global _last_error
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read().decode("utf-8", errors="replace")[:500]
        _last_error = f"HTTP {exc.code}: {body}"
    else:
        _last_error = str(exc)[:500]
    print(f"[product-sync] Supabase product sync skipped: {_last_error}")
