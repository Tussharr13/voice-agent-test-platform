import json
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

from backend import failure_diagnosis


DEFAULT_PROJECT_ID = "project_voice_agent_test_platform"
DEFAULT_PROJECT_NAME = "Yellow.ai Chat QA Workbench"
PROJECT_ACCESS_PROFILE_KEYS = {
    "yellow_ai_bot_id": "bot_id",
    "yellow_ai_environment": "environment",
    "yellow_ai_ui_base_url": "ui_base_url",
    "yellow_ai_console_url": "console_url",
    "chat_endpoint": "chat_widget_url",
}


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "item"


def yellow_ai_context(profile: Dict[str, Any]) -> Dict[str, str]:
    return {
        "platform": str(profile.get("yellow_ai_platform", "nexus")).strip() or "nexus",
        "bot_id": str(profile.get("yellow_ai_bot_id", "")).strip(),
        "environment": str(profile.get("yellow_ai_environment", "")).strip(),
        "super_agent": str(profile.get("yellow_ai_super_agent", "")).strip(),
        "agent_name": str(profile.get("yellow_ai_agent_name", "")).strip(),
        "workflow_name": str(profile.get("yellow_ai_workflow_name", "")).strip(),
        "workflow_id": str(profile.get("yellow_ai_workflow_id", "")).strip(),
        "tool_name": str(profile.get("yellow_ai_tool_name", "")).strip(),
        "kb_name": str(profile.get("yellow_ai_kb_name", "")).strip(),
    }


def yellow_ai_target(profile: Dict[str, Any]) -> Dict[str, str]:
    return {key: value for key, value in yellow_ai_context(profile).items() if value}


def normalize_bot_profile(profile: Dict[str, Any]) -> bool:
    changed = False
    for key in ["channels", "bot_phone_number", "phone_number"]:
        if key in profile:
            profile.pop(key, None)
            changed = True
    return changed


def ensure_state_shape(state: Dict[str, Any]) -> bool:
    changed = False
    for key, default in [
        ("suites", []),
        ("runs", []),
        ("reports", []),
        ("settings", {}),
        ("documents", []),
        ("change_plans", []),
        ("platform_snapshots", []),
        ("bot_discoveries", []),
        ("project_secrets", {}),
        ("voice_calls", []),
        ("voice_sync_runs", []),
        ("projects", []),
        ("chats", []),
    ]:
        if key not in state:
            state[key] = default.copy() if isinstance(default, (dict, list)) else default
            changed = True

    if not state["projects"]:
        state["projects"].append(build_default_project(state))
        changed = True

    default_project_id = state["projects"][0].get("id") or DEFAULT_PROJECT_ID
    if state["projects"][0].get("id") != default_project_id:
        state["projects"][0]["id"] = default_project_id
        changed = True

    for project in state["projects"]:
        project.setdefault("created_at", now_iso())
        project.setdefault("updated_at", project.get("created_at", now_iso()))
        project.setdefault("bot_profile", {})
        if normalize_bot_profile(project["bot_profile"]):
            changed = True
        project.setdefault("yellow_ai_target", yellow_ai_target(project.get("bot_profile", {})))
        project.setdefault("goal_test_brief", {})
        project.setdefault("goal_test_briefs", [])
        project.setdefault("description", "Shared workspace for analyzer chats, tests, docs, and reports.")
        if project.get("id") == DEFAULT_PROJECT_ID and project.get("name") == "voice-agent-test-platform":
            project["name"] = DEFAULT_PROJECT_NAME
            changed = True

    for collection in ["suites", "runs", "reports", "documents", "change_plans", "platform_snapshots", "bot_discoveries", "voice_calls", "voice_sync_runs"]:
        for item in state.get(collection, []):
            if "project_id" not in item:
                item["project_id"] = default_project_id
                changed = True

    for suite in state.get("suites", []):
        if isinstance(suite.get("bot_profile"), dict) and normalize_bot_profile(suite["bot_profile"]):
            changed = True
        for case in suite.get("test_cases", []):
            if isinstance(case.get("test_profile"), dict) and "channel" in case["test_profile"] and case.get("channel") == "chat":
                case["test_profile"].pop("channel", None)
                changed = True

    for chat in state.get("chats", []):
        if "project_id" not in chat:
            chat["project_id"] = default_project_id
            changed = True
        chat.setdefault("mode", "analyzer")
        chat.setdefault("messages", [])
        chat.setdefault("attached_artifacts", {"documents": [], "suites": [], "reports": [], "change_plans": []})
    return changed


