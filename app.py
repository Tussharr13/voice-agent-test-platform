#!/usr/bin/env python3
import json
import os
import re
import time
import uuid
import cgi
import io
import zipfile
import xml.etree.ElementTree as ET
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from backend import auth as auth_backend
from backend import chat_automation
from backend import platform_snapshot
from backend import storage as state_storage
from backend import workspace as workspace_backend


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATE_PATH = DATA_DIR / "state.json"
STATIC_DIR = ROOT / "static"
UPLOAD_DIR = DATA_DIR / "uploads"
SECRET_SETTING_KEYS = {
    "OPENAI_API_KEY",
    "YELLOW_AI_API_KEY",
}

DEFAULT_SETTINGS = {
    "OPENAI_API_KEY": "",
    "OPENAI_MODEL": "gpt-4.1-mini",
    "PUBLIC_BASE_URL": "",
    "YELLOW_AI_API_KEY": "",
    "YELLOW_AI_BOT_ID": "",
    "YELLOW_AI_UI_BASE_URL": "https://cloud.yellow.ai",
    "CHAT_WIDGET_URL": "",
    "DEFAULT_BOT_NAME": "Yellow.ai Support Bot",
    "DEFAULT_CHAT_ENDPOINT": "",
}
SETTING_ALIASES = {key.lower(): key for key in DEFAULT_SETTINGS}


def load_local_env() -> None:
    for env_name in [".env", ".env.example"]:
        env_path = ROOT / env_name
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


load_local_env()

SCENARIO_TYPES = [
    "happy_path",
    "missing_information",
    "invalid_information",
    "user_changes_mind",
    "fallback_recovery",
    "agent_handoff",
]

PERSONAS = [
    "calm first-time user",
    "impatient returning user",
    "Hindi-English mixed user",
]

DEFAULT_CHAT_CASE_COUNT = 12
MAX_CHAT_CASE_COUNT = 60

CORE_METRIC_NAMES = [
    "Expected Outcome",
    "Instruction Following",
    "Intent Accuracy",
    "Response Relevance",
    "Context Retention",
    "CSAT",
    "Sentiment",
]

CHAT_METRIC_NAMES = [
    "Turn Efficiency",
    "Fallback Control",
    "Escalation Correctness",
]

YELLOW_AI_MODULES = {
    "agent_routing": "Agent routing",
    "tool_invocation": "Tool invocation",
    "workflow_api": "Workflow/API",
    "knowledge_base": "Knowledge base",
    "safety": "Safety and compliance",
    "conversation_design": "Conversation design",
}

YELLOW_AI_V3_ANALYZER_RUBRIC = [
    "V3 routing is LLM-led: the Context Expert selects one agent by reading WHEN TO USE THIS plus recent history and the latest user turn.",
    "Agent instructions should use plain English, {{memory}} variables for values needed later, and [tool]/[agent]/[kb] references for callable capabilities.",
    "Continuity matters: if the user is answering the active agent or is mid-procedure, tests should expect the current agent to stay active unless the topic clearly changes.",
    "Each agent should have one goal, concise keyword-rich trigger text, explicit exclusions, one action per step, branches for unknown/no-response cases, and a clear close condition.",
    "Every tool or workflow call needs declared inputs, failure handling, no-data behavior, timeout behavior, and proof that returned values are remembered or consumed.",
    "V2 migration risks to flag: ignored flow start triggers, missing skillConfig.inputs, dead ym.triggerJourney links, unwired lifecycle hooks except onConversationStart, and staticWorkflow/triggerWelcome usage.",
    "RAG and knowledge-base behavior must be tested separately from workflow/API behavior: retrieval relevance, no-answer handling, source grounding, and hallucination control are their own checks.",
    "Operational review should include live vs draft status, duplicated-agent draft behavior, safe iteration using draft copies, and bot-level scale warnings around many agents.",
]

def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "flow"


def read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length == 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw)


def read_multipart_upload(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    content_type = handler.headers.get("Content-Type", "")
    if not content_type.startswith("multipart/form-data"):
        raise ValueError("Expected multipart form upload")
    form = cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": handler.headers.get("Content-Length", "0"),
        },
    )
    file_item = form["document"] if "document" in form else None
    if file_item is None or not getattr(file_item, "filename", ""):
        raise ValueError("Upload field 'document' is required")
    raw = file_item.file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("Document is too large. Keep uploads under 8 MB for this local MVP.")
    return {
        "filename": Path(file_item.filename).name,
        "content_type": file_item.type or "application/octet-stream",
        "raw": raw,
        "project_id": str(form.getfirst("project_id", "") or "").strip(),
    }


def load_state() -> Dict[str, Any]:
    def default_state() -> Dict[str, Any]:
        state = {
            "suites": [],
            "runs": [],
            "reports": [],
            "settings": {},
            "documents": [],
            "change_plans": [],
            "platform_snapshots": [],
            "project_secrets": {},
        }
        workspace_backend.ensure_state_shape(state)
        return state

    user = auth_backend.current_user()
    state = state_storage.load_state(
        STATE_PATH,
        default_state,
        state_id=auth_backend.user_state_id(user) or "",
        seed_from_default=auth_backend.should_seed_from_default(user),
    )
    changed = workspace_backend.ensure_state_shape(state)
    if changed:
        save_state(state)
    return state


def save_state(state: Dict[str, Any]) -> None:
    user = auth_backend.current_user()
    state_storage.save_state(
        STATE_PATH,
        state,
        state_id=auth_backend.user_state_id(user) or "",
        user_id=(user or {}).get("id", ""),
        user_email=(user or {}).get("email", ""),
    )


def extract_document_text(filename: str, raw: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            pages = []
            for page in reader.pages[:40]:
                pages.append(page.extract_text() or "")
            return "\n".join(pages).strip()
        except Exception as exc:
            return f"[PDF text extraction failed: {exc}]"
    if suffix == ".docx":
        return extract_docx_text(raw)
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="ignore").strip()


def extract_docx_text(raw: bytes) -> str:
    namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    parts = [
        "word/document.xml",
        "word/footnotes.xml",
        "word/endnotes.xml",
    ]
    chunks = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for part in parts:
                if part not in archive.namelist():
                    continue
                root = ET.fromstring(archive.read(part))
                for paragraph in root.findall(".//w:p", namespaces):
                    texts = []
                    for node in paragraph.findall(".//w:t", namespaces):
                        if node.text:
                            texts.append(node.text)
                    if texts:
                        chunks.append("".join(texts))
                for table in root.findall(".//w:tbl", namespaces):
                    rows = []
                    for row in table.findall(".//w:tr", namespaces):
                        cells = []
                        for cell in row.findall(".//w:tc", namespaces):
                            cell_text = " ".join(
                                node.text for node in cell.findall(".//w:t", namespaces) if node.text
                            ).strip()
                            if cell_text:
                                cells.append(cell_text)
                        if cells:
                            rows.append(" | ".join(cells))
                    if rows:
                        chunks.append("\n".join(rows))
    except Exception as exc:
        return f"[DOCX text extraction failed: {exc}]"
    return "\n".join(chunks).strip()


def store_uploaded_document(upload: Dict[str, Any], project_id: str = "") -> Dict[str, Any]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    project_id = workspace_backend.resolve_project_id(state, project_id or upload.get("project_id", ""))
    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    filename = upload["filename"]
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename).strip("_") or "document"
    stored_name = f"{doc_id}_{safe_name}"
    path = UPLOAD_DIR / stored_name
    raw = upload["raw"]
    path.write_bytes(raw)
    text = extract_document_text(filename, raw)
    document = {
        "id": doc_id,
        "filename": filename,
        "stored_path": str(path.relative_to(ROOT)),
        "content_type": upload["content_type"],
        "size_bytes": len(raw),
        "created_at": now_iso(),
        "project_id": project_id,
        "text_preview": text[:4000],
        "text_length": len(text),
        "analysis_status": "uploaded",
    }
    state["documents"].insert(0, document)
    save_state(state)
    return document


