import re
import uuid
from datetime import datetime
from typing import Any, Dict, List


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def slugify(value: str) -> str:
    value = str(value or "").lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "item"


def unique_strings(values: List[str], limit: int = 30, preserve_edges: bool = False) -> List[str]:
    output: List[str] = []
    seen = set()
    for raw in values:
        value = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not preserve_edges:
            value = re.sub(r"^[^\w]+|[^\w]+$", "", value).strip()
        if not value or len(value) > 140:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
        if len(output) >= limit:
            break
    return output


def page_text(snapshot: Dict[str, Any]) -> str:
    parts = []
    for page in snapshot.get("pages", []):
        parts.append(str(page.get("label", "")))
        parts.append(str(page.get("title", "")))
        parts.append(str(page.get("text_preview", "")))
    return "\n".join(parts)


def pages_by_label(snapshot: Dict[str, Any], *needles: str) -> List[Dict[str, Any]]:
    lowered = [needle.lower() for needle in needles]
    return [
        page
        for page in snapshot.get("pages", [])
        if any(needle in str(page.get("label", "")).lower() or needle in str(page.get("url", "")).lower() for needle in lowered)
    ]


def discover_bot(snapshot: Dict[str, Any], current_profile: Dict[str, Any]) -> Dict[str, Any]:
    text = page_text(snapshot)
    bot_id = str(snapshot.get("bot_id") or current_profile.get("yellow_ai_bot_id") or "").strip()
    ui_base_url = str(snapshot.get("ui_base_url") or current_profile.get("yellow_ai_ui_base_url") or "https://cloud.yellow.ai").strip().rstrip("/")
    platform = infer_platform(text, current_profile)
    bot_name = infer_bot_name(snapshot, current_profile)
    super_agent = infer_super_agent(snapshot, bot_name, current_profile)
    agents = extract_agents(snapshot)
    flows = extract_flows(snapshot)
    kb_documents = extract_kb_documents(snapshot)
    menu_options = extract_menu_options(snapshot)
    modules = infer_modules(snapshot, agents, flows, kb_documents)
    business_goal = infer_business_goal(super_agent, agents, flows, kb_documents, current_profile)
    flow_docs = build_flow_docs(platform, super_agent, agents, flows, menu_options, kb_documents)
    recommended_tests = recommended_test_areas(modules, flows, kb_documents, menu_options)

    profile_patch = {
        "bot_name": bot_name,
        "business_goal": business_goal,
        "flow_docs": flow_docs,
        "flows": flows_to_profile_flows(flows, menu_options, kb_documents),
        "yellow_ai_bot_id": bot_id,
        "yellow_ai_platform": platform,
        "yellow_ai_environment": str(current_profile.get("yellow_ai_environment") or "Sandbox").strip(),
        "yellow_ai_super_agent": super_agent,
        "yellow_ai_agent_name": agents[0]["name"] if agents else str(current_profile.get("yellow_ai_agent_name", "")),
        "yellow_ai_kb_name": "Knowledge base" if kb_documents else str(current_profile.get("yellow_ai_kb_name", "")),
        "yellow_ai_ui_base_url": ui_base_url or "https://cloud.yellow.ai",
        "yellow_ai_console_url": f"{ui_base_url}/bot/{bot_id}/overview" if ui_base_url and bot_id else str(current_profile.get("yellow_ai_console_url", "")),
    }
    if bot_id and not str(profile_patch.get("chat_endpoint", "")).strip():
        profile_patch["chat_endpoint"] = current_profile.get("chat_endpoint") or f"{ui_base_url}/liveBot/{bot_id}?region="

    discovery = {
        "id": f"discovery_{uuid.uuid4().hex[:10]}",
        "created_at": now_iso(),
        "source": "yellow_ai_snapshot",
        "snapshot_id": snapshot.get("id", ""),
        "status": "ok" if snapshot.get("status") == "ok" else snapshot.get("status", "unknown"),
        "bot_id": bot_id,
        "bot_name": bot_name,
        "platform": platform,
        "super_agent": super_agent,
        "agents": agents,
        "flows": flows,
        "menu_options": menu_options,
        "kb_documents": kb_documents,
        "modules": modules,
        "recommended_tests": recommended_tests,
        "profile_patch": {key: value for key, value in profile_patch.items() if value not in ["", [], {}]},
        "summary": summarize(bot_name, platform, super_agent, agents, flows, menu_options, kb_documents),
    }
    return discovery


