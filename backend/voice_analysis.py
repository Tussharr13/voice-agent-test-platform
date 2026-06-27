from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Tuple

from backend import workspace


FAILURE_HANGUPS = (
    "Bot Failure",
    "Bot response failure",
    "tts_error",
    "tts resource not available",
    "Message Loop Detected",
)

CONF_THRESHOLD = 0.85

CATEGORIES = {
    "intent_mismatch": {
        "label": "Intent Mismatch",
        "description": "The caller made a clear request, but the bot matched the wrong intent or fell back.",
    },
    "speech_recognition": {
        "label": "Speech Recognition",
        "description": "The speech-to-text layer produced low confidence or garbled user turns.",
    },
    "flow_interruption": {
        "label": "Flow Interruption",
        "description": "The bot looped, repeated a prompt, hit a trace failure, or stopped progressing.",
    },
    "voice_synthesis": {
        "label": "Voice Synthesis",
        "description": "The TTS/audio layer failed and the caller likely heard silence or an audio error.",
    },
    "early_termination": {
        "label": "Early Termination",
        "description": "The caller disconnected before the bot meaningfully engaged.",
    },
    "pending_deep_analysis": {
        "label": "Pending Deep Analysis",
        "description": "CDR shows a bot-side failure, but turn data or traces are missing.",
    },
}


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value in [None, ""]:
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value in [None, ""]:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def clean_text(value: Any, limit: int = 5000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def clean_date(value: Any) -> str:
    text = str(value or "").strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [text, text.replace("Z", "+00:00")]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            pass
    for fmt, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:size], fmt)
        except ValueError:
            pass
    return None