def analyze_document(document_id: str, profile: Dict[str, Any], project_id: str = "") -> Dict[str, Any]:
    state = load_state()
    document = next((item for item in state["documents"] if item["id"] == document_id), None)
    if not document:
        raise ValueError("Document not found")
    project_id = workspace_backend.resolve_project_id(state, project_id or document.get("project_id", ""))
    project = workspace_backend.get_project(state, project_id)
    profile = profile or project.get("bot_profile", {})

    path = ROOT / document["stored_path"]
    text = extract_document_text(document["filename"], path.read_bytes())
    target = yellow_ai_target(profile)
    ai_analysis = openai_analyze_document(document["filename"], text, profile, target)
    analysis_source = "openai" if ai_analysis else "local_rules"
    insights = (ai_analysis or {}).get("insights") or document_insights(text)
    suggested_changes = normalize_ai_changes((ai_analysis or {}).get("suggested_changes"), target) or suggested_changes_for_document(text, target)
    test_cases = normalize_ai_tests((ai_analysis or {}).get("suggested_test_cases")) or suggested_doc_test_cases(text, profile)
    plan = {
        "id": f"plan_{uuid.uuid4().hex[:10]}",
        "document_id": document_id,
        "document_name": document["filename"],
        "project_id": project_id,
        "created_at": now_iso(),
        "analysis_source": analysis_source,
        "status": "pending_approval",
        "approval_required": True,
        "execution_status": "not_executed",
        "execution_note": "Yellow.ai execution is intentionally blocked until the user grants platform access and approves each action.",
        "target": target,
        "summary": (ai_analysis or {}).get("summary") or summarize_document(text),
        "insights": insights,
        "suggested_changes": suggested_changes,
        "suggested_test_cases": test_cases,
    }
    document["project_id"] = project_id
    document["analysis_status"] = "analyzed"
    document["last_plan_id"] = plan["id"]
    workspace_backend.update_project_profile(state, project_id, profile)
    state["change_plans"].insert(0, plan)
    save_state(state)
    return plan


def openai_analyze_document(filename: str, text: str, profile: Dict[str, Any], target: Dict[str, str]) -> Optional[Dict[str, Any]]:
    api_key = setting_value("OPENAI_API_KEY")
    if not api_key:
        return None

    model = setting_value("OPENAI_MODEL", "gpt-4.1-mini")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "insights", "suggested_changes", "suggested_test_cases"],
        "properties": {
            "summary": {"type": "string"},
            "insights": {"type": "array", "items": {"type": "string"}},
            "suggested_changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["module", "title", "recommendation", "risk"],
                    "properties": {
                        "module": {"type": "string"},
                        "title": {"type": "string"},
                        "recommendation": {"type": "string"},
                        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                    },
                },
            },
            "suggested_test_cases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "goal"],
                    "properties": {
                        "name": {"type": "string"},
                        "goal": {"type": "string"},
                    },
                },
            },
        },
    }
    prompt = (
        "You are a senior QA automation engineer and Yellow.ai product engineer. "
        "Analyze the uploaded bot/testing document and produce practical, approval-gated recommendations. "
        "Align the analysis to Yellow.ai V3, where the Context Expert LLM routes to one agent by reading "
        "WHEN TO USE THIS descriptions, conversation history, and the latest user turn. "
        "Map suggestions to Yellow.ai modules such as Agent routing, Testing lab, Workflow/API, Knowledge base, "
        "Chat execution, Reporting, Safety, or Conversation design. "
        "Look for V3-specific issues: unclear trigger descriptions, missing anti-triggers, weak one-goal agent boundaries, "
        "missing {{memory}} persistence, missing [tool]/[agent]/[kb] references, undeclared skill inputs, "
        "tool failure/no-data branches, dead V2 deep links, flow start trigger reliance, unsupported lifecycle hooks, "
        "staticWorkflow/triggerWelcome usage, live-vs-draft deployment risk, and RAG grounding gaps. "
        "Do not claim that any external change has been executed. Proposals must be safe to review before approval."
    )
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "filename": filename,
                        "bot_profile": profile,
                        "yellow_ai_target": target,
                        "yellow_ai_v3_analyzer_rubric": YELLOW_AI_V3_ANALYZER_RUBRIC,
                        "document_text": text[:24000],
                    },
                    indent=2,
                ),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "document_change_plan",
                "strict": True,
                "schema": schema,
            }
        },
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None

    output_text = raw.get("output_text")
    if not output_text:
        for item in raw.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    output_text = content.get("text")
                    break
    if not output_text:
        return None
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        return None
    return parsed


def normalize_ai_changes(items: Any, target: Dict[str, str]) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    target_hint = yellow_ai_target_hint(target)
    normalized = []
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        module = str(item.get("module") or "Conversation design").strip()
        title = str(item.get("title") or "Review suggested change").strip()
        recommendation = str(item.get("recommendation") or "").strip()
        if not recommendation:
            continue
        risk = str(item.get("risk") or "low").strip().lower()
        if risk not in ["low", "medium", "high"]:
            risk = "low"
        normalized.append(
            {
                "id": f"chg_{uuid.uuid4().hex[:8]}",
                "module": module,
                "title": title,
                "recommendation": recommendation,
                "yellow_ai_hint": f"Target: {target_hint}. This AI-generated action is a proposal only until approved.",
                "status": "pending_approval",
                "risk": risk,
            }
        )
    return normalized


def normalize_ai_tests(items: Any) -> List[Dict[str, str]]:
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        goal = str(item.get("goal") or "").strip()
        if name and goal:
            normalized.append({"name": name, "goal": goal})
    return normalized