def infer_platform(text: str, profile: Dict[str, Any]) -> str:
    if "Super agent" in text or "studio/ai-agent" in text or "AI Safety & Conduct" in text:
        return "nexus"
    if "studio/build/flows" in text or "Automation" in text:
        return "cloud"
    return str(profile.get("yellow_ai_platform") or "nexus").strip() or "nexus"


def infer_bot_name(snapshot: Dict[str, Any], profile: Dict[str, Any]) -> str:
    candidates = []
    for page in snapshot.get("pages", []):
        text = str(page.get("text_preview", ""))
        for pattern in [
            r"heading\s+\"([^\"]+)\"",
            r"\b([A-Z][A-Za-z0-9 &/-]{2,40}\s+(?:HR|Bot|Assistant|Agent))\b",
        ]:
            candidates.extend(re.findall(pattern, text))
    cleaned = unique_strings(candidates, 8)
    if cleaned:
        return cleaned[0]
    return str(profile.get("bot_name") or "Yellow.ai Bot").strip()


def infer_super_agent(snapshot: Dict[str, Any], bot_name: str, profile: Dict[str, Any]) -> str:
    for page in pages_by_label(snapshot, "super agent", "ai-agent/profile"):
        text = str(page.get("text_preview", ""))
        match = re.search(r"heading\s+\"?([^\"\n]{2,80})\"?\s+\[level=3\]", text)
        if match:
            return match.group(1).strip()
    return str(profile.get("yellow_ai_super_agent") or bot_name).strip()