def build_default_project(state: Dict[str, Any]) -> Dict[str, Any]:
    profile: Dict[str, Any] = {}
    for suite in state.get("suites", []):
        if suite.get("bot_profile"):
            profile = dict(suite["bot_profile"])
            break
    if not profile:
        profile = {
            "bot_name": "Yellow.ai Support Bot",
            "business_goal": "Help users resolve support requests without needing a human agent unless the issue is complex.",
            "flow_docs": "Order status, cancel order, refund status, complaint, agent handoff, fallback recovery.",
            "yellow_ai_platform": "nexus",
        }
    timestamp = now_iso()
    return {
        "id": DEFAULT_PROJECT_ID,
        "name": DEFAULT_PROJECT_NAME,
        "description": "Default project migrated from the original local dashboard.",
        "bot_profile": profile,
        "yellow_ai_target": yellow_ai_target(profile),
        "goal_test_brief": {},
        "goal_test_briefs": [],
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def resolve_project_id(state: Dict[str, Any], project_id: str = "") -> str:
    ensure_state_shape(state)
    if project_id and any(project.get("id") == project_id for project in state["projects"]):
        return project_id
    return state["projects"][0]["id"]


def get_project(state: Dict[str, Any], project_id: str = "") -> Dict[str, Any]:
    resolved = resolve_project_id(state, project_id)
    return next(project for project in state["projects"] if project["id"] == resolved)


def filter_project_items(items: List[Dict[str, Any]], project_id: str) -> List[Dict[str, Any]]:
    return [item for item in items if item.get("project_id") == project_id]


def update_project_profile(state: Dict[str, Any], project_id: str, profile: Dict[str, Any]) -> None:
    if not isinstance(profile, dict) or not profile:
        return
    project = get_project(state, project_id)
    project["bot_profile"] = profile
    project["yellow_ai_target"] = yellow_ai_target(profile)
    project["updated_at"] = now_iso()


def apply_bot_discovery(state: Dict[str, Any], project_id: str, discovery: Dict[str, Any]) -> Dict[str, Any]:
    project = get_project(state, project_id)
    discovery["project_id"] = project["id"]
    profile = dict(project.get("bot_profile", {}))
    for key, value in discovery.get("profile_patch", {}).items():
        if value not in ["", [], {}]:
            profile[key] = value
    normalize_bot_profile(profile)
    project["bot_profile"] = profile
    project["yellow_ai_target"] = yellow_ai_target(profile)
    project["bot_discovery"] = {
        "id": discovery.get("id", ""),
        "created_at": discovery.get("created_at", ""),
        "summary": discovery.get("summary", ""),
        "snapshot_id": discovery.get("snapshot_id", ""),
        "recommended_tests": discovery.get("recommended_tests", []),
    }
    project["updated_at"] = now_iso()
    state.setdefault("bot_discoveries", []).insert(0, discovery)
    state["bot_discoveries"] = state["bot_discoveries"][:20]
    return project


def create_project(state: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    name = str(payload.get("name") or "Untitled project").strip()[:80] or "Untitled project"
    profile = payload.get("bot_profile") if isinstance(payload.get("bot_profile"), dict) else {}
    timestamp = now_iso()
    project = {
        "id": f"project_{uuid.uuid4().hex[:10]}",
        "name": name,
        "description": str(payload.get("description") or "").strip(),
        "bot_profile": profile,
        "yellow_ai_target": yellow_ai_target(profile),
        "goal_test_brief": {},
        "goal_test_briefs": [],
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    state["projects"].insert(0, project)
    return project


def update_project(state: Dict[str, Any], project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    project = get_project(state, project_id)
    if "name" in payload:
        project["name"] = str(payload.get("name") or project["name"]).strip()[:80] or project["name"]
    if "description" in payload:
        project["description"] = str(payload.get("description") or "").strip()
    if isinstance(payload.get("bot_profile"), dict):
        project["bot_profile"] = payload["bot_profile"]
        project["yellow_ai_target"] = yellow_ai_target(payload["bot_profile"])
    project["updated_at"] = now_iso()
    return project


def project_access_payload(state: Dict[str, Any], project_id: str = "") -> Dict[str, Any]:
    project = get_project(state, project_id)
    profile = project.get("bot_profile", {})
    secrets = state.setdefault("project_secrets", {}).get(project["id"], {})
    return {
        "project_id": project["id"],
        "bot_id": str(profile.get("yellow_ai_bot_id", "")).strip(),
        "environment": str(profile.get("yellow_ai_environment", "")).strip(),
        "ui_base_url": str(profile.get("yellow_ai_ui_base_url", "https://cloud.yellow.ai")).strip() or "https://cloud.yellow.ai",
        "console_url": str(profile.get("yellow_ai_console_url", "")).strip(),
        "chat_widget_url": str(profile.get("chat_endpoint", "")).strip(),
        "api_key_configured": bool(str(secrets.get("YELLOW_AI_API_KEY", "")).strip()),
    }


def update_project_access(state: Dict[str, Any], project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    project = get_project(state, project_id)
    profile = project.setdefault("bot_profile", {})
    for profile_key, payload_key in PROJECT_ACCESS_PROFILE_KEYS.items():
        if payload_key in payload:
            profile[profile_key] = str(payload.get(payload_key) or "").strip()
    if not profile.get("yellow_ai_ui_base_url"):
        profile["yellow_ai_ui_base_url"] = "https://cloud.yellow.ai"
    api_key = str(payload.get("api_key") or "").strip()
    if api_key:
        state.setdefault("project_secrets", {}).setdefault(project["id"], {})["YELLOW_AI_API_KEY"] = api_key
    if payload.get("clear_api_key"):
        state.setdefault("project_secrets", {}).setdefault(project["id"], {}).pop("YELLOW_AI_API_KEY", None)
    project["yellow_ai_target"] = yellow_ai_target(profile)
    project["updated_at"] = now_iso()
    return project_access_payload(state, project["id"])


def create_chat(state: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    project_id = resolve_project_id(state, str(payload.get("project_id", "")))
    mode = str(payload.get("mode") or "analyzer").strip().lower()
    if mode not in ["analyzer", "docs"]:
        mode = "analyzer"
    title = str(payload.get("title") or ("Docs chat" if mode == "docs" else "New analysis chat")).strip()[:90]
    timestamp = now_iso()
    chat = {
        "id": f"chat_{uuid.uuid4().hex[:10]}",
        "project_id": project_id,
        "mode": mode,
        "title": title,
        "messages": [],
        "attached_artifacts": {"documents": [], "suites": [], "reports": [], "change_plans": []},
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    state["chats"].insert(0, chat)
    return chat


def delete_chat(state: Dict[str, Any], project_id: str, chat_id: str) -> Dict[str, Any]:
    resolved_project_id = resolve_project_id(state, project_id)
    for index, chat in enumerate(state.get("chats", [])):
        if chat.get("id") == chat_id and chat.get("project_id") == resolved_project_id:
            return state["chats"].pop(index)
    raise ValueError("Chat not found")


def add_chat_message(
    state: Dict[str, Any],
    chat_id: str,
    content: str,
    setting_value: Callable[[str, str], str],
    rubric: List[str],
    root: Path,
) -> Dict[str, Any]:
    content = str(content or "").strip()
    if not content:
        raise ValueError("Message content is required")
    chat = next((item for item in state["chats"] if item["id"] == chat_id), None)
    if not chat:
        raise ValueError("Chat not found")

    project = get_project(state, chat.get("project_id", ""))
    user_message = {"id": f"msg_{uuid.uuid4().hex[:8]}", "role": "user", "content": content, "created_at": now_iso()}
    chat["messages"].append(user_message)
    remember_report_mentions(chat, content)

    assistant_text = openai_chat_response(chat, project, state, setting_value, rubric, root)
    assistant_message = {
        "id": f"msg_{uuid.uuid4().hex[:8]}",
        "role": "assistant",
        "content": assistant_text,
        "created_at": now_iso(),
    }
    chat["messages"].append(assistant_message)
    if chat["title"] in ["New analysis chat", "Docs chat", "New chat"]:
        chat["title"] = make_chat_title(content)
    chat["updated_at"] = now_iso()
    return chat


def prepare_goal_test_brief(
    state: Dict[str, Any],
    project_id: str,
    setting_value: Callable[[str, str], str],
    rubric: List[str],
    root: Path,
    chat_id: str = "",
    instruction: str = "",
) -> Dict[str, Any]:
    project = get_project(state, project_id)
    chat = next(
        (
            item
            for item in state.get("chats", [])
            if item.get("id") == chat_id and item.get("project_id") == project["id"] and item.get("mode") == "analyzer"
        ),
        None,
    )
    if chat is None:
        chat = next(
            (
                item
                for item in state.get("chats", [])
                if item.get("project_id") == project["id"] and item.get("mode") == "analyzer"
            ),
            {"id": "", "mode": "analyzer", "project_id": project["id"], "messages": [], "attached_artifacts": {}},
        )

    brief = openai_goal_test_brief(chat, project, state, setting_value, rubric, root, instruction)
    timestamp = now_iso()
    normalized = {
        "id": f"goal_brief_{uuid.uuid4().hex[:10]}",
        "project_id": project["id"],
        "title": str(brief.get("title") or "Analyzer goal-driven test brief").strip()[:90],
        "goal": str(brief.get("goal") or "").strip(),
        "constraints": str(brief.get("constraints") or "").strip(),
        "test_data": str(brief.get("test_data") or "").strip(),
        "success_criteria": str(brief.get("success_criteria") or "").strip(),
        "max_turns": clamp_int(brief.get("max_turns"), 2, 20, 10),
        "reasoning": str(brief.get("reasoning") or "").strip(),
        "source_artifacts": [str(item)[:160] for item in brief.get("source_artifacts", []) if str(item).strip()][:10],
        "source_chat_id": chat.get("id", ""),
        "created_at": timestamp,
        "source": "analyzer",
    }
    if not normalized["goal"]:
        raise ValueError("Analyzer could not prepare a usable test goal from the current project context.")
    if not normalized["constraints"]:
        normalized["constraints"] = "Use realistic user replies. Stop on loops, fallback misuse, conversation restart, or unclear next step."
    if not normalized["test_data"]:
        normalized["test_data"] = "Use realistic placeholder customer details and exact quick-reply labels when the bot presents options."
    if not normalized["success_criteria"]:
        normalized["success_criteria"] = "The bot reaches the intended outcome without losing context, switching flows unexpectedly, or asking for already-provided details."

    project["goal_test_brief"] = normalized
    history = project.setdefault("goal_test_briefs", [])
    history.insert(0, normalized)
    project["goal_test_briefs"] = history[:12]
    project["updated_at"] = timestamp
    return normalized


def openai_goal_test_brief(
    chat: Dict[str, Any],
    project: Dict[str, Any],
    state: Dict[str, Any],
    setting_value: Callable[[str, str], str],
    rubric: List[str],
    root: Path,
    instruction: str = "",
) -> Dict[str, Any]:
    api_key = setting_value("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OpenAI API key is required to prepare a goal-driven test brief. Add it in Settings first.")
    model = setting_value("OPENAI_MODEL", "gpt-4.1-mini")
    context = build_chat_context(chat, project, state, rubric, root)
    context["recent_analyzer_messages"] = [
        {
            "role": message.get("role"),
            "content": str(message.get("content", ""))[:4000],
        }
        for message in chat.get("messages", [])[-10:]
    ]
    context["user_instruction"] = str(instruction or "").strip()
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "goal",
            "constraints",
            "test_data",
            "success_criteria",
            "max_turns",
            "reasoning",
            "source_artifacts",
        ],
        "properties": {
            "title": {"type": "string"},
            "goal": {"type": "string"},
            "constraints": {"type": "string"},
            "test_data": {"type": "string"},
            "success_criteria": {"type": "string"},
            "max_turns": {"type": "integer", "minimum": 2, "maximum": 20},
            "reasoning": {"type": "string"},
            "source_artifacts": {"type": "array", "items": {"type": "string"}},
        },
    }
    system_prompt = (
        "You convert Analyzer context into one executable goal-driven chat automation brief. "
        "The brief will be consumed by a Playwright web-widget runner that adaptively chooses user replies. "
        "Fill every field so the tester does not need to manually write the goal, constraints, test data, or success criteria. "
        "Use the current project context, latest analyzer chat, attached reports, failed transcripts, docs, and platform snapshots. "
        "Stay generic across Yellow.ai bots: do not hard-code a single client's artifact unless the current project evidence explicitly names it. "
        "Prefer failure-focused journeys when a failed report is attached; otherwise choose the highest-value customer journey from the bot profile. "
        "Constraints must include guardrails for context retention, wrong routing, fallback misuse, loops, language changes when relevant, and unsupported claims. "
        "Test data must be concrete enough for automation, but use safe placeholder customer details. "
        "Success criteria must be observable from the chat transcript. Return only structured JSON."
    )
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(context, indent=2)[:56000]},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "goal_driven_test_brief",
                "strict": True,
                "schema": schema,
            }
        },
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:400]
        raise ValueError(f"OpenAI goal brief request failed: {detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"OpenAI goal brief request failed: {exc}") from exc

    output_text = extract_openai_output_text(raw)
    if not output_text:
        raise ValueError("OpenAI goal brief request returned no readable response.")
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise ValueError("OpenAI goal brief response was not valid JSON.") from exc
    return parsed


def clamp_int(value: Any, minimum: int, maximum: int, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def make_chat_title(content: str) -> str:
    title = re.sub(r"\s+", " ", content).strip()
    return (title[:56] + "...") if len(title) > 59 else title or "New chat"


def remember_report_mentions(chat: Dict[str, Any], content: str) -> None:
    report_ids = extract_report_ids(content)
    if not report_ids:
        return
    artifacts = chat.setdefault("attached_artifacts", {"documents": [], "suites": [], "reports": [], "change_plans": []})
    attached_reports = artifacts.setdefault("reports", [])
    for report_id in report_ids:
        if report_id not in attached_reports:
            attached_reports.insert(0, report_id)


def extract_report_ids(value: str) -> List[str]:
    seen = set()
    report_ids = []
    for report_id in re.findall(r"\breport_[a-zA-Z0-9_:-]+\b", str(value or "")):
        clean_id = report_id.rstrip(".,;:) ]}")
        if clean_id and clean_id not in seen:
            seen.add(clean_id)
            report_ids.append(clean_id)
    return report_ids


def openai_chat_response(
    chat: Dict[str, Any],
    project: Dict[str, Any],
    state: Dict[str, Any],
    setting_value: Callable[[str, str], str],
    rubric: List[str],
    root: Path,
) -> str:
    api_key = setting_value("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OpenAI API key is required for real Analyzer chat. Add it in Settings first.")
    model = setting_value("OPENAI_MODEL", "gpt-4.1-mini")
    mode = chat.get("mode", "analyzer")
    system_prompt = (
        "You are the in-house Bot QA Analyzer for Yellow.ai chat agents. "
        "Be practical, direct, and project-aware. Use the provided project context, documents, suites, reports, platform snapshots, and Yellow.ai V3 rubric. "
        "This phase is read-only: diagnose, recommend, and test, but do not claim you edited Yellow.ai Studio or changed any bot configuration. "
        "For report analysis, do not stop at a summary. For every failed or review case, identify: the exact failed user turn, expected vs actual behavior, "
        "the most likely Yellow.ai artifact type and candidate page from platform_snapshot evidence, the likely configuration failure, the exact fix to make, "
        "and the regression test to rerun. Cite snapshot IDs/page labels/URLs when present. If snapshot evidence is missing or does not expose the needed "
        "agent/workflow/KB/tool details, say exactly which Studio page or artifact must be captured next. Do not give generic advice like 'review routing' "
        "unless you also name the specific route, trigger, workflow step, KB answer, or fallback branch suggested by the report and snapshot evidence. "
        "Use yellow_ai_specialist_brief before writing any root-cause answer. You may propose tests and exact recommended Yellow.ai changes, "
        "but edit execution and publishing are out of scope right now."
        f" {failure_diagnosis.analyzer_failure_prompt()}"
    )
    if mode == "docs":
        system_prompt = (
            "You are the Docs assistant for this in-house Bot QA Platform. "
            "Answer from the provided handbook and uploaded document context where possible. "
            "Mention source page or document names in plain text. If the context is insufficient, say what is missing."
        )

    context = build_chat_context(chat, project, state, rubric, root)
    input_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Project context:\n" + json.dumps(context, indent=2)[:52000]},
    ]
    for message in chat.get("messages", [])[-12:]:
        role = message.get("role", "user")
        if role not in ["user", "assistant"]:
            role = "user"
        input_messages.append({"role": role, "content": str(message.get("content", ""))[:6000]})

    payload = {"model": model, "input": input_messages}
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:400]
        raise ValueError(f"OpenAI chat request failed: {detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"OpenAI chat request failed: {exc}") from exc

    output_text = extract_openai_output_text(raw)
    if not output_text:
        raise ValueError("OpenAI chat returned no readable response.")
    return output_text.strip()


def extract_openai_output_text(raw: Dict[str, Any]) -> str:
    output_text = raw.get("output_text")
    if output_text:
        return output_text
    for item in raw.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text", "")
    return ""


def build_chat_context(
    chat: Dict[str, Any],
    project: Dict[str, Any],
    state: Dict[str, Any],
    rubric: List[str],
    root: Path,
) -> Dict[str, Any]:
    project_id = project["id"]
    docs = filter_project_items(state.get("documents", []), project_id)[:8]
    plans = filter_project_items(state.get("change_plans", []), project_id)[:6]
    suites = filter_project_items(state.get("suites", []), project_id)[:5]
    runs = filter_project_items(state.get("runs", []), project_id)[:5]
    reports = reports_for_chat_context(state, chat, project_id)
    snapshots = filter_project_items(state.get("platform_snapshots", []), project_id)[:3]
    requested_report_ids = report_ids_for_chat(chat)
    context: Dict[str, Any] = {
        "analysis_contract": [
            "Current product scope: read-only Yellow.ai QA agent. Diagnose, recommend, and test. Do not edit Yellow.ai.",
            "Use platform_snapshots and failure_debug_map before giving recommendations.",
            "Use yellow_ai_specialist_brief as the first source of truth for what to do and where to inspect.",
            "Use failure_investigation_packets first when present; they are pre-built root-cause packets from report transcript and platform snapshot evidence.",
            "Rank evidence in this order: failed transcript turn, report expected-vs-actual, exact active agent/step/function/API snapshot, then broad inventory pages. Broad inventory pages alone are weak evidence.",
            "Respect ruled_out_artifacts from failure_investigation_packets; do not recommend those artifacts unless the transcript or snapshot explicitly contradicts the packet.",
            "For each failed report case, return exact solutions: where the failure happened, candidate Yellow.ai artifact, what to change, and how to verify.",
            "If the snapshot does not expose enough details, state the exact missing artifact/page instead of giving generic guidance.",
        ],
        "failure_response_format": failure_diagnosis.failure_response_format(),
        "yellow_ai_specialist_brief": failure_diagnosis.build_readonly_specialist_brief(project, reports[:3], snapshots),
        "requested_report_ids": requested_report_ids,
        "reports": [
            report_context(report)
            for report in reports
        ],
        "failure_investigation_packets": failure_diagnosis.build_failure_investigation_packets(reports[:3], snapshots),
        "failure_debug_map": failure_debug_map(reports[:2], snapshots),
        "platform_snapshots": [
            snapshot_context(snapshot)
            for snapshot in snapshots
        ],
        "project": compact_project_context(project),
        "yellow_ai_v3_rubric": rubric,
        "documents": [
            {
                "id": doc["id"],
                "filename": doc["filename"],
                "analysis_status": doc.get("analysis_status"),
                "text_preview": doc.get("text_preview", "")[:1800],
            }
            for doc in docs
        ],
        "change_plans": [
            {
                "id": plan["id"],
                "document_name": plan.get("document_name"),
                "status": plan.get("status"),
                "summary": plan.get("summary", "")[:1200],
                "suggested_changes": plan.get("suggested_changes", [])[:5],
            }
            for plan in plans
        ],
        "suites": [
            {
                "id": suite["id"],
                "name": suite.get("name"),
                "source": suite.get("source"),
                "case_count": len(suite.get("test_cases", [])),
                "coverage_matrix": suite.get("coverage_matrix", {}),
            }
            for suite in suites
        ],
        "runs": runs,
    }
    if chat.get("mode") == "docs":
        context["handbook_pages"] = docs_pages(root)[:12]
    return context


def report_ids_for_chat(chat: Dict[str, Any]) -> List[str]:
    preferred_ids: List[str] = []
    for report_id in chat.get("attached_artifacts", {}).get("reports", []):
        if report_id not in preferred_ids:
            preferred_ids.append(report_id)
    for message in chat.get("messages", [])[-12:]:
        for report_id in extract_report_ids(str(message.get("content", ""))):
            if report_id not in preferred_ids:
                preferred_ids.append(report_id)
    return preferred_ids


def reports_for_chat_context(state: Dict[str, Any], chat: Dict[str, Any], project_id: str) -> List[Dict[str, Any]]:
    project_reports = filter_project_items(state.get("reports", []), project_id)
    by_id = {report.get("id"): report for report in project_reports}
    preferred_ids = report_ids_for_chat(chat)

    selected = [by_id[report_id] for report_id in preferred_ids if report_id in by_id]
    for report in project_reports:
        if len(selected) >= 5:
            break
        if report not in selected:
            selected.append(report)
    return selected


def compact_project_context(project: Dict[str, Any]) -> Dict[str, Any]:
    profile = project.get("bot_profile", {}) if isinstance(project.get("bot_profile"), dict) else {}
    profile_keys = [
        "bot_name",
        "bot_description",
        "business_goal",
        "chat_endpoint",
        "yellow_ai_bot_id",
        "yellow_ai_platform",
        "yellow_ai_environment",
        "agent_name",
        "workflow_name",
        "tool_name",
        "kb_name",
        "chat_case_count",
    ]
    compact_profile = {key: profile.get(key) for key in profile_keys if profile.get(key) not in [None, ""]}
    for long_key in ["flow_docs", "intents", "faqs"]:
        if profile.get(long_key):
            compact_profile[long_key] = str(profile.get(long_key, ""))[:1800]
    brief = project.get("goal_test_brief", {}) if isinstance(project.get("goal_test_brief"), dict) else {}
    return {
        "id": project.get("id"),
        "name": project.get("name"),
        "description": str(project.get("description", ""))[:1000],
        "bot_profile": compact_profile,
        "yellow_ai_target": project.get("yellow_ai_target", {}),
        "goal_test_brief": {
            "id": brief.get("id"),
            "title": brief.get("title"),
            "goal": str(brief.get("goal", ""))[:1200],
            "max_turns": brief.get("max_turns"),
        } if brief else {},
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at"),
    }


def snapshot_context(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": snapshot.get("id"),
        "created_at": snapshot.get("created_at"),
        "status": snapshot.get("status"),
        "bot_id": snapshot.get("bot_id"),
        "summary": snapshot.get("summary", "")[:1800],
        "pages": [snapshot_page_context(page) for page in snapshot.get("pages", [])[:10]],
        "network_events": snapshot.get("network_events", [])[:25],
    }


def snapshot_page_context(page: Dict[str, Any]) -> Dict[str, Any]:
    signals = page.get("signals", {}) if isinstance(page.get("signals"), dict) else {}
    return {
        "label": page.get("label"),
        "title": page.get("title"),
        "url": page.get("url"),
        "text_preview": str(page.get("text_preview", ""))[:3200],
        "signals": {
            "headings": compact_signal_items(signals.get("headings", []), 16),
            "buttons": compact_signal_items(signals.get("buttons", []), 18),
            "links": compact_signal_items(signals.get("links", []), 18),
            "inputs": compact_signal_items(signals.get("inputs", []), 18),
        },
        "tables": compact_tables(signals.get("tables", []), 4),
        "code_snippets": [str(snippet)[:1600] for snippet in signals.get("code_snippets", [])[:5]] if isinstance(signals.get("code_snippets"), list) else [],
    }


def compact_signal_items(items: Any, limit: int) -> List[Dict[str, str]]:
    if not isinstance(items, list):
        return []
    compact = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "text": str(item.get("text", ""))[:180],
                "href": str(item.get("href", ""))[:260],
                "aria": str(item.get("aria", ""))[:120],
                "role": str(item.get("role", ""))[:80],
            }
        )
    return compact