def summarize_document(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return "No readable text was extracted from this document."
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    return " ".join(sentences[:3])[:900]


def document_insights(text: str) -> List[str]:
    lower = text.lower()
    insights = []
    if "context expert" in lower or "when to use this" in lower or "v3" in lower:
        insights.append("Yellow.ai V3 routing should be evaluated through Context Expert selection, trigger descriptions, anti-triggers, and continuity behavior rather than legacy intent-only routing.")
    if "{{" in text or "remember" in lower or "automatic memory" in lower:
        insights.append("Memory persistence is a first-class V3 check: values needed after a user reply or agent switch must be explicitly remembered and regression-tested.")
    if "skillconfig.inputs" in lower or "skill input" in lower or "bot-scope variables" in lower:
        insights.append("Flow-as-skill execution needs explicit input contracts; bot-scope/session variables can silently become undefined in V3 if not passed or remembered.")
    if "ym.triggerjourney" in lower or "onconversationstart" in lower or "lifecycle hook" in lower:
        insights.append("Migration checks should flag V2 deep links and unwired lifecycle hooks, with onConversationStart as the reliable setup path.")
    if "staticworkflow" in lower or "triggerwelcome" in lower:
        insights.append("Welcome and fallback review should avoid staticWorkflow/triggerWelcome assumptions and prefer instruction pools plus setup hooks.")
    if "live" in lower and "draft" in lower and "agent" in lower:
        insights.append("Deployment review should validate live/draft status, duplicated-agent draft behavior, and safe iteration using draft copies.")
    if "playwright" in lower or "browser" in lower:
        insights.append("Document describes browser-driven chatbot testing automation.")
    if "markdown" in lower and "test" in lower:
        insights.append("Test cases can be represented as Markdown conversation scripts and parsed into structured turns.")
    if "report" in lower:
        insights.append("Report generation should preserve expected vs actual bot behavior and machine-readable JSON.")
    if "knowledge" in lower or "kb" in lower or "rag" in lower:
        insights.append("Knowledge-base behavior should be tested separately from workflow/API behavior.")
    if "api" in lower or "webhook" in lower or "function" in lower:
        insights.append("Workflow/API failures should be classified apart from prompt or routing failures.")
    if "yellow" in lower or "agent" in lower:
        insights.append("Suggested changes should map back to Yellow.ai modules such as agents, tools, workflows, KB, evaluators, and chat execution.")
    return insights or ["Document uploaded successfully. Add more flow, test, or bot details for richer analysis."]


def suggested_changes_for_document(text: str, target: Dict[str, str]) -> List[Dict[str, Any]]:
    lower = text.lower()
    changes: List[Dict[str, Any]] = []
    target_hint = yellow_ai_target_hint(target)
    if "context expert" in lower or "when to use this" in lower or "v3" in lower:
        changes.append(change_item("Agent routing", "Add V3 Context Expert routing audit", "Check every agent's WHEN TO USE THIS text for concise keyword coverage, anti-triggers, one-goal boundaries, and continuity behavior when a user is mid-procedure.", target_hint))
    if "{{" in text or "remember" in lower or "automatic memory" in lower:
        changes.append(change_item("Conversation design", "Add memory persistence tests", "Generate tests that verify important customer input and tool outputs are remembered as {{variables}} across replies, summaries, and agent switches.", target_hint))
    if "skillconfig.inputs" in lower or "skill input" in lower or "bot-scope variables" in lower:
        changes.append(change_item("Workflow/API", "Validate flow-as-skill input contracts", "Require every flow-as-skill to declare the inputs it reads, then test undefined bot-scope variables, missing session values, and output consumption.", target_hint))
    if "ym.triggerjourney" in lower or "onconversationstart" in lower or "lifecycle hook" in lower:
        changes.append(change_item("Conversation design", "Add V2-to-V3 migration checks", "Flag ym.triggerJourney links, flow start trigger reliance, unsupported lifecycle hooks, staticWorkflow, and triggerWelcome patterns before approving migration changes.", target_hint))
    if "knowledge" in lower or "kb" in lower or "rag" in lower:
        changes.append(change_item("Knowledge base", "Add RAG grounding analyzer", "Score retrieval relevance, source grounding, no-answer behavior, stale content risk, and hallucination control separately from workflow/API failures.", target_hint))
    if "markdown" in lower and "test" in lower:
        changes.append(change_item("Testing lab", "Create Markdown-script import format", "Add parser support for User/Bot turn blocks, expected buttons, expected tables, click steps, and upload steps.", target_hint))
    if "playwright" in lower or "browser" in lower:
        changes.append(change_item("Chat execution", "Add browser-runner adapter", "Use a browser automation adapter for web-widget bots, capturing transcript, buttons, cards, and DOM/browser evidence without modifying the bot.", target_hint))
    if "report" in lower:
        changes.append(change_item("Reporting", "Add expected-vs-actual report section", "Show expected response, observed response, missing entities, extra prompts, and module-level failure classification.", target_hint))
    if "api" in lower or "webhook" in lower or "function" in lower:
        changes.append(change_item("Workflow/API", "Add tool contract checks", "Validate required args, API status, timeout behavior, and output mapping for Yellow.ai workflows/functions.", target_hint))
    if not changes:
        changes.append(change_item("Conversation design", "Review document against bot profile", "Use the uploaded document as additional context for suite generation and recommendation wording.", target_hint))
    return changes


def change_item(module: str, title: str, recommendation: str, target_hint: str) -> Dict[str, Any]:
    return {
        "id": f"chg_{uuid.uuid4().hex[:8]}",
        "module": module,
        "title": title,
        "recommendation": recommendation,
        "yellow_ai_hint": f"Target: {target_hint}. This action is a proposal only until approved.",
        "status": "pending_approval",
        "risk": "medium" if module in ["Workflow/API"] else "low",
    }


def suggested_doc_test_cases(text: str, profile: Dict[str, Any]) -> List[Dict[str, str]]:
    lower = text.lower()
    cases = []
    if "context expert" in lower or "when to use this" in lower or "v3" in lower:
        cases.append({"name": "V3 Context Expert Routing", "goal": "Send overlapping user intents and verify the selected agent matches WHEN TO USE THIS while continuity keeps the active agent during in-progress steps."})
    if "{{" in text or "remember" in lower:
        cases.append({"name": "V3 Memory Persistence", "goal": "Capture user input and tool output, continue for several turns, then verify the bot still uses remembered values correctly."})
    if "skillconfig.inputs" in lower or "bot-scope variables" in lower:
        cases.append({"name": "Flow Skill Input Contract", "goal": "Invoke a flow-as-skill with missing, invalid, and valid inputs to ensure V3 does not rely on implicit bot-scope variables."})
    if "ym.triggerjourney" in lower or "onconversationstart" in lower:
        cases.append({"name": "V3 Deep Link Migration", "goal": "Verify startup routing uses onConversationStart context handling instead of ym.triggerJourney or ignored flow start triggers."})
    if "knowledge" in lower or "kb" in lower or "rag" in lower:
        cases.append({"name": "RAG Grounding Guardrail", "goal": "Ask answerable, unanswerable, and ambiguous KB questions and score retrieval relevance, no-answer behavior, and hallucination control."})
    if "markdown" in lower:
        cases.append({"name": "Markdown Script Parsing", "goal": "Upload a scripted conversation and verify turns, expected bot replies, buttons, and tables are parsed correctly."})
    if "playwright" in lower or "browser" in lower:
        cases.append({"name": "Web Widget Smoke Run", "goal": "Open the configured chat endpoint, send a scripted turn, and capture the bot response without editing platform state."})
    if "api" in lower or "function" in lower:
        cases.append({"name": "Workflow Contract Check", "goal": "Verify the expected tool receives required args and returns a consumable output result."})
    if not cases:
        bot_name = profile.get("bot_name", "bot")
        cases.append({"name": "Document Context Regression", "goal": f"Generate a regression case from the uploaded document for {bot_name}."})
    return cases[:6]


def approve_change_plan(plan_id: str) -> Dict[str, Any]:
    state = load_state()
    plan = next((item for item in state["change_plans"] if item["id"] == plan_id), None)
    if not plan:
        raise ValueError("Change plan not found")
    plan["status"] = "approved"
    plan["approved_at"] = now_iso()
    plan["execution_status"] = "approved_not_executed"
    plan["execution_note"] = "Approved locally. Yellow.ai execution still requires an explicit platform-access implementation step."
    for item in plan.get("suggested_changes", []):
        item["status"] = "approved"
    save_state(state)
    return plan


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200, headers: Dict[str, str] = None) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    for key, value in (headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, body: str, content_type: str = "text/html") -> None:
    data = body.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def error_response(handler: BaseHTTPRequestHandler, message: str, status: int = 400) -> None:
    json_response(handler, {"error": message}, status=status)