def extract_agents(snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    agents = []
    for page in pages_by_label(snapshot, "agents"):
        signals = page.get("signals", {})
        for table in signals.get("tables", []):
            for row in table:
                if len(row) < 2:
                    continue
                name = clean_cell(row[0])
                trigger = clean_cell(row[1])
                if name and name.lower() not in {"agent name", "super agent"} and "using gpt" not in name.lower():
                    agents.append({"name": name, "trigger": trigger})
    return dedupe_dicts(agents, "name", 20)


def extract_flows(snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    flows = []
    for page in pages_by_label(snapshot, "flows", "workflows"):
        signals = page.get("signals", {})
        for table in signals.get("tables", []):
            for row in table:
                if len(row) < 2:
                    continue
                name = clean_cell(row[0])
                description = clean_cell(row[1])
                if name and name.lower() not in {"flow name", "workflow name"}:
                    flows.append({"name": strip_status_words(name), "description": description})
    return dedupe_dicts(flows, "name", 30)


def extract_kb_documents(snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    docs = []
    for page in pages_by_label(snapshot, "knowledge", "kb/files"):
        signals = page.get("signals", {})
        for table in signals.get("tables", []):
            for row in table:
                if len(row) < 2:
                    continue
                name = clean_cell(row[0])
                if not name or name.lower() in {"file name", "documents"}:
                    continue
                docs.append(
                    {
                        "name": strip_status_words(name),
                        "source": clean_cell(row[1]) if len(row) > 1 else "",
                        "status": clean_cell(row[2]) if len(row) > 2 else "",
                        "updated_at_label": clean_cell(row[3]) if len(row) > 3 else "",
                    }
                )
    return dedupe_dicts(docs, "name", 80)


def extract_menu_options(snapshot: Dict[str, Any]) -> List[str]:
    options: List[str] = []
    for page in snapshot.get("pages", []):
        signals = page.get("signals", {})
        for button in signals.get("buttons", []):
            text = str(button.get("text") or button.get("aria") or "")
            if is_quick_reply(text):
                options.append(text)
    return unique_strings(options, 20, preserve_edges=True)


def is_quick_reply(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return False
    keywords = ["queries", "leave", "personal information", "document request", "policy", "payroll", "attendance", "pf"]
    return any(keyword in cleaned.lower() for keyword in keywords) and len(cleaned) < 90


def infer_modules(snapshot: Dict[str, Any], agents: List[Dict[str, str]], flows: List[Dict[str, str]], docs: List[Dict[str, str]]) -> Dict[str, int]:
    text = page_text(snapshot).lower()
    return {
        "agents": len(agents),
        "flows": len(flows),
        "knowledge_documents": len(docs),
        "tools_or_functions": len(re.findall(r"\b(function|api|tool|workflow)\b", text)),
        "test_suites": len(re.findall(r"\b(test suite|test case)\b", text)),
    }


def infer_business_goal(
    super_agent: str,
    agents: List[Dict[str, str]],
    flows: List[Dict[str, str]],
    docs: List[Dict[str, str]],
    profile: Dict[str, Any],
) -> str:
    existing = str(profile.get("business_goal") or "").strip()
    if existing and "order" not in existing.lower() and "refund" not in existing.lower():
        return existing
    if docs and any(token in " ".join(doc["name"] for doc in docs).lower() for token in ["policy", "payroll", "attendance", "leave", "pf"]):
        return f"Help employees resolve HR policy, payroll, PF, attendance, leave, personal information, and document questions through {super_agent or 'the HR assistant'}."
    if agents:
        return f"Route user requests to the right Yellow.ai agent and answer supported queries through {super_agent or 'the bot'}."
    if flows:
        return f"Guide users through {', '.join(flow['name'] for flow in flows[:4])}."
    return existing or "Help users complete the bot's primary support journeys."


def build_flow_docs(
    platform: str,
    super_agent: str,
    agents: List[Dict[str, str]],
    flows: List[Dict[str, str]],
    menu_options: List[str],
    docs: List[Dict[str, str]],
) -> str:
    parts = [f"{platform.title()} bot discovered from read-only Yellow.ai snapshot."]
    if super_agent:
        parts.append(f"Super agent: {super_agent}.")
    if flows:
        parts.append("Flows/workflows: " + ", ".join(flow["name"] for flow in flows[:12]) + ".")
    if menu_options:
        parts.append("Main menu quick replies: " + ", ".join(menu_options[:12]) + ".")
    if agents:
        parts.append("Agents: " + "; ".join(f"{agent['name']} - {agent.get('trigger', '')}" for agent in agents[:8]) + ".")
    if docs:
        parts.append("Knowledge base documents include: " + ", ".join(doc["name"] for doc in docs[:12]) + ".")
    return " ".join(parts)


def flows_to_profile_flows(flows: List[Dict[str, str]], menu_options: List[str], docs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if menu_options:
        return [{"name": option, "description": "Visible bot quick reply/menu option."} for option in menu_options[:12]]
    if flows:
        return flows[:12]
    if docs:
        topics = []
        for doc in docs[:8]:
            name = re.sub(r"[_-]+", " ", doc["name"])
            name = re.sub(r"\.(pdf|docx?|xlsx?|csv)$", "", name, flags=re.I)
            topics.append({"name": name[:70], "description": f"Knowledge-base topic from {doc['name']}"})
        return topics
    return []


def recommended_test_areas(modules: Dict[str, int], flows: List[Dict[str, str]], docs: List[Dict[str, str]], menu_options: List[str]) -> List[str]:
    tests = []
    if menu_options:
        tests.append("Quick-reply routing coverage for every visible menu option")
    if docs:
        tests.append("Knowledge-base grounding, no-answer behavior, and hallucination control")
    if flows:
        tests.append("Welcome/main flow continuity, fallback recovery, and completion behavior")
    if modules.get("agents"):
        tests.append("Super-agent to specialist-agent routing accuracy")
    tests.append("Out-of-scope and live-agent handoff behavior")
    return tests


def summarize(bot_name: str, platform: str, super_agent: str, agents: List[Dict[str, str]], flows: List[Dict[str, str]], menu_options: List[str], docs: List[Dict[str, str]]) -> str:
    return (
        f"Discovered {bot_name or 'Yellow.ai bot'} as a {platform} bot"
        f"{f' with super agent {super_agent}' if super_agent else ''}. "
        f"Captured {len(agents)} agents, {len(flows)} flows/workflows, {len(menu_options)} menu options, and {len(docs)} KB documents."
    )


def clean_cell(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"[^\w\s&/().,:+-]+", " ", text).strip()
    return re.sub(r"\s+", " ", text)


def strip_status_words(value: str) -> str:
    text = re.sub(r"\b(Start flow|Preview|completed|yellowmessenger)\b", "", value, flags=re.I)
    text = re.sub(r"\b\d{1,2}/\d{1,2}/\d{4}.*$", "", text)
    text = re.sub(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{4}\b.*$", "", text)
    return re.sub(r"\s+", " ", text).strip(" -")


def dedupe_dicts(items: List[Dict[str, str]], key: str, limit: int) -> List[Dict[str, str]]:
    output = []
    seen = set()
    for item in items:
        value = str(item.get(key, "")).strip()
        if not value:
            continue
        slug = slugify(value)
        if slug in seen:
            continue
        seen.add(slug)
        output.append(item)
        if len(output) >= limit:
            break
    return output