def compact_tables(tables: Any, limit: int) -> List[List[List[str]]]:
    if not isinstance(tables, list):
        return []
    compact = []
    for table in tables[:limit]:
        if not isinstance(table, list):
            continue
        compact.append([[str(cell)[:500] for cell in row[:8]] for row in table[:25] if isinstance(row, list)])
    return compact


def failure_debug_map(reports: List[Dict[str, Any]], snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    mapped = []
    for report in reports:
        for case in report.get("case_results", [])[:10]:
            score = case.get("score", {}) or {}
            if score.get("status") == "pass" and float(score.get("overall_score", 0) or 0) >= 0.78:
                continue
            result = case.get("result", {}) or {}
            transcript = compact_transcript(result.get("transcript", []))
            evidence_text = " ".join(
                [
                    str(case.get("flow_name", "")),
                    str(case.get("scenario_type", "")),
                    str(case.get("expected_outcome", "")),
                    " ".join(str(turn.get("text", "")) for turn in transcript),
                    " ".join(str(turn.get("expected_text", "")) for turn in transcript),
                    " ".join(str(issue) for issue in score.get("issues", [])[:5]),
                ]
            )
            keywords = debug_keywords(evidence_text)
            mapped.append(
                {
                    "report_id": report.get("id"),
                    "case_id": case.get("case_id"),
                    "flow_name": case.get("flow_name"),
                    "scenario_type": case.get("scenario_type"),
                    "score": {
                        "status": score.get("status"),
                        "overall_score": score.get("overall_score"),
                        "issues": score.get("issues", [])[:5],
                    },
                    "transcript": transcript,
                    "expected_response": expected_response_for_case(case, transcript),
                    "actual_response": actual_response_for_case(case, transcript),
                    "likely_artifact_type": likely_artifact_type(case, transcript),
                    "suggested_artifacts": candidate_artifacts_for_case(case, transcript, snapshots),
                    "suggested_fix": suggested_fix_for_case(case, transcript),
                    "snapshot_candidates": match_snapshot_pages(snapshots, keywords),
                }
            )
    return mapped[:12]


def expected_response_for_case(case: Dict[str, Any], transcript: List[Dict[str, Any]]) -> str:
    expected_texts = [str(turn.get("expected_text", "")).strip() for turn in transcript if turn.get("expected_text")]
    result = case.get("result", {}) if isinstance(case.get("result"), dict) else {}
    return result.get("expected_response") or result.get("expected_bot_response") or " | ".join(expected_texts) or case.get("expected_outcome", "")


def actual_response_for_case(case: Dict[str, Any], transcript: List[Dict[str, Any]]) -> str:
    actual_texts = [str(turn.get("text", "")).strip() for turn in transcript if turn.get("speaker") == "bot" and turn.get("text")]
    result = case.get("result", {}) if isinstance(case.get("result"), dict) else {}
    return result.get("actual_response") or result.get("bot_response") or result.get("observed_response") or " | ".join(actual_texts)


def likely_artifact_type(case: Dict[str, Any], transcript: List[Dict[str, Any]]) -> str:
    text = " ".join(
        [
            str(case.get("flow_name", "")),
            str(case.get("scenario_type", "")),
            " ".join(str(turn.get("text", "")) for turn in transcript),
            " ".join(str(turn.get("expected_text", "")) for turn in transcript),
        ]
    ).lower()
    if any(token in text for token in ["product", "recommend", "purifier", "small family", "model", "sku"]):
        return "Agent trigger or KB/product recommendation answer"
    if any(token in text for token in ["service", "not working", "registered number", "new customer", "warranty"]):
        return "Service workflow branch or registration gate"
    if any(token in text for token in ["order", "track", "unsupported"]):
        return "Routing trigger, unsupported-intent fallback, or handoff workflow"
    if any(token in text for token in ["human", "customer care", "agent"]):
        return "Handoff workflow or escalation response"
    if any(token in text for token in ["fallback", "unclear", "sorry", "can't help"]):
        return "Fallback branch or no-answer behavior"
    return "Agent routing, workflow branch, or KB answer"


def candidate_artifacts_for_case(case: Dict[str, Any], transcript: List[Dict[str, Any]], snapshots: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    text = " ".join(
        [
            str(case.get("flow_name", "")),
            str(case.get("scenario_type", "")),
            " ".join(str(turn.get("text", "")) for turn in transcript),
            " ".join(str(turn.get("expected_text", "")) for turn in transcript),
        ]
    ).lower()
    artifacts: List[Dict[str, str]] = []
    def add(kind: str, name: str, reason: str, always: bool = False) -> None:
        if always and not any(item["type"] == kind and item["name"] == name for item in artifacts):
            artifacts.append({"type": kind, "name": name, "why": reason})

    if any(token in text for token in ["product", "recommend", "purifier", "small family", "model", "sku"]):
        add("agent", "Active product recommendation or sales agent from snapshot", "Product guidance may be routed to an agent before enough qualification.", True)
        add("agent", "Knowledge answer agent from snapshot", "Product detail answer may come from KB or a knowledge-answer policy.", True)
        add("knowledge_base", "Product catalog or recommendation KB from snapshot", "Check whether the source content or retrieval ranking biases toward one option.", True)
        add("workflow", "Product card, quote, lead, or demo workflow from snapshot", "A conversion workflow may be firing before the user confirms intent.", True)
        add("function", "Product retrieval, ranking, or option-builder function from snapshot", "Check whether retrieval/ranking defaults to an inappropriate option.", True)

    if any(token in text for token in ["service", "not working", "registered number", "new customer", "warranty"]):
        add("agent", "Active service/support agent from snapshot", "Verify it acknowledges and stores the issue before lookup/validation.", True)
        add("workflow", "User lookup or registration workflow from snapshot", "Registration gates often run before case creation and can lose the original issue.", True)
        add("workflow", "Case/service-request creation workflow from snapshot", "Creates the downstream service record and may return the failure.", True)
        add("function", "Service parameter builder or status handler from snapshot", "Builds request fields or maps API success/failure into user-facing text.", True)
        add("api", "Create/update service case API from snapshot", "Downstream service API candidate.", True)

    if any(token in text for token in ["order", "track", "unsupported"]):
        add("agent", "Fallback or unsupported-intent agent from snapshot", "Candidate owner for unsupported order-tracking behavior.", True)
        add("workflow", "Handoff/escalation workflow from snapshot", "Escalation path when the bot cannot complete the request.", True)
        add("knowledge_base", "No-answer or unsupported-intent KB source from snapshot", "May need a source-backed limitation response.", True)
        add("function", "Fallback or unsupported-intent classifier from snapshot", "Candidate classifier for unsupported requests.", True)

    if any(token in text for token in ["human", "customer care", "agent"]):
        add("workflow", "Handoff/escalation workflow from snapshot", "Target workflow for live/customer-care escalation.", True)

    return artifacts[:10]


def suggested_fix_for_case(case: Dict[str, Any], transcript: List[Dict[str, Any]]) -> str:
    text = " ".join(
        [
            str(case.get("flow_name", "")),
            str(case.get("scenario_type", "")),
            " ".join(str(turn.get("text", "")) for turn in transcript),
            " ".join(str(turn.get("expected_text", "")) for turn in transcript),
        ]
    ).lower()
    if any(token in text for token in ["product", "recommend", "small family", "model", "sku"]):
        return (
            "Fix the active product recommendation or knowledge-answer path so advice queries first ask qualifying questions "
            "(for example usage need, budget, category constraints, location, or other domain-specific qualifiers) and then present suitable options. "
            "Check the product catalog/KB, ranking or option-builder function, and any product-card/lead/demo workflow so it does not fire before user confirmation."
        )
    if any(token in text for token in ["service", "not working", "registered number", "new customer"]):
        return (
            "Fix the active service/support path so the first response acknowledges and stores the user issue before identity, registration, or account lookup runs. "
            "The unregistered or unknown-user branch should preserve the original service intent and offer the next valid path without losing the problem statement."
        )
    if any(token in text for token in ["order", "track", "unsupported"]):
        return (
            "Add an explicit unsupported-intent or order-tracking branch: match those phrases, explain the limitation, and offer the correct channel or handoff/escalation path "
            "instead of resetting to welcome or misrouting."
        )
    return "Update the matching agent trigger/prompt or workflow branch and rerun the failed Playwright scenario plus nearby negative paths."


def debug_keywords(value: str) -> List[str]:
    stop = {
        "actual", "answer", "assistant", "because", "behavior", "branch", "case", "chat", "expected", "failed",
        "flow", "from", "issue", "message", "response", "scenario", "status", "that", "this", "turn", "user",
        "with", "yellow", "would", "should", "could", "please", "details",
    }
    words = []
    for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", value.lower()):
        if word not in stop and word not in words:
            words.append(word)
    preferred = [word for word in words if word in {
        "product", "recommendation", "service", "installation", "order", "tracking", "handoff", "fallback",
        "purifier", "registered", "customer", "agent", "workflow", "knowledge", "kb", "tool", "intent",
        "router", "routing", "number", "warranty", "grand", "star", "kent", "shuddhi",
    }]
    remainder = [word for word in words if word not in preferred]
    return (preferred + remainder)[:24]


def match_snapshot_pages(snapshots: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
    candidates = []
    for snapshot in snapshots:
        for page in snapshot.get("pages", [])[:12]:
            page_text = snapshot_page_search_text(page)
            if not page_text:
                continue
            matched = [keyword for keyword in keywords if keyword and keyword in page_text]
            if not matched:
                continue
            candidates.append(
                {
                    "snapshot_id": snapshot.get("id"),
                    "page_label": page.get("label"),
                    "page_title": page.get("title"),
                    "page_url": page.get("url"),
                    "matched_keywords": matched[:10],
                    "evidence_snippets": page_snippets(page_text, matched[:4]),
                }
            )
    candidates.sort(key=lambda item: len(item["matched_keywords"]), reverse=True)
    return candidates[:5]


def snapshot_page_search_text(page: Dict[str, Any]) -> str:
    signals = page.get("signals", {}) if isinstance(page.get("signals"), dict) else {}
    signal_text = []
    for key in ["headings", "buttons", "links", "inputs"]:
        items = signals.get(key, [])
        if isinstance(items, list):
            for item in items[:40]:
                if isinstance(item, dict):
                    signal_text.extend([str(item.get("text", "")), str(item.get("aria", "")), str(item.get("href", ""))])
    for table in signals.get("tables", []) if isinstance(signals.get("tables", []), list) else []:
        if isinstance(table, list):
            signal_text.append(" ".join(" ".join(str(cell) for cell in row) for row in table[:20] if isinstance(row, list)))
    for snippet in signals.get("code_snippets", []) if isinstance(signals.get("code_snippets", []), list) else []:
        signal_text.append(str(snippet))
    return re.sub(r"\s+", " ", " ".join([str(page.get("label", "")), str(page.get("title", "")), str(page.get("url", "")), str(page.get("text_preview", "")), " ".join(signal_text)]).lower())


def page_snippets(page_text: str, keywords: List[str]) -> List[str]:
    snippets = []
    for keyword in keywords:
        index = page_text.find(keyword)
        if index < 0:
            continue
        start = max(0, index - 120)
        end = min(len(page_text), index + 220)
        snippet = page_text[start:end].strip()
        if snippet and snippet not in snippets:
            snippets.append(snippet)
    return snippets[:4]


def report_context(report: Dict[str, Any]) -> Dict[str, Any]:
    case_results = []
    for case in report.get("case_results", [])[:8]:
        result = case.get("result", {}) or {}
        score = case.get("score", {}) or {}
        transcript = compact_transcript(result.get("transcript", []))
        expected_texts = [str(turn.get("expected_text", "")).strip() for turn in transcript if turn.get("expected_text")]
        actual_texts = [str(turn.get("text", "")).strip() for turn in transcript if turn.get("speaker") == "bot" and turn.get("text")]
        case_results.append(
            {
                "case_id": case.get("case_id"),
                "flow_name": case.get("flow_name"),
                "scenario_type": case.get("scenario_type"),
                "persona": case.get("persona"),
                "goal": case.get("goal"),
                "expected_outcome": case.get("expected_outcome"),
                "expected_response": result.get("expected_response") or result.get("expected_bot_response") or " | ".join(expected_texts) or case.get("expected_outcome", ""),
                "actual_response": result.get("actual_response") or result.get("bot_response") or result.get("observed_response") or " | ".join(actual_texts),
                "adapter": result.get("adapter"),
                "adapter_status": result.get("adapter_status"),
                "score": {
                    "status": score.get("status"),
                    "overall_score": score.get("overall_score"),
                    "issues": score.get("issues", [])[:8],
                    "metrics": score.get("metrics", {}),
                },
                "transcript": transcript,
                "recommendations": case.get("recommendations", [])[:5],
            }
        )
    return {
        "id": report["id"],
        "created_at": report.get("created_at"),
        "summary": report.get("summary", {}),
        "yellow_ai_recommendations": report.get("yellow_ai_recommendations", [])[:8],
        "case_results": case_results,
    }


def compact_transcript(transcript: Any) -> List[Dict[str, Any]]:
    if not isinstance(transcript, list):
        return []
    compact = []
    for turn in transcript[:24]:
        if not isinstance(turn, dict):
            continue
        compact.append(
            {
                "turn": turn.get("turn"),
                "speaker": turn.get("speaker"),
                "text": str(turn.get("text", ""))[:1200],
                "expected_text": str(turn.get("expected_text", ""))[:1200],
                "expected_buttons": turn.get("expected_buttons", []),
                "action": turn.get("action"),
                "confidence": turn.get("confidence"),
                "message_type": turn.get("message_type"),
                "stt_language": turn.get("stt_language"),
                "slug": str(turn.get("slug", ""))[:200],
                "latency_seconds": turn.get("latency_seconds"),
                "timestamp": turn.get("timestamp"),
            }
        )
    return compact


def docs_pages(root: Path) -> List[Dict[str, str]]:
    pages = [
        {
            "id": "tool-overview",
            "title": "In-House Tool Overview",
            "category": "Platform",
            "body": (
                "This local Bot QA Platform helps teams run real Yellow.ai web-widget chat scripts, analyze failures, "
                "score transcripts, upload bot documents, and produce Yellow.ai-style debugging recommendations. "
                "The app is project-based: Analyzer chats, documents, suites, runs, and reports all attach to one shared workspace."
            ),
        },
        {
            "id": "yellow-ai-cloud-nexus",
            "title": "Yellow.ai Cloud And Nexus",
            "category": "Yellow.ai",
            "body": (
                "Yellow.ai workspaces expose build areas such as Agents, Tools, Test suites, Knowledge base, User 360, analytics, "
                "campaigns, inbox, playground, extensions, and settings. The QA tool maps findings back to these product modules."
            ),
        },
        {
            "id": "yellow-ai-v2-v3",
            "title": "Yellow.ai V2 To V3",
            "category": "Migration",
            "body": (
                "V3 replaces step-by-step intent routing with an LLM-led agent architecture. Flow start triggers, ym.triggerJourney links, "
                "bot-scope variable assumptions, staticWorkflow, triggerWelcome, and most lifecycle hooks need migration review."
            ),
        },
        {
            "id": "v3-routing",
            "title": "V3 Context Expert Routing",
            "category": "Analyzer",
            "body": (
                "The Context Expert reads each agent's WHEN TO USE THIS description, recent history, and the latest user turn. "
                "Good tests cover keyword-rich triggers, anti-triggers, continuity while mid-procedure, and clear topic shifts."
            ),
        },
        {
            "id": "rag-kb-testing",
            "title": "RAG And Knowledge Base Testing",
            "category": "Analyzer",
            "body": (
                "RAG and KB behavior should be tested separately from workflow/API behavior. Cover retrieval relevance, source grounding, "
                "no-answer behavior, stale content risk, similar-policy collisions, and hallucination control."
            ),
        },
        {
            "id": "chat-failure-analysis",
            "title": "Chat Failure Analysis",
            "category": "Testing",
            "body": (
                "Chat tests run through Playwright against the Yellow.ai web widget. Reports preserve expected vs actual replies, "
                "quick-reply actions, transcripts, DOM evidence, and failure cards that map issues to routing, workflow/API, KB, or conversation design."
            ),
        },
        {
            "id": "read-only-specialist-agent",
            "title": "Read-Only Yellow.ai Specialist Agent",
            "category": "Analyzer",
            "body": (
                "The Analyzer is currently scoped as a read-only Yellow.ai QA agent: diagnose, recommend, and test, but do not edit. "
                "It should pinpoint failed turns, likely Yellow.ai artifact locations, root causes, exact recommended fixes, regression tests, "
                "and missing evidence pages/logs. Studio editing and publishing belong to a future approval-gated executor."
            ),
        },
        {
            "id": "platform-snapshots",
            "title": "Automated Platform Snapshots",
            "category": "Analyzer",
            "body": (
                "Analyzer can attach read-only Yellow.ai platform snapshots captured through Playwright. The snapshot collects visible Studio text, "
                "navigation signals, relevant links, and network metadata from a logged-in session for automated platform context."
            ),
        },
        {
            "id": "provider-setup",
            "title": "Provider Setup",
            "category": "Operations",
            "body": (
                "Runtime Settings store OpenAI and Yellow.ai values locally, while each project stores bot URL and web-widget selectors so users do not edit .env files per bot. "
                "Secrets are accepted by the settings dialog and not returned by /api/config."
            ),
        },
        {
            "id": "security-transfer",
            "title": "Security And Transfer",
            "category": "Operations",
            "body": (
                "Keep real secrets in .env or Runtime Settings, use placeholders in .env.example, rotate pasted keys, and avoid committing local state when a clean transfer is needed."
            ),
        },
    ]

    for path, title, category in [
        (root / "README.md", "Project README", "Platform"),
        (root / "yellow_ai_agent_documenter" / "yellow_ai_v3_rag_analyzer_alignment.md", "Yellow.ai V3 RAG Analyzer Alignment", "Analyzer"),
        (root / "yellow_ai_agent_documenter" / "yellow_ai_platform_deep_dive.md", "Yellow.ai Platform Deep Dive", "Yellow.ai"),
    ]:
        if path.exists():
            pages.append(
                {
                    "id": slugify(title),
                    "title": title,
                    "category": category,
                    "body": path.read_text(encoding="utf-8", errors="ignore")[:18000],
                }
            )
    return pages


def search_docs(state: Dict[str, Any], root: Path, query: str, project_id: str = "") -> List[Dict[str, Any]]:
    project_id = resolve_project_id(state, project_id)
    query = str(query or "").strip()
    tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 1]
    sources: List[Dict[str, str]] = []
    for page in docs_pages(root):
        sources.append({"type": "handbook", **page})
    for doc in filter_project_items(state.get("documents", []), project_id):
        sources.append(
            {
                "type": "document",
                "id": doc["id"],
                "title": doc["filename"],
                "category": "Project document",
                "body": doc.get("text_preview", ""),
            }
        )

    results = []
    for source in sources:
        body = source.get("body", "")
        haystack = f"{source.get('title', '')} {source.get('category', '')} {body}".lower()
        score = sum(haystack.count(token) for token in tokens) if tokens else 1
        if score <= 0:
            continue
        results.append(
            {
                "id": source.get("id"),
                "title": source.get("title"),
                "category": source.get("category"),
                "type": source.get("type"),
                "score": score,
                "excerpt": make_excerpt(body, tokens),
            }
        )
    return sorted(results, key=lambda item: item["score"], reverse=True)[:12]


def make_excerpt(body: str, tokens: List[str]) -> str:
    clean = re.sub(r"\s+", " ", body).strip()
    if not clean:
        return ""
    lower = clean.lower()
    index = 0
    for token in tokens:
        found = lower.find(token)
        if found >= 0:
            index = max(0, found - 120)
            break
    return clean[index : index + 420]