def auth_payload(user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {"authenticated": bool(user), "user": user if user else None}


def request_user(handler: BaseHTTPRequestHandler) -> Optional[Dict[str, Any]]:
    user = auth_backend.user_from_handler(handler)
    if not user:
        error_response(handler, "Sign in to continue.", 401)
        return None
    auth_backend.set_current_user(user)
    return user


def complete_auth(handler: BaseHTTPRequestHandler, user: Dict[str, Any]) -> None:
    auth_backend.set_current_user(user)
    try:
        load_state()
    finally:
        auth_backend.clear_current_user()
    json_response(handler, auth_payload(user), headers={"Set-Cookie": auth_backend.create_cookie(user)})


def runtime_settings() -> Dict[str, str]:
    saved = load_state().get("settings", {})
    settings = dict(DEFAULT_SETTINGS)
    for key in DEFAULT_SETTINGS:
        env_value = os.environ.get(key, "").strip()
        if env_value:
            settings[key] = env_value
    for key, value in saved.items():
        canonical_key = key if key in DEFAULT_SETTINGS else SETTING_ALIASES.get(key)
        if canonical_key and isinstance(value, str) and value.strip():
            settings[canonical_key] = value.strip()
    return settings


def setting_value(name: str, default: str = "") -> str:
    return runtime_settings().get(name, default).strip()


def setting_bool(name: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return setting_value(name, fallback).lower() == "true"


def setting_present(settings: Dict[str, str], name: str) -> bool:
    return bool(settings.get(name, "").strip())


def provider_readiness(settings: Dict[str, str], provider: str, required_env: List[str]) -> Dict[str, Any]:
    missing = [name for name in required_env if not setting_present(settings, name)]
    return {
        "provider": provider,
        "configured": not missing,
        "missing_env": missing,
    }


def public_settings(settings: Dict[str, str]) -> Dict[str, Any]:
    safe_settings: Dict[str, Any] = {}
    for key in DEFAULT_SETTINGS:
        value = settings.get(key, "")
        if key in SECRET_SETTING_KEYS:
            safe_settings[key] = {
                "value": "",
                "configured": bool(value.strip()),
                "secret": True,
            }
        else:
            safe_settings[key] = {
                "value": value,
                "configured": bool(value.strip()),
                "secret": False,
            }
    return safe_settings


def update_runtime_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    saved = state.setdefault("settings", {})
    for key, raw_value in updates.items():
        if key not in DEFAULT_SETTINGS:
            continue
        value = str(raw_value).strip()
        if key in SECRET_SETTING_KEYS and not value:
            continue
        saved[key] = value
    save_state(state)
    return public_config()


def public_config() -> Dict[str, Any]:
    settings = runtime_settings()
    return {
        "auth": auth_payload(auth_backend.current_user()),
        "openai": provider_readiness(settings, "openai", ["OPENAI_API_KEY"]),
        "playwright": chat_automation.playwright_status(),
        "platform_snapshot": platform_snapshot.playwright_status(),
        "app_port": int(os.environ.get("APP_PORT", "8787")),
        "storage": state_storage.public_status(STATE_PATH),
        "settings": public_settings(settings),
    }


def project_access_response(state: Dict[str, Any], project_id: str) -> Dict[str, Any]:
    access = workspace_backend.project_access_payload(state, project_id)
    if not access.get("api_key_configured") and setting_value("YELLOW_AI_API_KEY", ""):
        access["api_key_configured"] = True
    return access


def extract_flows(profile: Dict[str, Any]) -> List[Dict[str, str]]:
    flows = []
    for flow in profile.get("flows", []):
        if isinstance(flow, dict):
            name = flow.get("name") or flow.get("flow_name")
            description = flow.get("description", "")
        else:
            name = str(flow)
            description = ""
        if name:
            flows.append({"name": name, "description": description})

    if flows:
        return flows

    text = " ".join(
        str(profile.get(key, ""))
        for key in ["bot_description", "business_goal", "flow_docs", "intents", "faqs"]
    )
    candidates = []
    patterns = [
        r"(order status|track order|cancel order|refund|return|appointment|booking|payment|kyc|agent handoff|complaint|support ticket)",
        r"(balance enquiry|loan status|card block|policy renewal|claim status)",
    ]
    for pattern in patterns:
        candidates.extend(re.findall(pattern, text, flags=re.IGNORECASE))

    unique = []
    seen = set()
    for candidate in candidates:
        name = candidate.strip().title()
        key = slugify(name)
        if key not in seen:
            seen.add(key)
            unique.append({"name": name, "description": f"Detected from profile: {name}"})

    if unique:
        return unique[:6]

    return [
        {"name": "Primary Goal Completion", "description": "Main user journey for this bot."},
        {"name": "Fallback And Recovery", "description": "Bot handles unclear or unsupported user input."},
        {"name": "Agent Handoff", "description": "Bot escalates to a human when automation cannot continue."},
    ]


def yellow_ai_context(profile: Dict[str, Any]) -> Dict[str, str]:
    return {
        "platform": profile.get("yellow_ai_platform", "nexus").strip() or "nexus",
        "bot_id": profile.get("yellow_ai_bot_id", "").strip(),
        "environment": profile.get("yellow_ai_environment", "").strip(),
        "super_agent": profile.get("yellow_ai_super_agent", "").strip(),
        "agent_name": profile.get("yellow_ai_agent_name", "").strip(),
        "workflow_name": profile.get("yellow_ai_workflow_name", "").strip(),
        "workflow_id": profile.get("yellow_ai_workflow_id", "").strip(),
        "tool_name": profile.get("yellow_ai_tool_name", "").strip(),
        "kb_name": profile.get("yellow_ai_kb_name", "").strip(),
    }


def yellow_ai_target(profile: Dict[str, Any]) -> Dict[str, str]:
    context = yellow_ai_context(profile)
    return {key: value for key, value in context.items() if value}


def yellow_ai_module_for(flow_name: str, scenario_type: str, channel: str) -> str:
    text = f"{flow_name} {scenario_type}".lower()
    if "handoff" in text:
        return "agent_routing"
    if any(token in text for token in ["order status", "track order", "refund", "delivery", "lookup", "status"]):
        return "tool_invocation"
    if any(token in text for token in ["faq", "policy", "knowledge", "kb"]):
        return "knowledge_base"
    if any(token in text for token in ["fallback", "missing", "invalid", "changes_mind"]):
        return "conversation_design"
    return "agent_routing"


def case_yellow_ai_metadata(profile: Dict[str, Any], flow_name: str, scenario_type: str, channel: str) -> Dict[str, Any]:
    target = yellow_ai_target(profile)
    module_key = yellow_ai_module_for(flow_name, scenario_type, channel)
    return {
        "target": target,
        "module_key": module_key,
        "module": YELLOW_AI_MODULES[module_key],
        "failure_lens": failure_lens_for(module_key),
    }


def failure_lens_for(module_key: str) -> List[str]:
    lenses = {
        "agent_routing": ["specialist selected", "trigger matched", "handoff rule respected"],
        "tool_invocation": ["tool selected", "required args passed", "tool result consumed"],
        "workflow_api": ["workflow branch", "API/function status", "output mapping"],
        "knowledge_base": ["retrieval relevance", "no-answer behavior", "hallucination control"],
        "safety": ["PII", "toxicity/bias", "jailbreak resistance"],
        "conversation_design": ["clarification", "context retention", "terminal message"],
    }
    return lenses.get(module_key, lenses["conversation_design"])


def desired_chat_case_count(profile: Dict[str, Any]) -> int:
    raw_value = profile.get("chat_case_count") or profile.get("test_case_count") or DEFAULT_CHAT_CASE_COUNT
    try:
        count = int(str(raw_value).strip())
    except (TypeError, ValueError):
        count = DEFAULT_CHAT_CASE_COUNT
    return max(1, min(MAX_CHAT_CASE_COUNT, count))


def build_fallback_suite(profile: Dict[str, Any]) -> Dict[str, Any]:
    channels = ["chat"]

    flows = extract_flows(profile)
    desired_count = desired_chat_case_count(profile)
    cases = []
    case_index = 0
    while len(cases) < desired_count:
        flow = flows[case_index % len(flows)]
        scenario_type = SCENARIO_TYPES[(case_index // len(flows)) % len(SCENARIO_TYPES)]
        channel = channels[0]
        persona = PERSONAS[(case_index + len(flow["name"])) % len(PERSONAS)]
        case_id = f"tc_{slugify(flow['name'])}_{scenario_type}_{channel}_{len(cases) + 1}"
        yellow_ai = case_yellow_ai_metadata(profile, flow["name"], scenario_type, channel)
        cases.append(
            {
                "id": case_id,
                "flow_name": flow["name"],
                "channel": channel,
                "scenario_type": scenario_type,
                "persona": persona,
                "priority": "high" if scenario_type in ["happy_path", "fallback_recovery"] else "medium",
                "goal": scenario_goal(flow["name"], scenario_type),
                "instructions": evaluator_instructions(flow["name"], scenario_type, channel, persona),
                "expected_outcome": expected_outcome(flow["name"], scenario_type),
                "test_profile": test_profile_for(persona, channel),
                "metric_names": metric_names_for(channel),
                "tags": ["generated", channel, scenario_type, slugify(flow["name"])],
                "steps": scenario_steps(flow["name"], scenario_type, channel),
                "expected_bot_behaviors": expected_behaviors(flow["name"], scenario_type),
                "failure_conditions": failure_conditions(scenario_type),
                "metrics": base_metrics(channel, scenario_type),
                "yellow_ai": yellow_ai,
                "target": {
                    "chat_endpoint": profile.get("chat_endpoint", ""),
                },
            }
        )
        case_index += 1

    return {
        "id": f"suite_{uuid.uuid4().hex[:10]}",
        "name": profile.get("bot_name", "Untitled Bot") + " Regression Suite",
        "created_at": now_iso(),
        "source": "heuristic",
        "bot_profile": profile,
        "requested_chat_case_count": desired_count,
        "yellow_ai_target": yellow_ai_target(profile),
        "coverage_matrix": build_coverage_matrix(cases),
        "test_cases": cases,
    }


def evaluator_instructions(flow_name: str, scenario_type: str, channel: str, persona: str) -> str:
    return (
        f"Act as a {persona}. Your goal is to test the {flow_name} flow. "
        f"Use the {scenario_type.replace('_', ' ')} scenario and type concise chat messages. "
        "Follow the test steps, provide only the information the bot asks for, and expose failures without coaching the bot."
    )


def expected_outcome(flow_name: str, scenario_type: str) -> str:
    if scenario_type == "happy_path":
        return f"The bot completes {flow_name}, confirms the outcome, and does not ask for already-provided information."
    if scenario_type == "missing_information":
        return f"The bot offers an alternate path for {flow_name} instead of getting stuck on a missing identifier."
    if scenario_type == "invalid_information":
        return f"The bot rejects invalid information for {flow_name}, explains the required format, and lets the user retry."
    if scenario_type == "user_changes_mind":
        return f"The bot handles a mid-flow context change and routes the user without losing the conversation."
    if scenario_type == "fallback_recovery":
        return f"The bot recovers from unclear input within one clarification turn and returns to {flow_name}."
    if scenario_type == "agent_handoff":
        return "The bot offers a human handoff when automation cannot continue or when the user explicitly asks."
    return f"The bot satisfies the evaluator goal for {flow_name}."


def test_profile_for(persona: str, channel: str) -> Dict[str, str]:
    profiles = {
        "calm first-time user": {
            "name": "Ananya Sharma",
            "language": "English",
            "tone": "calm",
            "behavior": "cooperative and patient",
        },
        "impatient returning user": {
            "name": "Rahul Mehta",
            "language": "English",
            "tone": "impatient",
            "behavior": "wants quick resolution and may interrupt",
        },
        "Hindi-English mixed user": {
            "name": "Priya Singh",
            "language": "Hindi-English",
            "tone": "natural code-switching",
            "behavior": "mixes short Hindi phrases with English intent",
        },
    }
    profile = profiles.get(persona, profiles["calm first-time user"]).copy()
    profile["channel"] = channel
    return profile


def metric_names_for(channel: str) -> List[str]:
    return CORE_METRIC_NAMES + CHAT_METRIC_NAMES


def scenario_goal(flow_name: str, scenario_type: str) -> str:
    labels = {
        "happy_path": f"Complete the {flow_name} flow with valid information.",
        "missing_information": f"Check whether the bot can recover when the user lacks required information for {flow_name}.",
        "invalid_information": f"Validate how the bot handles invalid details in {flow_name}.",
        "user_changes_mind": f"Ensure the bot can handle a user changing direction during {flow_name}.",
        "fallback_recovery": f"Probe fallback behavior and recovery during {flow_name}.",
        "agent_handoff": f"Verify escalation behavior when {flow_name} cannot be completed automatically.",
    }
    return labels.get(scenario_type, f"Test {flow_name}.")


def scenario_steps(flow_name: str, scenario_type: str, channel: str) -> List[Dict[str, str]]:
    opener = f"I need help with {flow_name.lower()}."

    steps = [{"user_intent": slugify(flow_name), "utterance": opener}]
    if scenario_type == "happy_path":
        steps.extend(
            [
                {"condition": "bot asks for required details", "utterance": "Sure, the details are valid and match my account."},
                {"condition": "bot confirms action", "utterance": "Yes, please go ahead."},
            ]
        )
    elif scenario_type == "missing_information":
        steps.extend(
            [
                {"condition": "bot asks for identifier", "utterance": "I do not have that with me. Can you use my registered email?"},
                {"condition": "bot offers alternative lookup", "utterance": "Yes, use my registered email."},
            ]
        )
    elif scenario_type == "invalid_information":
        steps.extend(
            [
                {"condition": "bot asks for identifier", "utterance": "The ID is ABC000."},
                {"condition": "bot rejects invalid input", "utterance": "Okay, what format do you need?"},
            ]
        )
    elif scenario_type == "user_changes_mind":
        steps.extend(
            [
                {"condition": "bot starts the flow", "utterance": "Actually wait, I want to check the status first."},
                {"condition": "bot switches context", "utterance": "Yes, continue with that instead."},
            ]
        )
    elif scenario_type == "fallback_recovery":
        steps.extend(
            [
                {"condition": "bot asks clarifying question", "utterance": "That is not what I meant."},
                {"condition": "bot recovers", "utterance": opener},
            ]
        )
    else:
        steps.extend(
            [
                {"condition": "bot cannot complete automatically", "utterance": "Please connect me to a human agent."},
                {"condition": "bot starts handoff", "utterance": "Yes, I can wait."},
            ]
        )
    return steps


def expected_behaviors(flow_name: str, scenario_type: str) -> List[str]:
    common = [
        "recognizes the correct user intent",
        "asks only for information required for the flow",
        "does not repeat the same question unnecessarily",
        "keeps context across turns",
    ]
    if scenario_type == "agent_handoff":
        common.append("offers or starts human handoff when automation cannot continue")
    if scenario_type == "fallback_recovery":
        common.append("recovers from unclear input within one clarification turn")
    if scenario_type == "happy_path":
        common.append(f"completes {flow_name} successfully")
    return common


def failure_conditions(scenario_type: str) -> List[str]:
    failures = [
        "wrong intent selected",
        "irrelevant answer",
        "repeated fallback",
        "asks for information already provided",
        "ends the conversation before resolution",
    ]
    if scenario_type == "invalid_information":
        failures.append("accepts invalid user information without validation")
    if scenario_type == "agent_handoff":
        failures.append("refuses handoff when the user explicitly asks")
    return failures


def base_metrics(channel: str, scenario_type: str) -> Dict[str, Any]:
    max_latency = 8.0 if scenario_type == "browser_automation" else 2.0
    return {
        "requires_goal_completion": scenario_type == "happy_path",
        "max_turns": 10,
        "max_fallbacks": 1,
        "max_avg_latency_seconds": max_latency,
        "required_scores": {
            "intent_accuracy": 0.8,
            "response_relevance": 0.8,
            "context_retention": 0.75,
            "user_experience": 0.75,
        },
    }


def build_coverage_matrix(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    matrix: Dict[str, Any] = {"flows": {}, "channels": {}, "scenario_types": {}, "total_cases": len(cases)}
    for case in cases:
        matrix["flows"][case["flow_name"]] = matrix["flows"].get(case["flow_name"], 0) + 1
        matrix["channels"][case["channel"]] = matrix["channels"].get(case["channel"], 0) + 1
        matrix["scenario_types"][case["scenario_type"]] = matrix["scenario_types"].get(case["scenario_type"], 0) + 1
    return matrix


def openai_generate_suite(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    api_key = setting_value("OPENAI_API_KEY")
    if not api_key:
        return None

    model = setting_value("OPENAI_MODEL", "gpt-4.1-mini")
    desired_count = desired_chat_case_count(profile)
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "coverage_matrix", "test_cases"],
        "properties": {
            "name": {"type": "string"},
            "coverage_matrix": {
                "type": "object",
                "additionalProperties": True,
                "properties": {},
            },
            "test_cases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "id",
                        "flow_name",
                        "channel",
                        "scenario_type",
                        "persona",
                        "priority",
                        "goal",
                        "instructions",
                        "expected_outcome",
                        "test_profile",
                        "metric_names",
                        "tags",
                        "steps",
                        "expected_bot_behaviors",
                        "failure_conditions",
                        "metrics",
                    ],
                    "properties": {
                        "id": {"type": "string"},
                        "flow_name": {"type": "string"},
                        "channel": {"type": "string", "enum": ["chat"]},
                        "scenario_type": {"type": "string"},
                        "persona": {"type": "string"},
                        "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "goal": {"type": "string"},
                        "instructions": {"type": "string"},
                        "expected_outcome": {"type": "string"},
                        "test_profile": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                            "properties": {},
                        },
                        "metric_names": {"type": "array", "items": {"type": "string"}},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["utterance"],
                                "properties": {
                                    "condition": {"type": "string"},
                                    "user_intent": {"type": "string"},
                                    "utterance": {"type": "string"},
                                },
                            },
                        },
                        "expected_bot_behaviors": {"type": "array", "items": {"type": "string"}},
                        "failure_conditions": {"type": "array", "items": {"type": "string"}},
                        "metrics": {
                            "type": "object",
                            "additionalProperties": True,
                            "properties": {},
                        },
                    },
                },
            },
        },
    }

    prompt = (
        "Generate a practical QA regression suite for a Yellow.ai chat bot. "
        f"Generate exactly {desired_count} executable chat test cases. "
        "Each test case is an in-house evaluator with instructions, expected outcome, test profile, tags, and metric names. "
        "Cover happy paths, negative paths, missing data, invalid data, user interruptions, fallback recovery, "
        "agent handoff, multilingual behavior when relevant, quick-reply paths, wrong-branch behavior, context retention, and KB/RAG failures. "
        "Return only structured data."
    )
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(profile, indent=2)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "yellow_ai_chat_test_suite",
                "strict": True,
                "schema": schema,
            }
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None

    output_text = raw.get("output_text")
    if not output_text:
        for item in raw.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    output_text = content.get("text")
                    break
    if not output_text:
        return None

    try:
        suite = json.loads(output_text)
    except json.JSONDecodeError:
        return None

    suite["id"] = f"suite_{uuid.uuid4().hex[:10]}"
    suite["created_at"] = now_iso()
    suite["source"] = "openai"
    suite["bot_profile"] = profile
    return suite