def short_flow(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.split("/")[-1]
    text = text.split(":")[-1]
    return text[:120]


def ensure_state_shape(state: Dict[str, Any]) -> bool:
    changed = False
    for key in ["voice_calls", "voice_sync_runs"]:
        if key not in state:
            state[key] = []
            changed = True
    return changed


def access_payload(
    state: Dict[str, Any],
    project_id: str,
    setting_value: Callable[[str, str], str],
) -> Dict[str, Any]:
    project = workspace.get_project(state, project_id)
    profile = project.get("bot_profile", {}) if isinstance(project.get("bot_profile"), dict) else {}
    secrets = state.setdefault("project_secrets", {}).get(project["id"], {})
    return {
        "project_id": project["id"],
        "bot_name": profile.get("voice_bot_name") or profile.get("bot_name") or "",
        "bot_id": profile.get("voice_bot_id") or profile.get("yellow_ai_bot_id") or "",
        "ui_base_url": profile.get("voice_ui_base_url") or profile.get("yellow_ai_ui_base_url") or "https://cloud.yellow.ai",
        "days_back": safe_int(profile.get("voice_days_back"), 7),
        "range_mode": profile.get("voice_range_mode") or ("custom" if profile.get("voice_date_from") and profile.get("voice_date_to") else "preset"),
        "date_from": profile.get("voice_date_from") or "",
        "date_to": profile.get("voice_date_to") or "",
        "api_key_configured": bool(secrets.get("VOICE_YELLOW_AI_API_KEY") or secrets.get("YELLOW_AI_API_KEY") or setting_value("YELLOW_AI_API_KEY", "")),
        "cookie_configured": bool(secrets.get("VOICE_YELLOW_AI_COOKIE") or setting_value("YELLOW_AI_COOKIE", "")),
    }


def update_access(state: Dict[str, Any], project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    project = workspace.get_project(state, project_id)
    profile = project.setdefault("bot_profile", {})
    if "bot_name" in payload:
        profile["voice_bot_name"] = clean_text(payload.get("bot_name"), 80)
    if "bot_id" in payload:
        bot_id = clean_text(payload.get("bot_id"), 80)
        profile["voice_bot_id"] = bot_id
        if bot_id and not profile.get("yellow_ai_bot_id"):
            profile["yellow_ai_bot_id"] = bot_id
    if "ui_base_url" in payload:
        profile["voice_ui_base_url"] = clean_text(payload.get("ui_base_url"), 180) or "https://cloud.yellow.ai"
    if "days_back" in payload:
        profile["voice_days_back"] = str(max(1, min(31, safe_int(payload.get("days_back"), 7))))
    if "range_mode" in payload:
        profile["voice_range_mode"] = "custom" if payload.get("range_mode") == "custom" else "preset"
    if "date_from" in payload:
        profile["voice_date_from"] = clean_date(payload.get("date_from"))
    if "date_to" in payload:
        profile["voice_date_to"] = clean_date(payload.get("date_to"))

    secrets = state.setdefault("project_secrets", {}).setdefault(project["id"], {})
    api_key = str(payload.get("api_key") or "").strip()
    cookie = str(payload.get("cookie") or "").strip()
    if api_key:
        secrets["VOICE_YELLOW_AI_API_KEY"] = api_key
    if cookie:
        secrets["VOICE_YELLOW_AI_COOKIE"] = cookie
    if payload.get("clear_api_key"):
        secrets.pop("VOICE_YELLOW_AI_API_KEY", None)
    if payload.get("clear_cookie"):
        secrets.pop("VOICE_YELLOW_AI_COOKIE", None)

    project["yellow_ai_target"] = workspace.yellow_ai_target(profile)
    project["updated_at"] = now_iso()
    return access_payload(state, project["id"], lambda key, default="": default)


def dashboard_payload(
    state: Dict[str, Any],
    project_id: str,
    setting_value: Callable[[str, str], str],
) -> Dict[str, Any]:
    ensure_state_shape(state)
    calls = sorted(
        workspace.filter_project_items(state.get("voice_calls", []), project_id),
        key=lambda item: str(item.get("started_at") or item.get("created_at") or ""),
        reverse=True,
    )
    sync_runs = sorted(
        workspace.filter_project_items(state.get("voice_sync_runs", []), project_id),
        key=lambda item: str(item.get("created_at") or ""),
        reverse=True,
    )
    reports = [
        report for report in workspace.filter_project_items(state.get("reports", []), project_id)
        if report.get("channel_filter") == "voice" or report.get("summary", {}).get("analysis_type") == "voice_call_analysis"
    ]
    return {
        "access": access_payload(state, project_id, setting_value),
        "summary": summarize_calls(calls),
        "calls": calls[:80],
        "sync_runs": sync_runs[:8],
        "reports": reports[:8],
        "categories": CATEGORIES,
        "failure_hangups": list(FAILURE_HANGUPS),
    }


def summarize_calls(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed = [call for call in calls if is_failed_call(call)]
    categorized = [call for call in failed if call.get("issues")]
    pending = [call for call in failed if call.get("classification_status") == "pending_deep_analysis"]
    category_counts: Dict[str, int] = {}
    for call in failed:
        for issue in call.get("issues", []):
            code = issue.get("category")
            if code:
                category_counts[code] = category_counts.get(code, 0) + 1
    unidentified = unidentified_utterances(calls)
    return {
        "total_calls": len(calls),
        "failed_calls": len(failed),
        "failure_rate": round((len(failed) / len(calls)) * 100, 1) if calls else 0,
        "categorized": len(categorized),
        "early_termination": category_counts.get("early_termination", 0),
        "pending_deep_analysis": len(pending),
        "category_counts": category_counts,
        "unidentified_turns": len(unidentified),
        "total_user_turns": sum(1 for call in calls for turn in call.get("turns", []) if turn.get("speaker") == "user"),
        "avg_low_confidence": round(sum(item.get("confidence", 0) for item in unidentified) / len(unidentified), 3) if unidentified else None,
    }


def unidentified_utterances(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for call in calls:
        for turn in call.get("turns", []):
            confidence = turn.get("confidence")
            if turn.get("speaker") != "user" or confidence in [None, ""]:
                continue
            conf = safe_float(confidence, 0)
            if 0 < conf < CONF_THRESHOLD:
                out.append(
                    {
                        "call_id": call.get("id"),
                        "text": turn.get("text"),
                        "confidence": conf,
                        "language": turn.get("stt_language") or "",
                        "flow": short_flow(turn.get("slug")),
                    }
                )
    return out


def is_failed_call(call: Dict[str, Any]) -> bool:
    return str(call.get("hangup_reason") or "") in FAILURE_HANGUPS or call.get("classification_status") in [
        "review",
        "pending_deep_analysis",
    ]


def sync_voice_calls(
    state: Dict[str, Any],
    project_id: str,
    payload: Dict[str, Any],
    setting_value: Callable[[str, str], str],
) -> Dict[str, Any]:
    ensure_state_shape(state)
    project = workspace.get_project(state, project_id)
    profile = project.get("bot_profile", {}) if isinstance(project.get("bot_profile"), dict) else {}
    secrets = state.setdefault("project_secrets", {}).get(project_id, {})

    bot_id = clean_text(payload.get("bot_id") or profile.get("voice_bot_id") or profile.get("yellow_ai_bot_id"), 80)
    if not bot_id:
        raise ValueError("Voice bot ID is required before syncing calls.")
    base_url = clean_text(payload.get("ui_base_url") or profile.get("voice_ui_base_url") or profile.get("yellow_ai_ui_base_url") or "https://cloud.yellow.ai", 180)
    api_key = str(payload.get("api_key") or secrets.get("VOICE_YELLOW_AI_API_KEY") or secrets.get("YELLOW_AI_API_KEY") or setting_value("YELLOW_AI_API_KEY", "")).strip()
    cookie = str(payload.get("cookie") or secrets.get("VOICE_YELLOW_AI_COOKIE") or setting_value("YELLOW_AI_COOKIE", "")).strip()
    if not api_key and not cookie:
        raise ValueError("Add a Yellow.ai API key or cookie before syncing voice calls.")

    window = resolve_sync_window(payload, profile)
    days_back = window["days_back"]
    max_records = max(1, min(5000, safe_int(payload.get("limit") or payload.get("max_records"), 1000)))
    page_size = max(1, min(500, safe_int(payload.get("page_size"), 250)))
    message_limit = max(0, min(30, safe_int(payload.get("message_limit"), 12)))
    failed_only = payload.get("failed_only") is True

    client = YellowVoiceClient(bot_id=bot_id, base_url=base_url, api_key=api_key, cookie=cookie)
    rows = client.fetch_cdr_rows(days_back=days_back, limit=max_records, page_size=page_size, failed_only=failed_only)
    calls = [normalize_cdr_row(row, project_id, bot_id) for row in rows]
    calls = [call for call in calls if call.get("id")]
    if window.get("date_from") and window.get("date_to"):
        calls = filter_calls_by_window(calls, window["start_at"], window["end_at"])

    messages_loaded = 0
    message_errors = []
    if cookie and message_limit:
        message_candidates = [call for call in calls if is_failed_call(call)] or calls
        for call in message_candidates[:message_limit]:
            uid = call.get("uid") or call.get("from_number")
            if not uid:
                continue
            try:
                messages = client.fetch_messages(str(uid), limit=200)
                turns = parse_turns(messages, call.get("id"))
                if turns:
                    call["turns"] = turns
                    messages_loaded += 1
            except Exception as exc:  # keep sync useful even with expired cookies
                message_errors.append(f"{call.get('id')}: {str(exc)[:140]}")
                call.setdefault("analysis_notes", []).append("Messages endpoint did not return turns. Refresh cookie and re-sync.")

    for call in calls:
        analyze_call(call)
        upsert_call(state, call)

    sync_run = build_sync_run(project_id, bot_id, window, calls, messages_loaded, message_errors)
    report, run = build_voice_report(project, sync_run, calls)
    state["voice_sync_runs"].insert(0, sync_run)
    state["reports"].insert(0, report)
    state["runs"].insert(0, run)

    profile["voice_bot_id"] = bot_id
    profile["voice_ui_base_url"] = base_url
    profile["voice_days_back"] = str(days_back)
    profile["voice_range_mode"] = window["mode"]
    if window.get("date_from"):
        profile["voice_date_from"] = window["date_from"]
    if window.get("date_to"):
        profile["voice_date_to"] = window["date_to"]
    if payload.get("bot_name"):
        profile["voice_bot_name"] = clean_text(payload.get("bot_name"), 80)
    project["updated_at"] = now_iso()

    return {
        "sync_run": sync_run,
        "report": report,
        "run": run,
        "voice": dashboard_payload(state, project_id, setting_value),
    }


def resolve_sync_window(payload: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    range_mode = str(payload.get("range_mode") or profile.get("voice_range_mode") or "").strip().lower()
    date_from_value = "" if range_mode == "preset" else payload.get("date_from") if "date_from" in payload else profile.get("voice_date_from")
    date_to_value = "" if range_mode == "preset" else payload.get("date_to") if "date_to" in payload else profile.get("voice_date_to")
    date_from = clean_date(date_from_value)
    date_to = clean_date(date_to_value)
    if range_mode == "custom" and not (date_from and date_to):
        raise ValueError("Select both start and end dates for custom voice sync.")
    if date_from and date_to:
        start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
        end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
        if end_date < start_date:
            raise ValueError("Voice sync end date must be on or after the start date.")
        selected_days = (end_date - start_date).days + 1
        if selected_days > 31:
            raise ValueError("Voice sync date range can cover up to 31 days at a time.")
        today = datetime.utcnow().date()
        days_back = max(1, min(31, (today - start_date).days + 1))
        start_at = datetime.combine(start_date, datetime.min.time())
        end_at = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        return {
            "mode": "custom",
            "date_from": date_from,
            "date_to": date_to,
            "start_at": start_at,
            "end_at": end_at,
            "days_back": days_back,
            "range_label": f"{date_from} to {date_to}",
        }
    days_back = max(1, min(31, safe_int(payload.get("days_back") or profile.get("voice_days_back"), 7)))
    return {
        "mode": "preset",
        "date_from": "",
        "date_to": "",
        "start_at": None,
        "end_at": None,
        "days_back": days_back,
        "range_label": f"last {days_back} day{'s' if days_back != 1 else ''}",
    }


def filter_calls_by_window(calls: List[Dict[str, Any]], start_at: datetime, end_at: datetime) -> List[Dict[str, Any]]:
    filtered = []
    for call in calls:
        started = parse_datetime(call.get("started_at") or call.get("created_at"))
        if not started:
            filtered.append(call)
            continue
        if start_at <= started < end_at:
            filtered.append(call)
    return filtered


class YellowVoiceClient:
    def __init__(self, bot_id: str, base_url: str, api_key: str = "", cookie: str = ""):
        self.bot_id = bot_id
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.cookie = cookie

    def fetch_cdr_rows(self, days_back: int, limit: int, page_size: int = 250, failed_only: bool = False) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        offset = 0
        while len(rows) < limit:
            current_limit = min(page_size, limit - len(rows))
            page = self.fetch_cdr_page(days_back=days_back, limit=current_limit, offset=offset, failed_only=failed_only)
            if not page:
                break
            rows.extend(page)
            if len(page) < current_limit:
                break
            offset += len(page)
        return rows

    def fetch_cdr_page(self, days_back: int, limit: int, offset: int = 0, failed_only: bool = False) -> List[Dict[str, Any]]:
        filters: List[Dict[str, Any]] = [
            {
                "type": "interval",
                "comparator": "previous",
                "operands": {
                    "_1": "start_time",
                    "_2": {"count": days_back, "type": "day", "includeCurrent": True},
                },
            }
        ]
        if failed_only:
            filters.append(
                {
                    "type": "in",
                    "comparator": "includes",
                    "operands": {"_1": "telco_text", "_2": list(FAILURE_HANGUPS)},
                }
            )
        body = {
            "dataSource": "cdr_reports",
            "datasetType": "default",
            "sourceType": "elasticsearch",
            "timeZone": "Asia/Kolkata",
            "type": "json",
            "json": {"filters": filters},
            "limit": limit,
            "offset": offset,
        }
        response = self._request_with_fallback("POST", "/api/insights/data-explorer", {"bot": self.bot_id}, body)
        return normalize_cdr_rows(response)

    def fetch_messages(self, uid: str, limit: int = 200) -> Dict[str, Any]:
        if not self.cookie:
            raise ValueError("Yellow.ai messages endpoint requires a cookie.")
        return self._request_json(
            "GET",
            "/api/agents/data/v3/messages",
            {
                "bot": self.bot_id,
                "uid": uid,
                "limit": str(limit),
                "showEvents": "true",
                "showMessageMetrics": "true",
                "source": "voice",
            },
            None,
            {"cookie": self.cookie},
        )

    def _request_with_fallback(
        self,
        method: str,
        path: str,
        params: Dict[str, str],
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        attempts: List[Dict[str, str]] = []
        if self.api_key:
            attempts.append({"x-api-key": self.api_key})
        if self.cookie:
            attempts.append({"cookie": self.cookie})
        last_error = ""
        for auth_headers in attempts:
            try:
                return self._request_json(method, path, params, body, auth_headers)
            except urllib.error.HTTPError as exc:
                last_error = exc.read().decode("utf-8", errors="ignore")[:260] or str(exc)
                if exc.code != 401:
                    raise ValueError(f"Yellow.ai API failed with HTTP {exc.code}: {last_error}") from exc
        raise ValueError(f"Yellow.ai API authentication failed: {last_error or 'no auth attempts succeeded'}")

    def _request_json(
        self,
        method: str,
        path: str,
        params: Dict[str, str],
        body: Dict[str, Any] | None,
        auth_headers: Dict[str, str],
    ) -> Dict[str, Any]:
        query = urllib.parse.urlencode(params)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "platform": "cloud",
            "origin": self.base_url,
            "user-agent": "Mozilla/5.0 VoiceBotObservability/1.0",
            **auth_headers,
        }
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=70) as response:
            return json.loads(response.read().decode("utf-8"))


def extract_rows(response: Dict[str, Any]) -> List[Any]:
    data = response.get("data", response)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["rows", "data", "results", "hits", "records", "profiles"]:
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def normalize_cdr_rows(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = response.get("data") or {}
    columns = data.get("columns") if isinstance(data, dict) else []
    column_names = []
    if isinstance(columns, list):
        for column in columns:
            if isinstance(column, dict):
                column_names.append(column.get("name") or column.get("displayName"))
    rows = extract_rows(response)
    if rows and isinstance(rows[0], list) and column_names:
        return [dict(zip(column_names, row)) for row in rows]
    return [row for row in rows if isinstance(row, dict)]


def first_value(row: Dict[str, Any], keys: Iterable[str], fallback: Any = "") -> Any:
    for key in keys:
        value = row.get(key)
        if value not in [None, ""]:
            return value
    return fallback


def normalize_cdr_row(row: Dict[str, Any], project_id: str, bot_id: str) -> Dict[str, Any]:
    call_id = str(first_value(row, ["sid", "CALL_ID", "call_id", "sessionId", "session_id"], "")).strip()
    if not call_id:
        call_id = f"voice_call_{uuid.uuid4().hex[:10]}"
    started_at = first_value(row, ["start_time", "CALL_START_TIME", "started_at", "createdAt"], "")
    ended_at = first_value(row, ["end_time", "CALL_END_TIME", "ended_at"], "")
    return {
        "id": call_id,
        "project_id": project_id,
        "bot_id": bot_id,
        "created_at": now_iso(),
        "started_at": str(started_at or ""),
        "ended_at": str(ended_at or ""),
        "uid": str(first_value(row, ["uid", "UID", "sender", "from_number"], "")),
        "from_number": str(first_value(row, ["from", "SOURCE_NUMBER", "from_number"], "")),
        "to_number": str(first_value(row, ["to", "DESTINATION_NUMBER", "to_number"], "")),
        "direction": str(first_value(row, ["direction", "DIRECTION"], "")),
        "status": str(first_value(row, ["status", "CALL_STATUS"], "")),
        "ring_duration_s": safe_int(first_value(row, ["ringing_duration", "RING_DURATION"], None), 0),
        "call_duration_s": safe_int(first_value(row, ["duration", "CALL_DURATION"], None), 0),
        "bot_duration_s": safe_int(first_value(row, ["voice_bot_duration", "VOICE_BOT_DURATION"], None), 0),
        "bill_duration_s": safe_int(first_value(row, ["voice_bot_bill_duration", "VOICE_BOT_BILL_DURATION"], None), 0),
        "hangup_reason": str(first_value(row, ["telco_text", "HANGUP_REASON", "hangup_reason"], "")),
        "hangup_source": str(first_value(row, ["disconnected_by", "HANGUP_SOURCE", "hangup_source"], "")),
        "recording_url": str(first_value(row, ["recording_url", "RECORDING_URL"], "")),
        "turns": [],
        "traces": [],
        "issues": [],
        "raw_cdr": compact_raw(row),
    }


def compact_raw(row: Dict[str, Any]) -> Dict[str, Any]:
    keep = [
        "sid",
        "uid",
        "start_time",
        "end_time",
        "duration",
        "voice_bot_duration",
        "telco_text",
        "disconnected_by",
        "status",
        "direction",
    ]
    return {key: row.get(key) for key in keep if key in row}


_TAG_RE = re.compile(r"<[^>]+>")


def strip_ssml(value: str) -> str:
    return clean_text(_TAG_RE.sub(" ", value or ""))


def message_rows(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = response.get("data") or response
    if isinstance(data, dict):
        for key in ["messages", "rows", "data", "results"]:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def parse_turns(response: Dict[str, Any], call_id: str) -> List[Dict[str, Any]]:
    turns = []
    for message in message_rows(response):
        if str(message.get("sessionId") or "") != str(call_id):
            continue
        parsed = parse_message(message)
        if parsed:
            turns.append(parsed)
    turns.sort(key=lambda item: str(item.get("timestamp") or ""))
    for index, turn in enumerate(turns, start=1):
        turn["turn"] = index
    return turns


def parse_message(message: Dict[str, Any]) -> Dict[str, Any] | None:
    message_type = str(message.get("messageType") or "").upper()
    additional = message.get("messageAdditionalData") if isinstance(message.get("messageAdditionalData"), dict) else {}
    raw = message.get("message") or ""
    speaker = ""
    text = ""
    confidence = None
    turn_type = ""
    stt_language = ""
    if message_type == "USER":
        speaker = "user"
        text = parse_user_text(raw, additional)
        confidence = additional.get("message_confidence")
        turn_type = str(additional.get("message_type") or "STT")[:32]
        stt_language = str(additional.get("stt_language") or "")[:16]
    elif message_type == "BOT":
        speaker = "bot"
        text = parse_bot_text(raw)
        turn_type = "BOT"
    elif message_type == "EVENT":
        speaker = "event"
        text = parse_event_text(raw)
        turn_type = "EVENT"
    else:
        return None
    return {
        "speaker": speaker,
        "text": text,
        "confidence": safe_float(confidence, None) if confidence not in [None, ""] else None,
        "message_type": turn_type,
        "stt_language": stt_language,
        "slug": str(message.get("slug") or "")[:200],
        "message_id": str(message.get("_id") or ""),
        "timestamp": str(message.get("created") or message.get("createdAt") or ""),
    }


def parse_user_text(raw: Any, additional: Dict[str, Any]) -> str:
    if isinstance(raw, str) and raw and not raw.lstrip().startswith("{"):
        return clean_text(raw)
    if isinstance(raw, str) and raw.lstrip().startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("message"):
                return clean_text(parsed.get("message"))
        except json.JSONDecodeError:
            pass
    return clean_text(additional.get("message"))


def parse_bot_text(raw: Any) -> str:
    if not raw:
        return ""
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return strip_ssml(str(parsed.get("message") or parsed.get("text") or ""))
        except json.JSONDecodeError:
            pass
        return strip_ssml(raw)
    return clean_text(raw)


def parse_event_text(raw: Any) -> str:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                event = parsed.get("event") if isinstance(parsed.get("event"), dict) else {}
                return clean_text(event.get("code") or parsed.get("code") or "")
        except json.JSONDecodeError:
            pass
    return clean_text(raw, 120)


def analyze_call(call: Dict[str, Any]) -> Dict[str, Any]:
    issues = []
    hangup = str(call.get("hangup_reason") or "")
    if safe_int(call.get("bot_duration_s"), 0) == 0 and safe_int(call.get("call_duration_s"), 0) <= 8:
        issues.append(issue("early_termination", "Caller disconnected before the bot had meaningful talk time."))
    if hangup in ["tts_error", "tts resource not available"]:
        issues.append(issue("voice_synthesis", f"CDR hangup reason is '{hangup}', which points to TTS/audio failure."))
    if hangup == "Message Loop Detected":
        issues.append(issue("flow_interruption", "Yellow.ai ended the call with Message Loop Detected."))

    turns = call.get("turns", []) if isinstance(call.get("turns"), list) else []
    issues.extend(rule_speech_recognition(turns))
    issues.extend(rule_flow_loop(turns))
    issues.extend(rule_intent_repeat(turns))

    deduped = []
    seen = set()
    for item in issues:
        key = (item.get("category"), item.get("evidence"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    call["issues"] = deduped
    if deduped:
        call["classification_status"] = "review"
        call["primary_issue"] = deduped[0]["category"]
        call["severity"] = severity_for(deduped)
        call["summary"] = summarize_call(call)
    elif hangup in ["Bot Failure", "Bot response failure"]:
        call["classification_status"] = "pending_deep_analysis"
        call["primary_issue"] = "pending_deep_analysis"
        call["severity"] = "Low"
        call["summary"] = (
            f"CDR hangup_reason='{hangup}' requires turn data/traces, but no deterministic signal is available yet. "
            "Refresh the Yellow.ai cookie and re-sync to fetch messages."
        )
    else:
        call["classification_status"] = "pass"
        call["primary_issue"] = ""
        call["severity"] = "Low"
        call["summary"] = "No bot-side failure signal found in the available CDR and turn data."
    call["language"] = infer_language(turns)
    return call


def issue(category: str, evidence: str) -> Dict[str, str]:
    return {"category": category, "label": CATEGORIES[category]["label"], "evidence": evidence}


def user_stt_turns(turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        turn for turn in turns
        if turn.get("speaker") == "user" and str(turn.get("message_type") or "STT").upper() == "STT"
    ]


def bot_turns(turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [turn for turn in turns if turn.get("speaker") == "bot"]


def rule_speech_recognition(turns: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    users = [turn for turn in user_stt_turns(turns) if turn.get("confidence") not in [None, ""]]
    if len(users) < 2:
        return []
    lows = [turn for turn in users if safe_float(turn.get("confidence"), 0) < CONF_THRESHOLD]
    if len(lows) / len(users) < 0.5:
        return []
    avg = sum(safe_float(turn.get("confidence"), 0) for turn in lows) / len(lows)
    return [issue("speech_recognition", f"{len(lows)}/{len(users)} user STT turns below {CONF_THRESHOLD}; average low confidence {avg:.2f}.")]


def rule_flow_loop(turns: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    slugs = [short_flow(turn.get("slug")) for turn in bot_turns(turns)]
    current = 1
    best = (1, "")
    for index in range(1, len(slugs)):
        if slugs[index] and slugs[index] == slugs[index - 1]:
            current += 1
            if current > best[0]:
                best = (current, slugs[index])
        else:
            current = 1
    if best[0] >= 3 and best[1]:
        return [issue("flow_interruption", f"Bot stayed on flow node '{best[1]}' for {best[0]} consecutive bot turns.")]
    return []


def rule_intent_repeat(turns: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    hits = []
    for index, turn in enumerate(turns):
        if turn.get("speaker") != "user" or safe_float(turn.get("confidence"), 1) < CONF_THRESHOLD:
            continue
        previous_bot = next((item for item in reversed(turns[:index]) if item.get("speaker") == "bot"), None)
        next_bot = next((item for item in turns[index + 1:] if item.get("speaker") == "bot"), None)
        if not previous_bot or not next_bot:
            continue
        previous_slug = short_flow(previous_bot.get("slug"))
        next_slug = short_flow(next_bot.get("slug"))
        if previous_slug and previous_slug == next_slug:
            hits.append(
                issue(
                    "intent_mismatch",
                    f"User said '{clean_text(turn.get('text'), 80)}' at high STT confidence, but bot stayed on '{previous_slug}'.",
                )
            )
    return hits[:3]


def severity_for(issues: List[Dict[str, str]]) -> str:
    categories = {item.get("category") for item in issues}
    if categories & {"voice_synthesis", "flow_interruption"}:
        return "High"
    if categories & {"intent_mismatch", "speech_recognition"}:
        return "Medium"
    return "Low"


def infer_language(turns: List[Dict[str, Any]]) -> str:
    langs = [str(turn.get("stt_language") or "").strip() for turn in user_stt_turns(turns) if turn.get("stt_language")]
    if not langs:
        return ""
    counts: Dict[str, int] = {}
    for lang in langs:
        counts[lang] = counts.get(lang, 0) + 1
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)[0][0]


def summarize_call(call: Dict[str, Any]) -> str:
    labels = ", ".join(item.get("label", item.get("category", "")) for item in call.get("issues", []))
    return (
        f"{labels} detected. Call lasted {call.get('call_duration_s', 0)}s, "
        f"bot duration {call.get('bot_duration_s', 0)}s, hangup reason '{call.get('hangup_reason', '')}'."
    )


def upsert_call(state: Dict[str, Any], call: Dict[str, Any]) -> None:
    calls = state.setdefault("voice_calls", [])
    for index, existing in enumerate(calls):
        if existing.get("id") == call.get("id") and existing.get("project_id") == call.get("project_id"):
            merged = {**existing, **call, "updated_at": now_iso()}
            calls[index] = merged
            return
    call["updated_at"] = now_iso()
    calls.insert(0, call)


def build_sync_run(
    project_id: str,
    bot_id: str,
    window: Dict[str, Any],
    calls: List[Dict[str, Any]],
    messages_loaded: int,
    message_errors: List[str],
) -> Dict[str, Any]:
    failed = [call for call in calls if is_failed_call(call)]
    pending = [call for call in failed if call.get("classification_status") == "pending_deep_analysis"]
    range_label = window.get("range_label") or f"last {window.get('days_back', 7)} days"
    return {
        "id": f"voice_sync_{uuid.uuid4().hex[:10]}",
        "project_id": project_id,
        "bot_id": bot_id,
        "created_at": now_iso(),
        "days_back": window.get("days_back", 7),
        "range_mode": window.get("mode", "preset"),
        "date_from": window.get("date_from", ""),
        "date_to": window.get("date_to", ""),
        "range_label": range_label,
        "calls_pulled": len(calls),
        "failed_calls": len(failed),
        "messages_loaded": messages_loaded,
        "pending_deep_analysis": len(pending),
        "status": "partial" if message_errors else "ok",
        "message": message_errors[0] if message_errors else f"Voice calls synced and analyzed for {range_label}.",
        "message_errors": message_errors[:5],
    }


def build_voice_report(
    project: Dict[str, Any],
    sync_run: Dict[str, Any],
    calls: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    failed = [call for call in calls if is_failed_call(call)]
    case_results = [case_from_call(call) for call in failed[:40]]
    scores = [safe_float(case.get("score", {}).get("overall_score"), 0) for case in case_results]
    average = round(sum(scores) / len(scores), 3) if scores else 1
    report_id = f"report_{uuid.uuid4().hex[:10]}"
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    report = {
        "id": report_id,
        "project_id": project["id"],
        "created_at": now_iso(),
        "suite_id": "",
        "run_id": run_id,
        "adapter": "yellow_ai_voice_analysis",
        "channel_filter": "voice",
        "summary": {
            "analysis_type": "voice_call_analysis",
            "bot_id": sync_run.get("bot_id"),
            "total_cases": len(case_results),
            "average_score": average,
            "status": "Review required" if case_results else "No failed calls",
            "pending_deep_analysis": sync_run.get("pending_deep_analysis", 0),
        },
        "case_results": case_results,
        "yellow_ai_recommendations": recommendations_for_calls(failed),
    }
    run = {
        "id": run_id,
        "project_id": project["id"],
        "created_at": now_iso(),
        "suite_id": "",
        "report_id": report_id,
        "adapter": "yellow_ai_voice_analysis",
        "channel_filter": "voice",
        "average_score": average,
        "total_cases": len(case_results),
    }
    return report, run


def case_from_call(call: Dict[str, Any]) -> Dict[str, Any]:
    status = "review" if call.get("classification_status") != "pass" else "pass"
    score = 0.2 if call.get("classification_status") == "pending_deep_analysis" else (0.35 if call.get("issues") else 1)
    return {
        "case_id": f"voice_{call.get('id')}",
        "channel": "voice",
        "flow_name": primary_flow(call),
        "scenario_type": call.get("primary_issue") or "voice_call",
        "persona": call.get("from_number") or "caller",
        "goal": "Complete the voice conversation without bot-side failure.",
        "expected_outcome": "The call should progress through the intended voice flow, preserve context, and close cleanly.",
        "result": {
            "adapter": "yellow_ai_voice_analysis",
            "adapter_status": call.get("classification_status"),
            "call_id": call.get("id"),
            "hangup_reason": call.get("hangup_reason"),
            "recording_url": call.get("recording_url"),
            "expected_response": "Successful voice flow completion or a controlled handoff/retry path.",
            "actual_response": call.get("summary"),
            "transcript": transcript_from_call(call),
        },
        "score": {
            "status": status,
            "overall_score": score,
            "issues": [item.get("evidence") for item in call.get("issues", [])] or [call.get("summary", "")],
            "metrics": {
                "call_duration_s": call.get("call_duration_s"),
                "bot_duration_s": call.get("bot_duration_s"),
                "hangup_reason": call.get("hangup_reason"),
                "severity": call.get("severity"),
            },
        },
        "yellow_ai": {"module": likely_module(call), "artifact_hint": artifact_hint(call)},
        "recommendations": recommendations_for_call(call),
    }


def transcript_from_call(call: Dict[str, Any]) -> List[Dict[str, Any]]:
    turns = call.get("turns") or []
    if turns:
        return turns
    return [
        {
            "turn": 1,
            "speaker": "system",
            "text": call.get("summary") or f"No turn data available. Hangup reason: {call.get('hangup_reason')}",
            "timestamp": call.get("started_at"),
        }
    ]


def primary_flow(call: Dict[str, Any]) -> str:
    for turn in call.get("turns", []):
        flow = short_flow(turn.get("slug"))
        if flow:
            return flow
    return call.get("hangup_reason") or "Voice call"


def likely_module(call: Dict[str, Any]) -> str:
    primary = call.get("primary_issue")
    if primary == "speech_recognition":
        return "Speech-to-text / Active Learning"
    if primary == "voice_synthesis":
        return "TTS / Voice provider"
    if primary == "flow_interruption":
        return "Voice workflow"
    if primary == "intent_mismatch":
        return "NLU intent routing"
    return "Conversation logs / traces"


def artifact_hint(call: Dict[str, Any]) -> str:
    flow = primary_flow(call)
    if call.get("primary_issue") == "pending_deep_analysis":
        return "Fetch Yellow.ai messages/traces for this call; cookie may be expired."
    if flow and flow != call.get("hangup_reason"):
        return f"Inspect Yellow.ai Studio voice flow node '{flow}' and call trace logs."
    return "Inspect Yellow.ai call logs, voice workflow, and provider error logs."


def recommendations_for_call(call: Dict[str, Any]) -> List[str]:
    primary = call.get("primary_issue")
    if primary == "speech_recognition":
        return [
            "Add low-confidence utterances to Active Learning/training data.",
            "Check STT language, model, and domain phrase hints for this voice bot.",
        ]
    if primary == "voice_synthesis":
        return [
            "Inspect TTS provider logs and Yellow.ai voice synthesis settings.",
            "Add a fallback audio/error branch if synthesis fails.",
        ]
    if primary == "flow_interruption":
        return [
            "Inspect the repeated/failing workflow node and add exit conditions.",
            "Rerun the same call path after fixing the loop or trace failure.",
        ]
    if primary == "intent_mismatch":
        return [
            "Review the matched intent/fallback route for the failed user utterance.",
            "Add training phrases or route guards for the high-confidence utterance.",
        ]
    return [
        "Refresh Yellow.ai cookie, re-sync messages/traces, and rerun analysis.",
        "Capture the call trace page for exact workflow/API failure evidence.",
    ]


def recommendations_for_calls(calls: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    by_category: Dict[str, int] = {}
    for call in calls:
        category = call.get("primary_issue") or "pending_deep_analysis"
        by_category[category] = by_category.get(category, 0) + 1
    recommendations = []
    for category, count in sorted(by_category.items(), key=lambda item: item[1], reverse=True):
        label = CATEGORIES.get(category, {}).get("label", category)
        recommendations.append(
            {
                "area": label,
                "recommendation": recommendation_for_category(category),
                "yellow_ai_hint": f"{count} call(s). {category_location(category)}",
                "channel": "voice",
            }
        )
    return recommendations[:8]


def recommendation_for_category(category: str) -> str:
    if category == "speech_recognition":
        return "Prioritize low-confidence utterances for STT/NLU training and language hint review."
    if category == "voice_synthesis":
        return "Fix TTS/provider failures and add controlled fallback handling for audio generation errors."
    if category == "flow_interruption":
        return "Inspect repeated workflow nodes, missing exit conditions, and trace failure nodes."
    if category == "intent_mismatch":
        return "Patch intent training and fallback routing for high-confidence user turns that do not progress."
    if category == "early_termination":
        return "Track separately as caller-side drop unless a pattern points to greeting latency or dead air."
    return "Fetch messages and traces so the Analyzer can pinpoint the exact workflow/API/function failure."


def category_location(category: str) -> str:
    if category == "speech_recognition":
        return "Yellow.ai Active Learning, user utterances, STT language/model configuration."
    if category == "voice_synthesis":
        return "Yellow.ai voice/TTS provider logs and synthesis settings."
    if category == "flow_interruption":
        return "Studio voice workflow, call trace, failing branch or loop node."
    if category == "intent_mismatch":
        return "NLU intents, route conditions, fallback branch, and conversation logs."
    return "Yellow.ai conversation messages and user-log traces."