def ensure_unique_case_ids(cases: List[Dict[str, Any]]) -> None:
    seen = set()
    for index, case in enumerate(cases, start=1):
        base_id = str(case.get("id") or f"tc_generated_{index}").strip()
        base_id = re.sub(r"[^a-zA-Z0-9_:-]+", "_", base_id).strip("_") or f"tc_generated_{index}"
        candidate = base_id
        suffix = 2
        while candidate in seen:
            candidate = f"{base_id}_{suffix}"
            suffix += 1
        case["id"] = candidate
        seen.add(candidate)


def normalize_suite_case_count(suite: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    desired_count = desired_chat_case_count(profile)
    cases = [case for case in suite.get("test_cases", []) if isinstance(case, dict)]
    chat_cases = []
    for case in cases:
        case["channel"] = str(case.get("channel") or "chat").strip() or "chat"
        if case["channel"] == "chat":
            chat_cases.append(case)

    if len(chat_cases) < desired_count:
        fallback_cases = build_fallback_suite(profile).get("test_cases", [])
        for fallback_case in fallback_cases:
            if len(chat_cases) >= desired_count:
                break
            chat_cases.append(json.loads(json.dumps(fallback_case)))

    suite["test_cases"] = chat_cases[:desired_count]
    suite["requested_chat_case_count"] = desired_count
    ensure_unique_case_ids(suite["test_cases"])
    return suite


def generate_suite(profile: Dict[str, Any]) -> Dict[str, Any]:
    suite = openai_generate_suite(profile) or build_fallback_suite(profile)
    suite = normalize_suite_case_count(suite, profile)
    for case in suite.get("test_cases", []):
        channel = case.get("channel", "chat")
        flow_name = case.get("flow_name", "Unknown Flow")
        scenario_type = case.get("scenario_type", "custom")
        persona = case.get("persona", "calm first-time user")
        case.setdefault("instructions", evaluator_instructions(flow_name, scenario_type, channel, persona))
        case.setdefault("expected_outcome", expected_outcome(flow_name, scenario_type))
        case.setdefault("test_profile", test_profile_for(persona, channel))
        case.setdefault("metric_names", metric_names_for(channel))
        case.setdefault("tags", ["generated", channel, scenario_type, slugify(flow_name)])
        case.setdefault("metrics", base_metrics(channel, scenario_type))
        case.setdefault("yellow_ai", case_yellow_ai_metadata(profile, flow_name, scenario_type, channel))
        case.setdefault(
            "target",
            {
                "chat_endpoint": profile.get("chat_endpoint", ""),
            },
        )
    suite["coverage_matrix"] = build_coverage_matrix(suite.get("test_cases", []))
    suite["yellow_ai_target"] = yellow_ai_target(profile)
    suite["source"] = "playwright_generated"
    suite["automation_type"] = "playwright_markdown"
    suite["automation_script"] = suite_to_chat_automation_script(suite)
    return suite


def compact_script_text(value: Any, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or fallback


def expected_bot_text_for_script(case: Dict[str, Any], step: Optional[Dict[str, Any]] = None) -> str:
    if step:
        step_expected = compact_script_text(
            step.get("expected_bot_response")
            or step.get("expected_text")
            or step.get("condition")
        )
        if step_expected:
            return step_expected
    behaviors = [
        compact_script_text(item)
        for item in case.get("expected_bot_behaviors", [])
        if compact_script_text(item)
    ]
    if behaviors:
        return "Bot should " + "; ".join(behaviors[:3]) + "."
    return compact_script_text(
        case.get("expected_outcome"),
        "Bot responds correctly and keeps the conversation aligned with the test goal.",
    )


def fallback_user_text_for_script(case: Dict[str, Any]) -> str:
    scenario_type = compact_script_text(case.get("scenario_type"), "scenario").replace("_", " ")
    goal = compact_script_text(case.get("goal") or case.get("flow_name"), "this support flow")
    if scenario_type == "happy path":
        return f"I need help with {goal}."
    if "missing information" in scenario_type:
        return f"I need help with {goal}, but I do not have all details ready."
    if "invalid information" in scenario_type:
        return f"I need help with {goal}. I may provide an invalid detail to verify validation."
    if "fallback" in scenario_type:
        return "I am not sure how to explain my issue clearly."
    if "handoff" in scenario_type:
        return f"I need help with {goal} and may need a human agent."
    return f"I need help with {goal}."


def case_turns_for_script(case: Dict[str, Any]) -> List[Dict[str, str]]:
    turns = []
    automation_flow = case.get("automation_flow")
    if isinstance(automation_flow, dict):
        for turn in automation_flow.get("turns", []):
            if not isinstance(turn, dict):
                continue
            user_message = compact_script_text(turn.get("user_message"))
            if not user_message:
                continue
            turns.append(
                {
                    "user": user_message,
                    "bot": compact_script_text(
                        turn.get("expected_bot_response"),
                        expected_bot_text_for_script(case),
                    ),
                }
            )
        if turns:
            return turns[:10]

    for step in case.get("steps", []):
        if not isinstance(step, dict):
            continue
        user_message = compact_script_text(
            step.get("utterance")
            or step.get("user_message")
            or step.get("message")
            or step.get("input")
        )
        if not user_message:
            continue
        turns.append(
            {
                "user": user_message,
                "bot": expected_bot_text_for_script(case, step),
            }
        )
    if turns:
        return turns[:10]
    return [
        {
            "user": fallback_user_text_for_script(case),
            "bot": expected_bot_text_for_script(case),
        }
    ]


def suite_to_chat_automation_script(suite: Dict[str, Any], channel_filter: str = "chat") -> str:
    blocks = []
    for index, case in enumerate(suite.get("test_cases", []), start=1):
        channel = compact_script_text(case.get("channel"), "chat")
        if channel != "chat":
            continue
        if channel_filter not in ("all", "chat") and channel != channel_filter:
            continue
        title_parts = [
            compact_script_text(case.get("flow_name"), f"Chat flow {index}"),
            compact_script_text(case.get("scenario_type"), "scenario").replace("_", " "),
        ]
        lines = [
            f"## {' - '.join(part for part in title_parts if part)}",
            "",
            "#### Conversation Flow",
            "",
        ]
        for turn_index, turn in enumerate(case_turns_for_script(case), start=1):
            lines.extend(
                [
                    f"###### Turn {turn_index}",
                    "**User:**",
                    f">> {compact_script_text(turn.get('user'), fallback_user_text_for_script(case))}",
                    "",
                    "**Bot:**",
                    f">> {compact_script_text(turn.get('bot'), expected_bot_text_for_script(case))}",
                    "",
                ]
            )
        blocks.append("\n".join(lines).strip())
    return "\n\n------\n".join(blocks)


def run_case(case: Dict[str, Any], suite: Dict[str, Any]) -> Dict[str, Any]:
    raise ValueError("Generated suites run through Playwright chat automation. Use run_suite instead of run_case.")


def score_result(case: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    transcript = result["transcript"]
    bot_turns = [turn for turn in transcript if turn["speaker"] == "bot"]
    text = " ".join(turn["text"].lower() for turn in transcript)
    fallback_count = sum(1 for turn in bot_turns if "understood" in turn["text"].lower() or "not sure" in turn["text"].lower())
    avg_latency = 0.0
    latency_values = [turn.get("latency_seconds") for turn in bot_turns if turn.get("latency_seconds") is not None]
    if latency_values:
        avg_latency = sum(latency_values) / len(latency_values)

    max_turns = case["metrics"].get("max_turns", 10)
    max_fallbacks = case["metrics"].get("max_fallbacks", 1)
    max_latency = case["metrics"].get("max_avg_latency_seconds", 3.0)
    goal_completed = "completed" in text or case["scenario_type"] != "happy_path"

    metrics = {
        "goal_completion": 1.0 if goal_completed else 0.0,
        "turn_efficiency": max(0.0, min(1.0, 1 - ((len(transcript) - max_turns) / max_turns))),
        "fallback_control": 1.0 if fallback_count <= max_fallbacks else 0.4,
        "latency": 1.0 if avg_latency <= max_latency else max(0.2, max_latency / avg_latency),
        "intent_accuracy": 0.88,
        "response_relevance": 0.84,
        "context_retention": 0.8,
        "user_experience": 0.82,
    }
    overall = round(sum(metrics.values()) / len(metrics), 3)
    issues = []
    if metrics["goal_completion"] < 1:
        issues.append("Goal was not completed in the transcript.")
    if fallback_count > max_fallbacks:
        issues.append("Fallback was triggered more often than allowed.")
    if avg_latency > max_latency:
        issues.append("Average latency exceeded the configured threshold.")
    if len(transcript) > max_turns:
        issues.append("Conversation took more turns than expected.")

    return {
        "overall_score": overall,
        "status": "pass" if overall >= 0.78 and not issues else "review",
        "metrics": metrics,
        "observed": {
            "turn_count": len(transcript),
            "fallback_count": fallback_count,
            "avg_latency_seconds": round(avg_latency, 2),
        },
        "issues": issues,
    }


def recommendations_for(case: Dict[str, Any], score: Dict[str, Any]) -> List[Dict[str, str]]:
    recommendations = []
    flow = case["flow_name"]
    yellow_ai = case.get("yellow_ai", {})
    default_module = yellow_ai.get("module", "Conversation design")
    target = yellow_ai.get("target", {})
    target_hint = yellow_ai_target_hint(target)
    if not score["issues"]:
        return [
            {
                "area": f"{flow} flow",
                "recommendation": "Keep this flow in regression. No immediate change required from the latest run.",
                "yellow_ai_hint": f"Monitor intent confidence and completion rate in {target_hint}.",
                "module": default_module,
                "failure_mode": "Regression guardrail",
            }
        ]

    for issue in score["issues"]:
        if "Goal" in issue:
            recommendations.append(
                {
                    "area": f"{flow} completion logic",
                    "recommendation": "Add an explicit terminal success branch and confirmation message.",
                    "yellow_ai_hint": f"Check the specialist agent goal, workflow terminal node, context variables, and success transition in {target_hint}.",
                    "module": "Workflow/API",
                    "failure_mode": "No terminal success output",
                }
            )
        elif "Fallback" in issue:
            recommendations.append(
                {
                    "area": f"{flow} routing and fallback",
                    "recommendation": "Tighten the agent trigger, add failed utterances as examples, and improve one-turn clarification copy.",
                    "yellow_ai_hint": f"Review Super Agent routing, specialist trigger text, fallback journey, and Testing Lab examples in {target_hint}.",
                    "module": "Agent routing",
                    "failure_mode": "Repeated fallback or wrong specialist selection",
                }
            )
        elif "latency" in issue:
            recommendations.append(
                {
                    "area": f"{flow} response latency",
                    "recommendation": "Inspect API/webhook nodes and reduce slow dependency calls.",
                    "yellow_ai_hint": "Check workflow/API node timings, external endpoint latency, retries, and widget response latency.",
                    "module": "Workflow/API",
                    "failure_mode": "Slow dependency or widget latency",
                }
            )
        else:
            recommendations.append(
                {
                    "area": f"{flow} conversation design",
                    "recommendation": "Reduce repeated prompts and preserve captured entities in context.",
                    "yellow_ai_hint": f"Review entity capture, variable persistence, loopback transitions, and workflow output mapping in {target_hint}.",
                    "module": default_module,
                    "failure_mode": "Context or output mapping issue",
                }
            )
    return recommendations


def yellow_ai_target_hint(target: Dict[str, str]) -> str:
    if not target:
        return "the relevant Yellow.ai module"
    parts = []
    if target.get("platform"):
        parts.append(target["platform"].title())
    if target.get("bot_id"):
        parts.append(f"bot {target['bot_id']}")
    if target.get("agent_name"):
        parts.append(f"agent {target['agent_name']}")
    if target.get("workflow_name"):
        parts.append(f"workflow {target['workflow_name']}")
    if target.get("tool_name"):
        parts.append(f"tool {target['tool_name']}")
    if target.get("kb_name"):
        parts.append(f"KB {target['kb_name']}")
    return ", ".join(parts) or "the relevant Yellow.ai module"


def run_suite(suite: Dict[str, Any], channel_filter: str = "all") -> Dict[str, Any]:
    script = str(suite.get("automation_script") or "").strip()
    if not script:
        script = suite_to_chat_automation_script(suite, channel_filter)
        suite["automation_script"] = script
        suite["automation_type"] = "playwright_markdown"
        suite["source"] = "playwright_generated"
    if not script:
        raise ValueError("This suite does not contain chat cases that can be run through Playwright.")

    output = chat_automation.run_chat_automation(
        suite.get("bot_profile", {}),
        script,
        setting_value,
        ROOT,
        {},
    )
    output["suite"] = suite
    output["run"]["suite_id"] = suite["id"]
    output["report"]["suite_id"] = suite["id"]
    output["run"]["source"] = "playwright_generated_suite"
    output["report"]["summary"]["source_suite"] = {
        "id": suite["id"],
        "name": suite.get("name", "Generated chat suite"),
        "source": suite.get("source", "playwright_generated"),
    }
    output["report"]["summary"]["yellow_ai_target"] = suite.get(
        "yellow_ai_target",
        yellow_ai_target(suite.get("bot_profile", {})),
    )

    runnable_cases = [
        case
        for case in suite.get("test_cases", [])
        if case.get("channel", "chat") == "chat" and channel_filter in ("all", "chat", case.get("channel", "chat"))
    ]
    for case_result, planned_case in zip(output["report"].get("case_results", []), runnable_cases):
        case_result["planned_case_id"] = planned_case.get("id", case_result.get("case_id", ""))
        case_result["yellow_ai"] = planned_case.get("yellow_ai", case_result.get("yellow_ai", {}))
        case_result["planned_goal"] = planned_case.get("goal", case_result.get("goal", ""))
        case_result["failure_conditions"] = planned_case.get("failure_conditions", [])
    output["report"]["summary"]["yellow_ai_modules"] = module_summary(output["report"].get("case_results", []))
    return output


def flatten_recommendations(case_results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    seen = set()
    flattened = []
    for item in case_results:
        for recommendation in item["recommendations"]:
            key = (recommendation["area"], recommendation["recommendation"])
            if key in seen:
                continue
            seen.add(key)
            flattened.append(
                {
                    "flow_name": item["flow_name"],
                    "channel": item["channel"],
                    **recommendation,
                }
            )
    return flattened[:30]


def adapter_summary(case_results: List[Dict[str, Any]]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for item in case_results:
        adapter = item["result"].get("adapter", "unknown")
        summary[adapter] = summary.get(adapter, 0) + 1
    return summary


def module_summary(case_results: List[Dict[str, Any]]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for item in case_results:
        module = item.get("yellow_ai", {}).get("module", "Unmapped")
        summary[module] = summary.get(module, 0) + 1
    return summary


class AppHandler(BaseHTTPRequestHandler):
    server_version = "YellowAIChatQA/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            text_response(self, (STATIC_DIR / "index.html").read_text(encoding="utf-8"))
            return
        if path.startswith("/static/"):
            target = STATIC_DIR / path.replace("/static/", "", 1)
            if target.exists() and target.is_file():
                content_type = "text/css" if target.suffix == ".css" else "application/javascript"
                text_response(self, target.read_text(encoding="utf-8"), content_type)
                return
        if path == "/api/health":
            json_response(self, {"ok": True, "time": now_iso()})
            return
        if path == "/api/auth/session":
            json_response(self, auth_payload(auth_backend.user_from_handler(self)))
            return

        user = request_user(self)
        if not user:
            return
        try:
            state = load_state()
            project_id = workspace_backend.resolve_project_id(state, query.get("project_id", [""])[0])

            if path == "/api/config":
                json_response(self, public_config())
                return
            if path == "/api/projects":
                json_response(self, {"projects": state["projects"], "active_project_id": project_id})
                return
            if path == "/api/project-access":
                json_response(self, project_access_response(state, project_id))
                return
            if path == "/api/chats":
                mode = query.get("mode", [""])[0]
                chats = workspace_backend.filter_project_items(state["chats"], project_id)
                if mode:
                    chats = [chat for chat in chats if chat.get("mode") == mode]
                json_response(self, {"chats": chats})
                return
            if path == "/api/suites":
                json_response(self, workspace_backend.filter_project_items(state["suites"], project_id))
                return
            if path == "/api/runs":
                json_response(self, workspace_backend.filter_project_items(state["runs"], project_id))
                return
            if path == "/api/documents":
                json_response(
                    self,
                    {
                        "documents": workspace_backend.filter_project_items(state["documents"], project_id),
                        "change_plans": workspace_backend.filter_project_items(state["change_plans"], project_id),
                    },
                )
                return
            if path == "/api/platform-snapshots":
                json_response(self, {"snapshots": workspace_backend.filter_project_items(state["platform_snapshots"], project_id)})
                return
            if path == "/api/docs/pages":
                json_response(self, {"pages": workspace_backend.docs_pages(ROOT)})
                return
            if path.startswith("/api/reports/"):
                report_id = path.rsplit("/", 1)[-1]
                report = next((item for item in state["reports"] if item["id"] == report_id), None)
                if not report:
                    error_response(self, "Report not found", 404)
                    return
                json_response(self, report)
                return
            error_response(self, "Not found", 404)
        finally:
            auth_backend.clear_current_user()

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/auth/login":
                body = read_json_body(self)
                complete_auth(self, auth_backend.login(body.get("email", ""), body.get("password", "")))
                return

            if path == "/api/auth/signup":
                body = read_json_body(self)
                complete_auth(
                    self,
                    auth_backend.signup(body.get("email", ""), body.get("password", ""), body.get("full_name", "")),
                )
                return

            if path == "/api/auth/logout":
                json_response(self, auth_payload(None), headers={"Set-Cookie": auth_backend.clear_cookie()})
                return

            user = request_user(self)
            if not user:
                return

            if path == "/api/projects":
                state = load_state()
                project = workspace_backend.create_project(state, read_json_body(self))
                save_state(state)
                json_response(self, project)
                return

            if path == "/api/chats":
                state = load_state()
                chat = workspace_backend.create_chat(state, read_json_body(self))
                save_state(state)
                json_response(self, chat)
                return

            if path == "/api/project-access":
                body = read_json_body(self)
                state = load_state()
                project_id = workspace_backend.resolve_project_id(state, str(body.get("project_id", "")))
                access = workspace_backend.update_project_access(state, project_id, body)
                save_state(state)
                if not access.get("api_key_configured") and setting_value("YELLOW_AI_API_KEY", ""):
                    access["api_key_configured"] = True
                json_response(self, access)
                return

            if path.startswith("/api/projects/") and path.endswith("/goal-brief"):
                body = read_json_body(self)
                project_id = path.split("/")[3]
                state = load_state()
                project_id = workspace_backend.resolve_project_id(state, project_id)
                brief = workspace_backend.prepare_goal_test_brief(
                    state,
                    project_id,
                    setting_value,
                    YELLOW_AI_V3_ANALYZER_RUBRIC,
                    ROOT,
                    chat_id=str(body.get("chat_id", "")),
                    instruction=str(body.get("instruction", "")),
                )
                save_state(state)
                json_response(self, {"brief": brief, "project": workspace_backend.get_project(state, project_id)})
                return

            if path.startswith("/api/chats/") and path.endswith("/messages"):
                chat_id = path.split("/")[3]
                body = read_json_body(self)
                state = load_state()
                chat = workspace_backend.add_chat_message(
                    state,
                    chat_id,
                    body.get("content", ""),
                    setting_value,
                    YELLOW_AI_V3_ANALYZER_RUBRIC,
                    ROOT,
                )
                save_state(state)
                json_response(self, chat)
                return

            if path == "/api/docs/search":
                body = read_json_body(self)
                state = load_state()
                project_id = workspace_backend.resolve_project_id(state, str(body.get("project_id", "")))
                json_response(self, {"results": workspace_backend.search_docs(state, ROOT, body.get("query", ""), project_id)})
                return

            if path == "/api/generate-suite":
                body = read_json_body(self)
                state = load_state()
                project_id = workspace_backend.resolve_project_id(state, str(body.get("project_id", "")))
                project = workspace_backend.get_project(state, project_id)
                profile = body.get("bot_profile") or project.get("bot_profile", {}) or body
                suite = generate_suite(profile)
                suite["project_id"] = project_id
                state["suites"].insert(0, suite)
                workspace_backend.update_project_profile(state, project_id, profile)
                save_state(state)
                json_response(self, suite)
                return

            if path == "/api/run-suite":
                body = read_json_body(self)
                suite_id = body.get("suite_id")
                channel_filter = body.get("channel", "all")
                state = load_state()
                suite = next((item for item in state["suites"] if item["id"] == suite_id), None)
                if not suite:
                    error_response(self, "Suite not found", 404)
                    return
                output = run_suite(suite, channel_filter)
                project_id = workspace_backend.resolve_project_id(state, suite.get("project_id", ""))
                output["run"]["project_id"] = project_id
                output["report"]["project_id"] = project_id
                state["runs"].insert(0, output["run"])
                state["reports"].insert(0, output["report"])
                save_state(state)
                json_response(self, output)
                return

            if path == "/api/chat-automation/run":
                body = read_json_body(self)
                state = load_state()
                project_id = workspace_backend.resolve_project_id(state, str(body.get("project_id", "")))
                project = workspace_backend.get_project(state, project_id)
                profile = body.get("bot_profile") or project.get("bot_profile", {}) or {}
                if not isinstance(profile, dict):
                    error_response(self, "bot_profile must be an object", 400)
                    return
                options = body.get("options") if isinstance(body.get("options"), dict) else {}
                output = chat_automation.run_chat_automation(
                    profile,
                    str(body.get("script") or ""),
                    setting_value,
                    ROOT,
                    options,
                )
                output["suite"]["project_id"] = project_id
                output["suite"]["yellow_ai_target"] = yellow_ai_target(profile)
                output["run"]["project_id"] = project_id
                output["report"]["project_id"] = project_id
                state["suites"].insert(0, output["suite"])
                state["runs"].insert(0, output["run"])
                state["reports"].insert(0, output["report"])
                workspace_backend.update_project_profile(state, project_id, profile)
                save_state(state)
                json_response(self, output)
                return

            if path == "/api/chat-automation/goal-run":
                body = read_json_body(self)
                state = load_state()
                project_id = workspace_backend.resolve_project_id(state, str(body.get("project_id", "")))
                project = workspace_backend.get_project(state, project_id)
                profile = body.get("bot_profile") or project.get("bot_profile", {}) or {}
                if not isinstance(profile, dict):
                    error_response(self, "bot_profile must be an object", 400)
                    return
                options = body.get("options") if isinstance(body.get("options"), dict) else {}
                output = chat_automation.run_goal_chat_automation(
                    profile,
                    str(body.get("goal") or options.get("goal") or ""),
                    setting_value,
                    ROOT,
                    options,
                )
                output["suite"]["project_id"] = project_id
                output["suite"]["yellow_ai_target"] = yellow_ai_target(profile)
                output["run"]["project_id"] = project_id
                output["report"]["project_id"] = project_id
                state["suites"].insert(0, output["suite"])
                state["runs"].insert(0, output["run"])
                state["reports"].insert(0, output["report"])
                workspace_backend.update_project_profile(state, project_id, profile)
                save_state(state)
                json_response(self, output)
                return

            if path == "/api/platform-snapshots/run":
                body = read_json_body(self)
                state = load_state()
                project_id = workspace_backend.resolve_project_id(state, str(body.get("project_id", "")))
                project = workspace_backend.get_project(state, project_id)
                profile = body.get("bot_profile") or project.get("bot_profile", {}) or {}
                if not isinstance(profile, dict):
                    error_response(self, "bot_profile must be an object", 400)
                    return
                options = body.get("options") if isinstance(body.get("options"), dict) else {}
                snapshot = platform_snapshot.run_platform_snapshot(profile, setting_value, ROOT, options)
                snapshot["project_id"] = project_id
                state["platform_snapshots"].insert(0, snapshot)
                workspace_backend.update_project_profile(state, project_id, profile)
                save_state(state)
                json_response(self, snapshot)
                return

            if path == "/api/config":
                body = read_json_body(self)
                settings = body.get("settings", body)
                if not isinstance(settings, dict):
                    error_response(self, "Settings payload must be an object", 400)
                    return
                json_response(self, update_runtime_settings(settings))
                return

            if path == "/api/documents/upload":
                upload = read_multipart_upload(self)
                json_response(self, store_uploaded_document(upload, upload.get("project_id", "")))
                return

            if path == "/api/documents/analyze":
                body = read_json_body(self)
                document_id = body.get("document_id", "")
                profile = body.get("bot_profile") or body.get("profile") or {}
                project_id = body.get("project_id", "")
                if not document_id:
                    error_response(self, "document_id is required", 400)
                    return
                json_response(self, analyze_document(document_id, profile, project_id))
                return

            if path.startswith("/api/change-plans/") and path.endswith("/approve"):
                plan_id = path.split("/")[3]
                json_response(self, approve_change_plan(plan_id))
                return

            error_response(self, "Not found", 404)
        except json.JSONDecodeError:
            error_response(self, "Invalid JSON", 400)
        except ValueError as exc:
            error_response(self, str(exc), 400)
        except Exception as exc:
            error_response(self, f"Server error: {exc}", 500)
        finally:
            auth_backend.clear_current_user()

    def do_PATCH(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            user = request_user(self)
            if not user:
                return
            if path.startswith("/api/projects/"):
                project_id = path.rsplit("/", 1)[-1]
                state = load_state()
                project = workspace_backend.update_project(state, project_id, read_json_body(self))
                save_state(state)
                json_response(self, project)
                return
            error_response(self, "Not found", 404)
        except json.JSONDecodeError:
            error_response(self, "Invalid JSON", 400)
        except ValueError as exc:
            error_response(self, str(exc), 400)
        except Exception as exc:
            error_response(self, f"Server error: {exc}", 500)
        finally:
            auth_backend.clear_current_user()

    def log_message(self, format: str, *args: Any) -> None:
        print("[%s] %s" % (self.log_date_time_string(), format % args))


def main() -> None:
    port = int(os.environ.get("APP_PORT", "8787"))
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    print(f"Yellow.ai Chat QA Workbench running at http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")


if __name__ == "__main__":
    main()
