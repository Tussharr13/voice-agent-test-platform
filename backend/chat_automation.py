import json
import re
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


DEFAULT_SCRIPT = """## Greeting and scope

#### Conversation Flow

###### Turn 1
**User:**
>> Hi, what can you help me with?

**Bot:**
>> Bot greets the user and explains the support scope or asks what help is needed.

------
## Product recommendation

#### Conversation Flow

###### Turn 1
**User:**
>> I am looking for a water purifier for a small family. Can you guide me?

**Bot:**
>> Bot asks about user needs or recommends relevant product categories, features, or next steps.

------
## Service issue

#### Conversation Flow

###### Turn 1
**User:**
>> My purifier is not working and I need service support.

**Bot:**
>> Bot acknowledges the service issue and asks for product, location, contact, warranty, or service booking details.

------
## Installation request

#### Conversation Flow

###### Turn 1
**User:**
>> I bought a purifier and need installation help.

**Bot:**
>> Bot guides installation scheduling or asks for contact, address, and product details.

------
## Unsupported order tracking

#### Conversation Flow

###### Turn 1
**User:**
>> Track my order ID ORD12345.

**Bot:**
>> If order tracking is unavailable, bot explains the limitation and offers a useful next step or support handoff.

------
## Customer care handoff

#### Conversation Flow

###### Turn 1
**User:**
>> I want to speak to a human customer care agent.

**Bot:**
>> Bot offers customer care details, escalation, or asks enough information to route the user to support.

------
## Fallback clarification

#### Conversation Flow

###### Turn 1
**User:**
>> blorpy invoice magic banana.

**Bot:**
>> Bot handles the unclear request with a clarification question and does not invent unsupported information.
"""


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "flow"


def playwright_status() -> Dict[str, Any]:
    try:
        import playwright.sync_api  # noqa: F401
    except Exception as exc:
        return {
            "available": False,
            "package": "missing",
            "message": f"Python Playwright is not available: {exc}",
        }
    return {
        "available": True,
        "package": "python-playwright",
        "message": "Ready to run web-widget chat automation when URL and selectors are configured.",
    }


def default_config(profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "url": str(profile.get("chat_endpoint") or profile.get("chat_widget_url") or "").strip(),
        "launcher_selector": str(
            profile.get("chat_launcher_selector")
            or "#ymDivBar, button[aria-label*='bot' i], button[aria-label*='chat' i], [role='button'][aria-label*='bot' i]"
        ).strip(),
        "input_selector": str(
            profile.get("chat_input_selector")
            or "input[placeholder='Type your message'], input[aria-label='Type your message'], input[type='text'], textarea, input:not([type]), [contenteditable='true'], [role='textbox'], textarea[placeholder*='message' i], input[placeholder*='message' i], textarea[placeholder*='type' i], input[placeholder*='type' i]"
        ).strip(),
        "message_selector": str(
            profile.get("chat_message_selector")
            or "[role='group'][aria-label='bot replied'], [aria-label*='bot replied' i], [data-testid*='message'], .message, .chat-message, [class*='message']"
        ).strip(),
        "send_selector": str(profile.get("chat_send_selector") or "").strip(),
        "frame_hint": str(profile.get("chat_frame_hint") or "ymlIframe").strip(),
        "ready_selector": str(profile.get("chat_ready_selector") or "").strip(),
        "response_timeout_seconds": safe_int(profile.get("chat_response_timeout_seconds"), 45),
        "stability_seconds": safe_float(profile.get("chat_stability_seconds"), 1.5),
        "headless": str(profile.get("chat_playwright_headless", "true")).lower() != "false",
    }


def safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def parse_markdown_script(markdown: str) -> List[Dict[str, Any]]:
    text = (markdown or "").strip()
    if not text:
        text = DEFAULT_SCRIPT

    flows: List[Dict[str, Any]] = []
    flow_title = "Chat automation flow"
    turns: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    mode = ""

    def commit_turn() -> None:
        nonlocal current
        if not current:
            return
        if current.get("user_message") or current.get("expected_bot_response"):
            current["turn_number"] = len(turns) + 1
            normalize_turn_action(current)
            turns.append(current)
        current = None

    def commit_flow() -> None:
        nonlocal turns
        commit_turn()
        if turns:
            flows.append(
                {
                    "id": f"flow_{slugify(flow_title)}_{len(flows) + 1}",
                    "name": flow_title,
                    "turns": turns,
                }
            )
        turns = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        flow_match = re.match(r"^##\s+(.+)$", stripped)
        if flow_match and not re.match(r"^#{3,6}\s*turn\b", stripped, flags=re.I):
            commit_flow()
            flow_title = clean_markup(flow_match.group(1))
            mode = ""
            continue

        if re.match(r"^#{3,6}\s*turn\b", stripped, flags=re.I) or stripped.strip("-") == "":
            commit_turn()
            current = {"user_message": "", "expected_bot_response": "", "expected_buttons": []}
            mode = ""
            continue

        if re.match(r"^\*{0,4}\s*user(?:\s*:\s*user)?\s*:?\s*\*{0,4}$", stripped, flags=re.I):
            if current is None:
                current = {"user_message": "", "expected_bot_response": "", "expected_buttons": []}
            mode = "user"
            continue

        if re.match(r"^\*{0,4}\s*bot(?:\s*:\s*bot)?\s*:?\s*\*{0,4}$", stripped, flags=re.I):
            if current is None:
                current = {"user_message": "", "expected_bot_response": "", "expected_buttons": []}
            mode = "bot"
            continue

        if "action buttons" in stripped.lower():
            if current is None:
                current = {"user_message": "", "expected_bot_response": "", "expected_buttons": []}
            mode = "buttons"
            continue

        if current is None:
            continue

        value = clean_markup(stripped)
        if value.startswith(">>"):
            value = clean_markup(value[2:])
        if not value:
            continue

        if mode == "user":
            current["user_message"] = append_line(current.get("user_message", ""), value)
        elif mode == "bot":
            current["expected_bot_response"] = append_line(current.get("expected_bot_response", ""), value)
        elif mode == "buttons":
            label = clean_markup(value.lstrip("-* "))
            if label:
                current.setdefault("expected_buttons", []).append(label)

    commit_flow()

    if not flows:
        fallback_turns = parse_loose_pairs(text)
        if fallback_turns:
            flows.append({"id": "flow_chat_automation_1", "name": "Chat automation flow", "turns": fallback_turns})

    if not flows:
        raise ValueError(
            "No executable chat turns found. Add exact User/Bot blocks so Playwright knows what to type and what to expect."
        )
    return flows


def parse_loose_pairs(text: str) -> List[Dict[str, Any]]:
    matches = re.findall(r"(?:User|U)\s*:\s*(.+?)(?:\n|$)(?:Bot|B)\s*:\s*(.+?)(?=\n(?:User|U)\s*:|$)", text, flags=re.I | re.S)
    turns = []
    for user, bot in matches:
        turn = {
            "turn_number": len(turns) + 1,
            "user_message": clean_markup(user),
            "expected_bot_response": clean_markup(bot),
            "expected_buttons": [],
        }
        normalize_turn_action(turn)
        turns.append(turn)
    return turns


def clean_markup(value: str) -> str:
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\*+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def append_line(existing: str, value: str) -> str:
    return f"{existing}\n{value}".strip() if existing else value


def normalize_turn_action(turn: Dict[str, Any]) -> None:
    user_message = turn.get("user_message", "")
    click_match = re.search(r"\[click\]\s*(.+)$", user_message, flags=re.I)
    upload_match = re.search(r"\[uploads?\]\s*(.+)$", user_message, flags=re.I) or re.search(r"\[uploads?\s+([^\]]+)\]", user_message, flags=re.I)
    if click_match:
        turn["action"] = "click"
        turn["click_label"] = click_match.group(1).strip()
        turn["user_message"] = turn["click_label"]
    elif upload_match:
        turn["action"] = "upload"
        turn["upload_file"] = upload_match.group(1).strip()
    else:
        turn["action"] = "type"


def build_suite(profile: Dict[str, Any], flows: List[Dict[str, Any]]) -> Dict[str, Any]:
    cases = []
    for flow in flows:
        case_id = f"tc_chat_auto_{slugify(flow['name'])}_{len(cases) + 1}"
        scenario_type = scenario_type_for_flow(flow)
        expected = [turn.get("expected_bot_response", "") for turn in flow.get("turns", []) if turn.get("expected_bot_response")]
        cases.append(
            {
                "id": case_id,
                "name": flow["name"],
                "flow_name": flow["name"],
                "channel": "chat",
                "scenario_type": scenario_type,
                "persona": "scripted QA user",
                "priority": "high",
                "goal": f"Run scripted web-widget chat flow: {flow['name']}",
                "instructions": "Execute the uploaded Markdown conversation script through the configured chat widget.",
                "expected_outcome": " ".join(expected[:2]) or "Bot responds to each scripted user turn.",
                "test_profile": {"channel": "chat", "runner": "playwright"},
                "metric_names": ["Expected Outcome", "Response Relevance", "Context Retention", "Turn Efficiency", "Fallback Control"],
                "tags": ["chat", "playwright", "markdown_script", "browser_automation", scenario_type],
                "steps": [{"utterance": turn.get("user_message", ""), "condition": turn.get("action", "type")} for turn in flow.get("turns", [])],
                "expected_bot_behaviors": expected,
                "failure_conditions": [
                    "chat widget cannot be opened",
                    "input selector is not found",
                    "bot response does not match expected meaning",
                    "expected button or card is missing",
                ],
                "metrics": {
                    "max_turns": max(4, len(flow.get("turns", [])) * 2 + 2),
                    "max_fallbacks": 1,
                    "max_avg_latency_seconds": 8.0,
                },
                "target": {"chat_endpoint": profile.get("chat_endpoint", "")},
                "automation_flow": flow,
            }
        )
    return {
        "id": f"suite_{uuid.uuid4().hex[:10]}",
        "name": f"{profile.get('bot_name', 'Bot')} Chat Automation Script",
        "created_at": now_iso(),
        "source": "playwright_markdown",
        "bot_profile": profile,
        "coverage_matrix": {
            "flows": {flow["name"]: 1 for flow in flows},
            "channels": {"chat": len(cases)},
            "scenario_types": count_case_scenarios(cases),
            "total_cases": len(cases),
        },
        "test_cases": cases,
    }


def scenario_type_for_flow(flow: Dict[str, Any]) -> str:
    text = " ".join(
        [
            str(flow.get("name", "")),
            " ".join(str(turn.get("user_message", "")) for turn in flow.get("turns", [])),
            " ".join(str(turn.get("expected_bot_response", "")) for turn in flow.get("turns", [])),
        ]
    ).lower()
    if any(token in text for token in ["install", "installation", "new installation", "re-installation"]):
        return "installation"
    if any(token in text for token in ["unsupported order", "track my order", "order id", "order tracking"]):
        return "order_tracking"
    if any(token in text for token in ["fallback", "unclear", "blorpy"]):
        return "fallback_recovery"
    if any(token in text for token in ["unsupported", "limitation", "unavailable"]):
        return "unsupported_intent"
    if any(token in text for token in ["handoff", "human", "agent", "customer care"]):
        return "agent_handoff"
    if any(token in text for token in ["service", "not working", "repair", "warranty"]):
        return "service_support"
    if any(token in text for token in ["recommend", "looking for", "guide me", "product"]):
        return "product_discovery"
    if any(token in text for token in ["order", "track"]):
        return "order_tracking"
    if any(token in text for token in ["hi", "hello", "scope", "help me with"]):
        return "greeting_scope"
    return "custom_chat_flow"


def count_case_scenarios(cases: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for case in cases:
        scenario = str(case.get("scenario_type") or "custom_chat_flow")
        counts[scenario] = counts.get(scenario, 0) + 1
    return counts


def validate_config(config: Dict[str, Any]) -> None:
    if not config.get("url"):
        raise ValueError("Chat widget URL is required for real chat automation.")
    if not config.get("input_selector"):
        raise ValueError("Chat input selector is required for real chat automation.")
    if not config.get("message_selector"):
        raise ValueError("Chat message selector is required for real chat automation.")


def run_chat_automation(
    profile: Dict[str, Any],
    script: str,
    setting_value: Callable[[str, str], str],
    root: Path,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    config = default_config(profile)
    for key, value in options.items():
        if value not in [None, ""]:
            config[key] = value
    validate_config(config)

    flows = parse_markdown_script(script)
    suite = build_suite(profile, flows)
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    report_id = f"report_{uuid.uuid4().hex[:10]}"
    artifact_dir = root / "data" / "chat_automation"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    browser_results = execute_flows(flows, config, artifact_dir, run_id)
    case_results = []
    for case, result in zip(suite["test_cases"], browser_results):
        evaluation = evaluate_flow(case["automation_flow"], result, setting_value)
        case_results.append(
            {
                "case_id": case["id"],
                "flow_name": case["flow_name"],
                "channel": "chat",
                "scenario_type": case["scenario_type"],
                "persona": case["persona"],
                "goal": case["goal"],
                "instructions": case["instructions"],
                "expected_outcome": case["expected_outcome"],
                "test_profile": case["test_profile"],
                "metric_names": case["metric_names"],
                "tags": case["tags"],
                "yellow_ai": {
                    "module": "Chat execution",
                    "module_key": "chat_execution",
                    "failure_lens": ["widget selector", "response match", "button/card rendering"],
                },
                "result": result,
                "score": evaluation["score"],
                "turn_evaluations": evaluation["turn_evaluations"],
                "recommendations": recommendations_for_result(case, result, evaluation),
            }
        )

    avg_score = round(sum(item["score"]["overall_score"] for item in case_results) / max(1, len(case_results)), 3)
    status_counts: Dict[str, int] = {}
    for item in case_results:
        status = item["score"]["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    report = {
        "id": report_id,
        "run_id": run_id,
        "suite_id": suite["id"],
        "created_at": now_iso(),
        "summary": {
            "average_score": avg_score,
            "total_cases": len(case_results),
            "status_counts": status_counts,
            "channels": {"chat": len(case_results)},
            "adapters": adapter_summary(case_results),
            "yellow_ai_modules": {"Chat execution": len(case_results)},
            "automation": {
                "url": config["url"],
                "input_selector": config["input_selector"],
                "message_selector": config["message_selector"],
                "headless": config["headless"],
            },
        },
        "case_results": case_results,
        "yellow_ai_recommendations": flatten_recommendations(case_results),
    }
    run = {
        "id": run_id,
        "suite_id": suite["id"],
        "report_id": report_id,
        "created_at": now_iso(),
        "channel_filter": "chat",
        "average_score": avg_score,
        "total_cases": len(case_results),
        "status": "completed",
        "adapter": "playwright_web_widget",
    }
    return {"suite": suite, "run": run, "report": report, "flows": flows}


def run_goal_chat_automation(
    profile: Dict[str, Any],
    goal: str,
    setting_value: Callable[[str, str], str],
    root: Path,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    config = default_config(profile)
    for key, value in options.items():
        if value not in [None, ""] and key not in {"goal", "constraints", "test_data", "success_criteria", "max_turns"}:
            config[key] = value
    validate_config(config)

    goal_spec = normalize_goal_spec(goal, options, profile)
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    report_id = f"report_{uuid.uuid4().hex[:10]}"
    artifact_dir = root / "data" / "chat_automation"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    result = execute_goal_flow(goal_spec, config, setting_value, artifact_dir, run_id)
    flow = goal_result_to_flow(goal_spec, result)
    suite = build_suite(profile, [flow])
    suite["name"] = f"{profile.get('bot_name', 'Bot')} Goal-Driven Chat Test"
    suite["source"] = "goal_driven_playwright"
    suite["automation_mode"] = "goal_driven"

    case = suite["test_cases"][0]
    evaluation = evaluate_goal_result(goal_spec, flow, result, setting_value)
    case_result = {
        "case_id": case["id"],
        "flow_name": case["flow_name"],
        "channel": "chat",
        "scenario_type": case["scenario_type"],
        "persona": "adaptive QA user",
        "goal": goal_spec["goal"],
        "instructions": goal_spec["constraints"],
        "expected_outcome": goal_spec["success_criteria"],
        "test_profile": {"channel": "chat", "runner": "goal_driven_playwright", "max_turns": str(goal_spec["max_turns"])},
        "metric_names": ["Goal Completion", "Conversation Continuity", "Fallback Control", "Turn Efficiency"],
        "tags": ["chat", "playwright", "goal_driven", scenario_type_for_flow(flow)],
        "yellow_ai": {
            "module": "Chat execution",
            "module_key": "chat_execution",
            "failure_lens": ["goal completion", "routing", "context retention", "fallback behavior"],
        },
        "result": result,
        "score": evaluation["score"],
        "turn_evaluations": evaluation["turn_evaluations"],
        "recommendations": recommendations_for_result(case, result, evaluation),
    }
    avg_score = round(float(case_result["score"].get("overall_score", 0)), 3)
    report = {
        "id": report_id,
        "run_id": run_id,
        "suite_id": suite["id"],
        "created_at": now_iso(),
        "summary": {
            "average_score": avg_score,
            "total_cases": 1,
            "status_counts": {case_result["score"].get("status", "review"): 1},
            "channels": {"chat": 1},
            "adapters": adapter_summary([case_result]),
            "yellow_ai_modules": {"Chat execution": 1},
            "automation": {
                "mode": "goal_driven",
                "url": config["url"],
                "input_selector": config["input_selector"],
                "message_selector": config["message_selector"],
                "headless": config["headless"],
                "goal": goal_spec["goal"],
            },
        },
        "case_results": [case_result],
        "yellow_ai_recommendations": flatten_recommendations([case_result]),
    }
    run = {
        "id": run_id,
        "suite_id": suite["id"],
        "report_id": report_id,
        "created_at": now_iso(),
        "channel_filter": "chat",
        "average_score": avg_score,
        "total_cases": 1,
        "status": "completed",
        "adapter": "goal_driven_playwright",
    }
    return {"suite": suite, "run": run, "report": report, "flows": [flow], "goal_spec": goal_spec}


def normalize_goal_spec(goal: str, options: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    clean_goal = clean_message_text(goal or options.get("goal") or "")
    if not clean_goal:
        clean_goal = "Explore the configured chat bot and verify one important support journey."
    return {
        "goal": clean_goal,
        "constraints": clean_message_text(str(options.get("constraints") or "")),
        "test_data": clean_message_text(str(options.get("test_data") or "")),
        "success_criteria": clean_message_text(str(options.get("success_criteria") or "")) or default_goal_success_criteria(clean_goal),
        "max_turns": max(2, min(20, safe_int(options.get("max_turns"), safe_int(profile.get("goal_max_turns"), 10)))),
    }


def default_goal_success_criteria(goal: str) -> str:
    lower = goal.lower()
    criteria = [
        "Bot stays relevant to the requested journey.",
        "Bot asks for required data one step at a time.",
        "Bot does not loop, restart, or prematurely fallback.",
    ]
    if "language" in lower or "hindi" in lower or "english" in lower:
        criteria.append("Bot does not switch language unless the user explicitly asks.")
    if "install" in lower:
        criteria.append("Bot reaches installation booking confirmation or a clear next step.")
    if "handoff" in lower or "human" in lower:
        criteria.append("Bot offers a clear human handoff path when automation cannot continue.")
    return " ".join(criteria)


def execute_goal_flow(
    goal_spec: Dict[str, Any],
    config: Dict[str, Any],
    setting_value: Callable[[str, str], str],
    artifact_dir: Path,
    run_id: str,
) -> Dict[str, Any]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return setup_error_result({"name": goal_spec["goal"]}, config, f"Python Playwright is not installed or cannot load: {exc}")

    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright, config)
            context = browser.new_context(viewport={"width": 1366, "height": 820})
            page = context.new_page()
            try:
                return execute_goal_page(page, goal_spec, config, setting_value, artifact_dir, run_id)
            except PlaywrightTimeoutError as exc:
                return setup_error_result({"name": goal_spec["goal"]}, config, f"Playwright timeout: {exc}", capture_setup_artifact(page, {"name": goal_spec["goal"]}, artifact_dir, run_id))
            except Exception as exc:
                return setup_error_result({"name": goal_spec["goal"]}, config, f"Goal-driven automation failed: {exc}", capture_setup_artifact(page, {"name": goal_spec["goal"]}, artifact_dir, run_id))
            finally:
                try:
                    page.close()
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as exc:
        return setup_error_result({"name": goal_spec["goal"]}, config, f"Browser could not start: {exc}")


def execute_goal_page(
    page: Any,
    goal_spec: Dict[str, Any],
    config: Dict[str, Any],
    setting_value: Callable[[str, str], str],
    artifact_dir: Path,
    run_id: str,
) -> Dict[str, Any]:
    timeout_ms = max(5, int(config.get("response_timeout_seconds", 40))) * 1000
    started = time.time()
    transcript: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []
    page.goto(config["url"], wait_until="domcontentloaded", timeout=timeout_ms)
    if config.get("ready_selector"):
        page.locator(config["ready_selector"]).first.wait_for(timeout=timeout_ms)
    open_launcher_if_needed(page, config, timeout_ms)
    scope = find_chat_scope(page, config)
    wait_for_chat_surface(page, scope, config, timeout_ms)
    baseline_messages = wait_for_baseline_messages(scope, config, min(timeout_ms, 8000))
    if baseline_messages:
        transcript.append(
            {
                "turn": len(transcript) + 1,
                "speaker": "bot",
                "text": baseline_messages[-1],
                "timestamp_ms": int((time.time() - started) * 1000),
                "source": "welcome",
            }
        )

    stop_reason = ""
    for turn_index in range(1, goal_spec["max_turns"] + 1):
        scope = find_chat_scope(page, config)
        visible_buttons = collect_visible_buttons_anywhere(page, scope)
        latest_bot = latest_bot_text(transcript) or (baseline_messages[-1] if baseline_messages else "")
        decision = plan_goal_turn(goal_spec, transcript, visible_buttons, setting_value)
        decisions.append(decision)
        if decision.get("action") == "stop":
            stop_reason = decision.get("reason") or "Planner stopped."
            break
        user_text = clean_message_text(decision.get("text", ""))
        if not user_text:
            stop_reason = "Planner did not return a user action."
            break
        before_messages = collect_messages(scope, config["message_selector"])
        transcript.append(
            {
                "turn": len(transcript) + 1,
                "speaker": "user",
                "text": user_text,
                "timestamp_ms": int((time.time() - started) * 1000),
                "action": decision.get("action", "type"),
                "reason": decision.get("reason", ""),
                "visible_buttons": visible_buttons,
            }
        )
        sent_at = time.time()
        turn = {
            "action": "click" if decision.get("action") == "click" else "type",
            "user_message": user_text,
            "click_label": user_text,
            "expected_bot_response": decision.get("expected_bot_response", ""),
        }
        scope = perform_turn_action(page, scope, turn, config, timeout_ms) or scope
        actual_user_text = turn.get("actual_user_message") or user_text
        transcript[-1]["text"] = actual_user_text
        transcript[-1]["action"] = turn.get("action", transcript[-1].get("action", "type"))
        if turn.get("action_note"):
            transcript[-1]["action_note"] = turn["action_note"]
        after_messages = wait_for_bot_response(scope, config, before_messages, actual_user_text)
        actual_text = extract_actual_response(before_messages, after_messages, actual_user_text, allow_fallback=True)
        transcript.append(
            {
                "turn": len(transcript) + 1,
                "speaker": "bot",
                "text": actual_text,
                "expected_text": decision.get("expected_bot_response", ""),
                "timestamp_ms": int((time.time() - started) * 1000),
                "latency_seconds": round(time.time() - sent_at, 2),
            }
        )
        if goal_terminal_failure_signal(transcript):
            stop_reason = "Terminal bot failure observed after progressing through the goal flow."
            break
        if goal_completion_signal(goal_spec, transcript):
            stop_reason = "Goal completion signal observed."
            break
        if latest_bot and clean_message_text(actual_text).lower() == clean_message_text(latest_bot).lower() and turn_index >= 3:
            stop_reason = "Repeated bot response observed; stopping to avoid a loop."
            break

    if not stop_reason:
        stop_reason = "Maximum adaptive turns reached."

    screenshot_name = f"{run_id}_{slugify(goal_spec['goal'])}.png"
    screenshot_path = artifact_dir / screenshot_name
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        screenshot_rel = str(screenshot_path.relative_to(artifact_dir.parent.parent))
    except Exception:
        screenshot_rel = ""

    return {
        "channel": "chat",
        "adapter": "goal_driven_playwright",
        "adapter_status": "executed",
        "transcript": transcript,
        "planner_decisions": decisions,
        "artifacts": {
            "chat_endpoint": config["url"],
            "screenshot_path": screenshot_rel,
            "flow_name": goal_spec["goal"],
            "stop_reason": stop_reason,
            "goal": goal_spec,
        },
    }


def collect_visible_buttons(scope: Any) -> List[str]:
    labels: List[str] = []
    try:
        locator = scope.locator("button, [role='button'], [tabindex='0']")
        count = min(locator.count(), 80)
    except Exception:
        return labels
    for index in range(count):
        candidate = locator.nth(index)
        try:
            if not candidate.is_visible(timeout=250):
                continue
        except TypeError:
            if not candidate.is_visible():
                continue
        except Exception:
            continue
        for label in element_labels(candidate):
            cleaned = clean_message_text(label)
            if cleaned and cleaned not in labels and not should_ignore_button_label(cleaned):
                labels.append(cleaned)
                break
    return labels[:20]


def collect_visible_buttons_anywhere(page: Any, scope: Any) -> List[str]:
    labels: List[str] = []
    for candidate_scope in chat_scopes(page, scope):
        if not is_chat_action_scope(page, candidate_scope):
            continue
        for label in collect_visible_buttons(candidate_scope):
            if label not in labels:
                labels.append(label)
    return labels[:24]


def is_chat_action_scope(page: Any, scope: Any) -> bool:
    main_frame = getattr(page, "main_frame", None)
    if scope is not page and scope is not main_frame:
        return True
    for frame in getattr(page, "frames", []):
        if frame is main_frame:
            continue
        try:
            if find_visible_quick_reply(frame):
                return False
        except Exception:
            continue
    return True


def should_ignore_button_label(label: str) -> bool:
    lower = label.lower()
    ignored_tokens = [
        "powered by",
        "close",
        "minimize",
        "whatsapp",
        "emoji",
        "attachment",
        "try on your website",
        "install extension",
        "get bot script",
        "copy link",
        "agentic ai bot",
        "kent ro - agentic ai bot",
        "bot button",
    ]
    return any(token in lower for token in ignored_tokens)


def latest_bot_text(transcript: List[Dict[str, Any]]) -> str:
    for turn in reversed(transcript):
        if turn.get("speaker") == "bot":
            return clean_message_text(turn.get("text", ""))
    return ""


def plan_goal_turn(
    goal_spec: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    visible_buttons: List[str],
    setting_value: Callable[[str, str], str],
) -> Dict[str, str]:
    heuristic_decision = heuristic_goal_turn(goal_spec, transcript, visible_buttons)
    if not any(turn.get("speaker") == "user" for turn in transcript):
        return heuristic_decision

    ai_decision = openai_goal_turn(goal_spec, transcript, visible_buttons, setting_value)
    if ai_decision and visible_buttons:
        ai_label = choose_semantic_button_label(ai_decision.get("text", ""), visible_buttons)
        heuristic_label = choose_semantic_button_label(heuristic_decision.get("text", ""), visible_buttons)
        if ai_label:
            ai_decision["action"] = "click"
            ai_decision["text"] = ai_label
            return ai_decision
        if heuristic_label:
            heuristic_decision["action"] = "click"
            heuristic_decision["text"] = heuristic_label
            heuristic_decision["reason"] = "Visible quick reply selected deterministically before free-text planning."
            return heuristic_decision
    if ai_decision:
        return ai_decision
    return heuristic_decision


def openai_goal_turn(
    goal_spec: Dict[str, Any],
    transcript: List[Dict[str, Any]],
    visible_buttons: List[str],
    setting_value: Callable[[str, str], str],
) -> Optional[Dict[str, str]]:
    api_key = setting_value("OPENAI_API_KEY", "")
    if not api_key:
        return None
    model = setting_value("OPENAI_MODEL", "gpt-4.1-mini")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["action", "text", "expected_bot_response", "reason"],
        "properties": {
            "action": {"type": "string", "enum": ["type", "click", "stop"]},
            "text": {"type": "string"},
            "expected_bot_response": {"type": "string"},
            "reason": {"type": "string"},
        },
    }
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are an adaptive QA tester for a live Yellow.ai web widget. "
                    "Choose exactly one next user action that moves toward the goal. "
                    "If a visible quick reply matches the intended action, use action=click and text exactly equal to that button label. "
                    "Otherwise use action=type with a concise realistic user message. "
                    "Stop only when the goal is clearly complete, blocked, looping, or unsafe. Do not coach the bot."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "goal": goal_spec,
                        "visible_buttons": visible_buttons,
                        "transcript": transcript[-12:],
                    },
                    indent=2,
                ),
            },
        ],
        "text": {"format": {"type": "json_schema", "name": "goal_chat_next_action", "strict": True, "schema": schema}},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
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
        decision = json.loads(output_text)
    except json.JSONDecodeError:
        return None
    action = decision.get("action") if decision.get("action") in {"type", "click", "stop"} else "type"
    text = clean_message_text(decision.get("text", ""))
    if action == "click" and visible_buttons:
        exact = next((label for label in visible_buttons if labels_match(text, label)), "")
        if exact:
            text = exact
    return {
        "action": action,
        "text": text,
        "expected_bot_response": clean_message_text(decision.get("expected_bot_response", "")),
        "reason": clean_message_text(decision.get("reason", "")),
    }


def heuristic_goal_turn(goal_spec: Dict[str, Any], transcript: List[Dict[str, Any]], visible_buttons: List[str]) -> Dict[str, str]:
    goal = goal_spec["goal"].lower()
    latest = latest_bot_text(transcript).lower()
    previous_users = [clean_message_text(turn.get("text", "")).lower() for turn in transcript if turn.get("speaker") == "user"]

    def button(*needles: str) -> str:
        for label in visible_buttons:
            lower = label.lower()
            if any(needle in lower for needle in needles):
                return label
        return ""

    def exact_button(value: str) -> str:
        return next((label for label in visible_buttons if labels_match(value, label)), "")

    planned_text = ""
    if not previous_users:
        if ("hindi" in goal or "language" in goal) and button("hindi"):
            planned_text = button("hindi")
        elif "english" in goal and button("english"):
            planned_text = button("english")
        elif "install" in goal:
            planned_text = button("install", "installation")
        else:
            planned_text = ""
        if not planned_text:
            planned_text = "I need help with installation." if "install" in goal else "Hi, I need support."
    elif any(token in latest for token in ["language", "english", "hindi", "bengali", "telugu", "भाषा"]):
        planned_text = button("hindi") if ("hindi" in goal or "language" in goal) else button("english") or "English"
    elif any(token in latest for token in ["how can i help", "what can i help", "kis tarah", "madad", "मदद", "सहायता"]):
        planned_text = button("install", "installation") or "mujhe installation karvana hai"
    elif any(token in latest for token in ["delivered", "delivery", "machine", "मशीन", "डिलीवर", "deliver"]):
        planned_text = exact_button("Delivered") or button("yes", "हाँ", "haan") or positive_button(visible_buttons, "delivered") or "Delivered"
    elif any(token in latest for token in ["date", "technician visit", "service visit", "today", "tomorrow", "तारीख"]):
        planned_text = exact_button("Tomorrow") or button("tomorrow") or exact_button("Today") or button("today") or "Tomorrow"
    elif any(token in latest for token in ["purchased", "where was", "source", "खरीदा", "कहाँ से"]):
        planned_text = button("amazon") or "Amazon"
    elif any(token in latest for token in ["confirm or modify", "would you like to confirm", "is everything correct", "shall i proceed", "proceed?", "sahi"]):
        planned_text = button("confirm", "correct", "yes", "sahi", "हाँ", "haan") or "Confirm"
    elif any(token in latest for token in ["order id", "order number", "ऑर्डर", "आर्डर"]):
        planned_text = "Not Available"
    elif any(token in latest for token in ["category", "कैटेगरी", "श्रेणी"]):
        planned_text = button("water purifier") or "Water Purifier"
    elif any(token in latest for token in ["product name", "product", "प्रोडक्ट", "उत्पाद"]):
        planned_text = "Kent Grand Plus"
    elif any(token in latest for token in ["pin", "pincode", "postal", "पिन"]):
        planned_text = "560102"
    elif any(token in latest for token in ["address", "flat", "floor", "apartment", "street", "locality", "पता"]):
        planned_text = "Flat 101, Test Apartments, HSR Layout, Bengaluru"
    elif any(token in latest for token in ["name", "नाम"]):
        planned_text = "Test User"
    elif any(token in latest for token in ["correct", "confirm", "sahi"]):
        planned_text = button("correct", "yes", "sahi") or "Everything is correct"
    else:
        planned_text = button("yes", "continue", "proceed") or "Please continue."

    action = "click" if any(labels_match(planned_text, label) for label in visible_buttons) else "type"
    return {
        "action": action,
        "text": planned_text,
        "expected_bot_response": "Bot should continue toward the stated goal without losing context, looping, or switching language unexpectedly.",
        "reason": "Heuristic fallback selected the next action from visible buttons and latest bot prompt.",
    }


def goal_completion_signal(goal_spec: Dict[str, Any], transcript: List[Dict[str, Any]]) -> bool:
    latest = latest_bot_text(transcript).lower()
    if not latest:
        return False
    if terminal_failure_text(latest):
        return False
    success_tokens = ["confirmed", "registered", "booked", "scheduled", "request", "success", "thank you", "धन्यवाद", "दर्ज"]
    if any(token in latest for token in success_tokens):
        return True
    if "human" in goal_spec["goal"].lower() and any(token in latest for token in ["agent", "customer care", "representative"]):
        return True
    return False


def terminal_failure_text(value: str) -> bool:
    latest = clean_message_text(value).lower()
    failure_tokens = [
        "error while creating",
        "try again after some time",
        "try again later",
        "unable to create",
        "cannot create",
        "failed",
        "sorry",
    ]
    return any(token in latest for token in failure_tokens)


def goal_terminal_failure_signal(transcript: List[Dict[str, Any]]) -> bool:
    latest = latest_bot_text(transcript)
    if not terminal_failure_text(latest):
        return False
    user_turns = [clean_message_text(turn.get("text", "")).lower() for turn in transcript if turn.get("speaker") == "user"]
    progress_tokens = [
        "confirm",
        "today",
        "tomorrow",
        "day after tomorrow",
        "haan",
        "sahi",
    ]
    return any(any(token in turn for token in progress_tokens) for turn in user_turns)


def goal_result_to_flow(goal_spec: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    turns: List[Dict[str, Any]] = []
    pending_user: Optional[Dict[str, Any]] = None
    for item in result.get("transcript", []):
        if item.get("speaker") == "user":
            pending_user = {
                "turn_number": len(turns) + 1,
                "user_message": item.get("text", ""),
                "expected_bot_response": "",
                "expected_buttons": [],
                "action": "click" if item.get("action") == "click" else "type",
            }
        elif item.get("speaker") == "bot" and pending_user:
            pending_user["expected_bot_response"] = item.get("expected_text") or "Bot should continue toward the stated goal without losing context, looping, or falling back prematurely."
            turns.append(pending_user)
            pending_user = None
    if pending_user:
        turns.append(pending_user)
    return {
        "id": f"flow_goal_{slugify(goal_spec['goal'])}_1",
        "name": goal_spec["goal"],
        "turns": turns or [
            {
                "turn_number": 1,
                "user_message": goal_spec["goal"],
                "expected_bot_response": goal_spec["success_criteria"],
                "expected_buttons": [],
                "action": "type",
            }
        ],
    }


def evaluate_goal_result(
    goal_spec: Dict[str, Any],
    flow: Dict[str, Any],
    result: Dict[str, Any],
    setting_value: Callable[[str, str], str],
) -> Dict[str, Any]:
    base = evaluate_flow(flow, result, setting_value)
    if result.get("adapter_status") != "executed":
        return base
    final_eval = openai_goal_eval(goal_spec, result, setting_value) or heuristic_goal_eval(goal_spec, result)
    base_score = float(base["score"].get("overall_score", 0))
    final_score = float(final_eval.get("score", 0))
    combined = round((base_score * 0.45) + (final_score * 0.55), 3)
    issues = list(base["score"].get("issues", []))
    if final_eval.get("issue"):
        issues.append(final_eval["issue"])
    base["score"]["overall_score"] = combined
    base["score"]["status"] = "pass" if combined >= 0.78 and not issues else "review"
    base["score"]["metrics"]["goal_completion"] = final_score
    base["score"]["issues"] = issues
    base["turn_evaluations"].append(
        {
            "passed": final_score >= 0.78,
            "score": final_score,
            "reason": final_eval.get("reason", "Goal-level evaluation completed."),
        }
    )
    return base


def openai_goal_eval(goal_spec: Dict[str, Any], result: Dict[str, Any], setting_value: Callable[[str, str], str]) -> Optional[Dict[str, Any]]:
    api_key = setting_value("OPENAI_API_KEY", "")
    if not api_key:
        return None
    model = setting_value("OPENAI_MODEL", "gpt-4.1-mini")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["passed", "score", "reason", "issue"],
        "properties": {
            "passed": {"type": "boolean"},
            "score": {"type": "number"},
            "reason": {"type": "string"},
            "issue": {"type": "string"},
        },
    }
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "Judge whether a live chatbot transcript achieved the QA goal. "
                    "Penalize wrong branch, language switch without explicit request, loops, fallback, restart, missing required data handling, and no clear next step."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"goal": goal_spec, "result": result}, indent=2),
            },
        ],
        "text": {"format": {"type": "json_schema", "name": "goal_chat_eval", "strict": True, "schema": schema}},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
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
    return {
        "passed": bool(parsed.get("passed")),
        "score": max(0.0, min(1.0, float(parsed.get("score", 0)))),
        "reason": clean_message_text(parsed.get("reason", "")),
        "issue": clean_message_text(parsed.get("issue", "")),
    }


def heuristic_goal_eval(goal_spec: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    transcript_text = " ".join(turn.get("text", "") for turn in result.get("transcript", [])).lower()
    issues = []
    terminal_failure = goal_terminal_failure_signal(result.get("transcript", []))
    if result.get("artifacts", {}).get("stop_reason", "").lower().startswith("repeated"):
        issues.append("Possible loop detected.")
    if terminal_failure:
        issues.append("Bot returned a terminal failure after the booking details were collected.")
    elif any(token in transcript_text for token in ["sorry", "cannot help", "try again later", "unable"]):
        issues.append("Bot produced a fallback or failure-style response.")
    if "language" in goal_spec["goal"].lower() and "continue in english" in transcript_text and "hindi" in goal_spec["goal"].lower():
        issues.append("Possible unexpected language switch.")
    if terminal_failure:
        score = 0.42
    elif goal_completion_signal(goal_spec, result.get("transcript", [])):
        score = 0.85 if issues else 1.0
    else:
        score = 0.55 if not issues else 0.35
        issues.append("No clear goal completion signal was observed.")
    return {
        "passed": score >= 0.78,
        "score": score,
        "reason": "Heuristic goal evaluation completed.",
        "issue": " ".join(dict.fromkeys(issues)),
    }


def execute_flows(flows: List[Dict[str, Any]], config: Dict[str, Any], artifact_dir: Path, run_id: str) -> List[Dict[str, Any]]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return [setup_error_result(flow, config, f"Python Playwright is not installed or cannot load: {exc}") for flow in flows]

    results = []
    try:
        with sync_playwright() as playwright:
            browser = launch_browser(playwright, config)
            for flow in flows:
                context = browser.new_context(viewport={"width": 1366, "height": 820})
                page = context.new_page()
                try:
                    results.append(execute_flow(page, flow, config, artifact_dir, run_id))
                except PlaywrightTimeoutError as exc:
                    results.append(setup_error_result(flow, config, f"Playwright timeout: {exc}", capture_setup_artifact(page, flow, artifact_dir, run_id)))
                except Exception as exc:
                    results.append(setup_error_result(flow, config, f"Automation failed: {exc}", capture_setup_artifact(page, flow, artifact_dir, run_id)))
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
                    try:
                        context.close()
                    except Exception:
                        pass
            browser.close()
    except Exception as exc:
        return [setup_error_result(flow, config, f"Browser could not start: {exc}") for flow in flows]
    return results


def launch_browser(playwright: Any, config: Dict[str, Any]) -> Any:
    headless = bool(config.get("headless", True))
    errors = []
    for kwargs in [{"channel": "chrome", "headless": headless}, {"headless": headless}]:
        try:
            return playwright.chromium.launch(**kwargs)
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(" ; ".join(errors[-2:]))


def execute_flow(page: Any, flow: Dict[str, Any], config: Dict[str, Any], artifact_dir: Path, run_id: str) -> Dict[str, Any]:
    timeout_ms = max(5, int(config.get("response_timeout_seconds", 40))) * 1000
    started = time.time()
    transcript: List[Dict[str, Any]] = []
    page.goto(config["url"], wait_until="domcontentloaded", timeout=timeout_ms)
    if config.get("ready_selector"):
        page.locator(config["ready_selector"]).first.wait_for(timeout=timeout_ms)
    open_launcher_if_needed(page, config, timeout_ms)
    scope = find_chat_scope(page, config)
    wait_for_chat_surface(page, scope, config, timeout_ms)
    wait_for_baseline_messages(scope, config, min(timeout_ms, 8000))

    for index, turn in enumerate(flow.get("turns", []), start=1):
        scope = find_chat_scope(page, config)
        before_messages = collect_messages(scope, config["message_selector"])
        user_text = turn.get("user_message", "")
        transcript.append(
            {
                "turn": len(transcript) + 1,
                "speaker": "user",
                "text": user_text,
                "timestamp_ms": int((time.time() - started) * 1000),
                "action": turn.get("action", "type"),
            }
        )
        sent_at = time.time()
        scope = perform_turn_action(page, scope, turn, config, timeout_ms) or scope
        after_messages = wait_for_bot_response(scope, config, before_messages, user_text)
        actual_text = extract_actual_response(before_messages, after_messages, user_text, allow_fallback=True)
        transcript.append(
            {
                "turn": len(transcript) + 1,
                "speaker": "bot",
                "text": actual_text,
                "expected_text": turn.get("expected_bot_response", ""),
                "expected_buttons": turn.get("expected_buttons", []),
                "timestamp_ms": int((time.time() - started) * 1000),
                "latency_seconds": round(time.time() - sent_at, 2),
            }
        )

    screenshot_name = f"{run_id}_{slugify(flow['name'])}.png"
    screenshot_path = artifact_dir / screenshot_name
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        screenshot_rel = str(screenshot_path.relative_to(artifact_dir.parent.parent))
    except Exception:
        screenshot_rel = ""

    return {
        "channel": "chat",
        "adapter": "playwright_web_widget",
        "adapter_status": "executed",
        "transcript": transcript,
        "artifacts": {
            "chat_endpoint": config["url"],
            "screenshot_path": screenshot_rel,
            "flow_name": flow["name"],
        },
    }


def open_launcher_if_needed(page: Any, config: Dict[str, Any], timeout_ms: int) -> None:
    if any_frame_has_chat_surface(page, config):
        return
    try:
        if click_launcher_locator(page, page.locator("#ymDivBar"), config, min(timeout_ms, 15000)):
            return
    except Exception:
        pass
    launcher_selectors = launcher_candidate_selectors(config)
    for scope in chat_scopes(page):
        for launcher_selector in launcher_selectors:
            try:
                if click_launcher_locator(page, scope.locator(launcher_selector), config, min(timeout_ms, 15000)):
                    return
            except Exception:
                continue
        if click_likely_widget_launcher(page, scope, config, min(timeout_ms, 15000)):
            return


def launcher_candidate_selectors(config: Dict[str, Any]) -> List[str]:
    selectors = [str(config.get("launcher_selector") or "").strip()]
    selectors.extend(
        [
            "#ymDivBar",
            "[id*='ymDivBar']",
            "button[aria-label*='bot' i]",
            "button[title*='bot' i]",
            "button:has-text('Agentic AI bot')",
            "button:has-text('Kent RO')",
        ]
    )
    unique: List[str] = []
    for selector in selectors:
        if selector and selector not in unique:
            unique.append(selector)
    return unique


def any_frame_has_visible_input(page: Any, config: Dict[str, Any]) -> bool:
    for frame in page.frames:
        try:
            if find_visible_input(frame, config):
                return True
        except Exception:
            continue
    return False


def any_frame_has_chat_surface(page: Any, config: Dict[str, Any]) -> bool:
    message_selector = str(config.get("message_selector") or "").strip()
    main_frame = getattr(page, "main_frame", None)
    for frame in getattr(page, "frames", []):
        try:
            if find_visible_input(frame, config):
                return True
            if message_selector and collect_messages(frame, message_selector):
                return True
            if frame is not main_frame and find_visible_quick_reply(frame):
                return True
        except Exception:
            continue
    return False


def find_chat_scope(page: Any, config: Dict[str, Any]) -> Any:
    frame_hint = str(config.get("frame_hint") or "").lower()
    input_selector = config["input_selector"]
    message_selector = str(config.get("message_selector") or "").strip()
    frames = page.frames
    if frame_hint:
        for frame in frames:
            if frame_hint in (frame.url or "").lower() or frame_hint in (frame.name or "").lower():
                try:
                    if (
                        find_visible_input(frame, config)
                        or frame.locator(input_selector).count() > 0
                        or (message_selector and frame.locator(message_selector).count() > 0)
                    ):
                        return frame
                except Exception:
                    continue
    for frame in frames:
        try:
            if find_visible_input(frame, config):
                return frame
        except Exception:
            continue
    if message_selector:
        for frame in frames:
            try:
                if frame.locator(message_selector).count() > 0:
                    return frame
            except Exception:
                continue
    for frame in frames:
        try:
            if frame.locator(input_selector).count() > 0:
                return frame
        except Exception:
            continue
    return page


def chat_scopes(page: Any, preferred_scope: Optional[Any] = None) -> List[Any]:
    scopes = []
    seen = set()

    def add(scope: Any) -> None:
        key = id(scope)
        if key not in seen:
            scopes.append(scope)
            seen.add(key)

    if preferred_scope is not None:
        add(preferred_scope)
    for frame in getattr(page, "frames", []):
        add(frame)
    add(page)
    return scopes


def input_candidate_selectors(config: Dict[str, Any]) -> List[str]:
    selectors = [str(config.get("input_selector") or "").strip()]
    selectors.extend(
        [
            "textarea",
            "input[type='text']",
            "input:not([type])",
            "[contenteditable='true']",
            "[role='textbox']",
            "textarea[placeholder*='message' i]",
            "input[placeholder*='message' i]",
            "textarea[placeholder*='type' i]",
            "input[placeholder*='type' i]",
        ]
    )
    unique: List[str] = []
    for selector in selectors:
        if selector and selector not in unique:
            unique.append(selector)
    return unique


def wait_for_chat_surface(page: Any, scope: Any, config: Dict[str, Any], timeout_ms: int) -> Any:
    deadline = time.time() + max(5, min(timeout_ms / 1000, 15))
    while time.time() < deadline:
        for candidate_scope in chat_scopes(page, scope):
            if find_visible_input(candidate_scope, config):
                return candidate_scope
            if collect_messages(candidate_scope, config["message_selector"]):
                return candidate_scope
            if candidate_scope is not page and find_visible_quick_reply(candidate_scope):
                return candidate_scope
        open_launcher_if_needed(page, config, timeout_ms)
        pause_scope(scope, 500)
    return scope


def wait_for_chat_input(page: Any, scope: Any, config: Dict[str, Any], timeout_ms: int) -> Any:
    deadline = time.time() + max(5, timeout_ms / 1000)
    checked = ", ".join(input_candidate_selectors(config)[:5])
    while time.time() < deadline:
        visible = find_visible_input(scope, config)
        if visible:
            return visible
        open_launcher_if_needed(page, config, timeout_ms)
        pause_scope(scope, 500)
    raise RuntimeError(
        f"No visible chat input found. Checked selectors: {checked}. "
        "If the current bot step shows quick-reply buttons, make the User value exactly match one visible option."
    )


def find_visible_input(scope: Any, config: Dict[str, Any]) -> Any:
    for selector in input_candidate_selectors(config):
        locator = visible_locator(scope, selector)
        if locator:
            return locator
    return None


def visible_locator(scope: Any, selector: str) -> Any:
    try:
        locator = scope.locator(selector)
        count = min(locator.count(), 40)
    except Exception:
        return None
    for index in range(count - 1, -1, -1):
        candidate = locator.nth(index)
        try:
            visible = candidate.is_visible(timeout=400)
        except TypeError:
            visible = candidate.is_visible()
        except Exception:
            continue
        if not visible:
            continue
        try:
            enabled = candidate.is_enabled(timeout=400)
        except TypeError:
            enabled = candidate.is_enabled()
        except Exception:
            enabled = True
        if enabled:
            return candidate
    return None


def find_visible_quick_reply(scope: Any) -> Any:
    for selector in ["button", "[role='button']", "[tabindex='0']"]:
        locator = visible_locator(scope, selector)
        if locator:
            return locator
    return None


def click_last_visible(locator: Any, timeout_ms: int) -> bool:
    try:
        count = min(locator.count(), 80)
    except Exception:
        return False
    for index in range(count - 1, -1, -1):
        candidate = locator.nth(index)
        try:
            visible = candidate.is_visible(timeout=400)
        except TypeError:
            visible = candidate.is_visible()
        except Exception:
            continue
        if not visible:
            continue
        try:
            enabled = candidate.is_enabled(timeout=400)
        except TypeError:
            enabled = candidate.is_enabled()
        except Exception:
            enabled = True
        if not enabled:
            continue
        try:
            candidate.click(timeout=min(timeout_ms, 10000))
            return True
        except Exception:
            continue
    return False


def click_locator_center(page: Any, locator: Any, timeout_ms: int) -> bool:
    try:
        locator.scroll_into_view_if_needed(timeout=min(timeout_ms, 3000))
    except Exception:
        pass
    try:
        box = locator.bounding_box(timeout=min(timeout_ms, 3000))
    except TypeError:
        try:
            box = locator.bounding_box()
        except Exception:
            box = None
    except Exception:
        box = None
    if not box:
        return False
    try:
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        return True
    except Exception:
        return False


def click_launcher_locator(page: Any, locator: Any, config: Dict[str, Any], timeout_ms: int) -> bool:
    try:
        count = min(locator.count(), 80)
    except Exception:
        return False
    for index in range(count - 1, -1, -1):
        candidate = locator.nth(index)
        try:
            visible = candidate.is_visible(timeout=400)
        except TypeError:
            visible = candidate.is_visible()
        except Exception:
            continue
        if not visible:
            continue
        try:
            enabled = candidate.is_enabled(timeout=400)
        except TypeError:
            enabled = candidate.is_enabled()
        except Exception:
            enabled = True
        if not enabled:
            continue
        for click_mode in ["center", "locator"]:
            try:
                if click_mode == "locator":
                    candidate.click(timeout=min(timeout_ms, 10000))
                else:
                    if not click_locator_center(page, candidate, timeout_ms):
                        continue
                if wait_for_any_chat_surface(page, config, min(timeout_ms, 10000)):
                    return True
            except Exception:
                continue
    return False


def click_likely_widget_launcher(page: Any, scope: Any, config: Dict[str, Any], timeout_ms: int) -> bool:
    try:
        locator = scope.locator("button")
        count = min(locator.count(), 80)
    except Exception:
        return False
    for index in range(count - 1, -1, -1):
        candidate = locator.nth(index)
        labels = element_labels(candidate)
        joined = " ".join(labels).lower()
        if not joined:
            continue
        if any(skip in joined for skip in ["whatsapp", "get bot script", "copy link", "install extension"]):
            continue
        if not any(token in joined for token in ["bot", "chat", "assistant", "agentic ai", "kent ro"]):
            continue
        try:
            if click_launcher_locator(page, candidate, config, timeout_ms):
                return True
        except Exception:
            continue
        try:
            if click_locator_center(page, candidate, timeout_ms):
                if wait_for_any_chat_surface(page, config, min(timeout_ms, 10000)):
                    return True
        except Exception:
            continue
    return False


def wait_for_any_chat_surface(page: Any, config: Dict[str, Any], timeout_ms: int) -> bool:
    deadline = time.time() + max(1.0, timeout_ms / 1000)
    while time.time() < deadline:
        if any_frame_has_chat_surface(page, config):
            return True
        try:
            page.wait_for_timeout(500)
        except Exception:
            time.sleep(0.5)
    return any_frame_has_chat_surface(page, config)


def element_labels(locator: Any) -> List[str]:
    labels = []
    for attr in ["aria-label", "title", "value"]:
        try:
            value = locator.get_attribute(attr, timeout=300)
        except TypeError:
            value = locator.get_attribute(attr)
        except Exception:
            value = ""
        if value:
            labels.append(clean_message_text(value))
    try:
        text = locator.inner_text(timeout=300)
    except Exception:
        text = ""
    if text:
        labels.append(clean_message_text(text))
    return [label for label in labels if label]


def label_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_message_text(value).lower()).strip()


def labels_match(expected: str, actual: str) -> bool:
    expected_clean = clean_message_text(expected).lower()
    actual_clean = clean_message_text(actual).lower()
    if expected_clean and expected_clean == actual_clean:
        return True
    expected_key = label_key(expected)
    actual_key = label_key(actual)
    return bool(expected_key and actual_key and expected_key == actual_key)


def choose_semantic_button_label(desired: str, visible_buttons: List[str]) -> str:
    clean_desired = clean_message_text(desired)
    desired_lower = clean_desired.lower()
    desired_key = label_key(clean_desired)
    desired_negative = is_negative_reply(clean_desired)
    if not clean_desired or not visible_buttons:
        return ""
    for label in visible_buttons:
        if labels_match(clean_desired, label):
            return label
    for label in visible_buttons:
        key = label_key(label)
        if key and desired_key and (key in desired_key or desired_key in key):
            return label

    semantic_groups = [
        (["hindi", "हिंदी", "हिन्दी"], ["hindi", "हिंदी", "हिन्दी"]),
        (["english"], ["english"]),
        (["bengali", "বাংলা"], ["bengali", "বাংলা"]),
        (["telugu", "తెలుగు"], ["telugu", "తెలుగు"]),
        (["install", "installation", "machine delivered"], ["install", "installation"]),
        (["delivered", "delivery done", "yes delivered"], ["delivered", "yes", "हाँ", "haan", "ha"]),
        (["not delivered", "not yet"], ["not delivered", "no", "नहीं", "nahi"]),
        (["amazon"], ["amazon"]),
        (["flipkart"], ["flipkart"]),
        (["not available", "no order", "do not have"], ["not available", "not avail", "skip"]),
        (["water purifier", "purifier"], ["water purifier", "purifier"]),
        (["air purifier"], ["air purifier"]),
        (["softener"], ["softener"]),
        (["correct", "confirm", "everything is correct", "sahi", "सब सही"], ["confirm", "correct", "yes", "sahi", "सही", "हाँ", "haan"]),
        (["continue", "proceed", "next"], ["continue", "proceed", "next", "confirm", "yes"]),
    ]
    for desired_needles, label_needles in semantic_groups:
        if not any(needle in desired_lower for needle in desired_needles):
            continue
        for label in visible_buttons:
            label_lower = label.lower()
            if is_negative_reply(label) and not desired_negative:
                continue
            if any(needle in label_lower for needle in label_needles):
                return label

    if len(visible_buttons) == 1:
        return visible_buttons[0]
    return ""


def is_negative_reply(value: str) -> bool:
    lower = clean_message_text(value).lower()
    return any(token in lower for token in ["not ", "not-", "not_", "no ", "no-", "no_", "nahi", "nahin", "नहीं"])


def positive_button(visible_buttons: List[str], *needles: str) -> str:
    for label in visible_buttons:
        if is_negative_reply(label):
            continue
        lower = label.lower()
        if any(needle in lower for needle in needles):
            return label
    return ""


def choose_visible_quick_reply(page: Any, scope: Any, desired: str) -> str:
    return choose_semantic_button_label(desired, collect_visible_buttons_anywhere(page, scope))


def click_matching_button(scope: Any, text: str, timeout_ms: int) -> bool:
    try:
        locator = scope.locator("button, [role='button'], [tabindex='0']")
        count = min(locator.count(), 120)
    except Exception:
        return False
    for index in range(count - 1, -1, -1):
        candidate = locator.nth(index)
        labels = element_labels(candidate)
        if not any(labels_match(text, label) for label in labels):
            continue
        try:
            visible = candidate.is_visible(timeout=400)
        except TypeError:
            visible = candidate.is_visible()
        except Exception:
            continue
        if not visible:
            continue
        try:
            enabled = candidate.is_enabled(timeout=400)
        except TypeError:
            enabled = candidate.is_enabled()
        except Exception:
            enabled = True
        if not enabled:
            continue
        try:
            candidate.click(timeout=min(timeout_ms, 10000))
            return True
        except Exception:
            continue
    return False


def click_visible_text(scope: Any, text: str, timeout_ms: int) -> bool:
    label = clean_message_text(text)
    if not label or should_ignore_button_label(label):
        return False
    locator_builders = [
        lambda: scope.get_by_role("button", name=label, exact=True),
        lambda: scope.locator(f"button:has-text({json.dumps(label)})"),
        lambda: scope.locator(f"[role='button']:has-text({json.dumps(label)})"),
    ]
    for build_locator in locator_builders:
        try:
            if click_last_visible(build_locator(), timeout_ms):
                return True
        except Exception:
            continue
    return click_matching_button(scope, label, timeout_ms)


def wait_and_click_visible_text(page: Any, scope: Any, text: str, config: Dict[str, Any], timeout_ms: int) -> Any:
    deadline = time.time() + max(1.5, min(timeout_ms / 1000, 8))
    while time.time() < deadline:
        for candidate_scope in chat_scopes(page, scope):
            if not is_chat_action_scope(page, candidate_scope):
                continue
            if click_visible_text(candidate_scope, text, timeout_ms):
                return candidate_scope
        open_launcher_if_needed(page, config, timeout_ms)
        pause_scope(scope, 300)
    return None


def pause_scope(scope: Any, ms: int) -> None:
    try:
        scope.page.wait_for_timeout(ms)
        return
    except Exception:
        pass
    try:
        scope.wait_for_timeout(ms)
        return
    except Exception:
        time.sleep(ms / 1000)


def collect_messages(scope: Any, selector: str) -> List[str]:
    try:
        locator = scope.locator(selector)
        count = min(locator.count(), 200)
    except Exception:
        return []
    messages = []
    for index in range(count):
        try:
            text = clean_message_text(locator.nth(index).inner_text(timeout=1000))
            if text:
                messages.append(text)
        except Exception:
            continue
    return messages


def wait_for_baseline_messages(scope: Any, config: Dict[str, Any], timeout_ms: int) -> List[str]:
    deadline = time.time() + max(1.0, timeout_ms / 1000)
    latest: List[str] = []
    while time.time() < deadline:
        latest = collect_messages(scope, config["message_selector"])
        if latest:
            return latest
        pause_scope(scope, 300)
    return latest


def perform_turn_action(page: Any, scope: Any, turn: Dict[str, Any], config: Dict[str, Any], timeout_ms: int) -> Any:
    action = turn.get("action", "type")
    if action == "click":
        label = turn.get("click_label") or turn.get("user_message", "")
        clicked_scope = wait_and_click_visible_text(page, scope, label, config, timeout_ms)
        if clicked_scope:
            turn["actual_user_message"] = clean_message_text(label)
            return clicked_scope
        fallback_label = choose_visible_quick_reply(page, scope, label)
        if fallback_label and fallback_label != label:
            clicked_scope = wait_and_click_visible_text(page, scope, fallback_label, config, timeout_ms)
            if clicked_scope:
                turn["actual_user_message"] = fallback_label
                turn["action_note"] = f"Clicked closest visible quick reply for requested action: {label}"
                return clicked_scope
        visible = collect_visible_buttons_anywhere(page, scope)
        visible_hint = f" Visible options: {', '.join(visible[:8])}." if visible else ""
        raise RuntimeError(f"No visible quick-reply or button found for '{label}'.{visible_hint}")
    if action == "upload":
        upload_file = turn.get("upload_file", "")
        if not upload_file:
            raise ValueError("Upload turn is missing a file name.")
        scope.locator("input[type='file']").last.set_input_files(upload_file)
        return scope
    user_message = turn.get("user_message", "")
    clicked_scope = wait_and_click_visible_text(page, scope, user_message, config, min(timeout_ms, 8000))
    if clicked_scope:
        turn["actual_user_message"] = clean_message_text(user_message)
        turn["action"] = "click"
        return clicked_scope
    fallback_label = choose_visible_quick_reply(page, scope, user_message)
    if fallback_label:
        clicked_scope = wait_and_click_visible_text(page, scope, fallback_label, config, timeout_ms)
        if clicked_scope:
            turn["actual_user_message"] = fallback_label
            turn["action"] = "click"
            turn["action_note"] = f"Clicked visible quick reply because no text input was available for: {user_message}"
            return clicked_scope
    for candidate_scope in chat_scopes(page, scope):
        input_box = find_visible_input(candidate_scope, config)
        if input_box:
            input_box.fill(user_message, timeout=timeout_ms)
            if config.get("send_selector"):
                candidate_scope.locator(config["send_selector"]).last.click(timeout=timeout_ms)
            else:
                input_box.press("Enter", timeout=timeout_ms)
            return candidate_scope
    fallback_label = choose_visible_quick_reply(page, scope, user_message)
    if fallback_label:
        clicked_scope = wait_and_click_visible_text(page, scope, fallback_label, config, timeout_ms)
        if clicked_scope:
            turn["actual_user_message"] = fallback_label
            turn["action"] = "click"
            turn["action_note"] = f"Clicked visible quick reply because no text input appeared for: {user_message}"
            return clicked_scope
    input_box = wait_for_visible_input(scope, config, timeout_ms)
    input_box.fill(user_message, timeout=timeout_ms)
    if config.get("send_selector"):
        scope.locator(config["send_selector"]).last.click(timeout=timeout_ms)
    else:
        input_box.press("Enter", timeout=timeout_ms)
    return scope


def wait_for_visible_input(scope: Any, config: Dict[str, Any], timeout_ms: int) -> Any:
    deadline = time.time() + max(5, timeout_ms / 1000)
    checked = ", ".join(input_candidate_selectors(config))
    while time.time() < deadline:
        visible = find_visible_input(scope, config)
        if visible:
            return visible
        pause_scope(scope, 400)
    raise RuntimeError(
        f"No visible chat input found. Checked selectors: {checked}. "
        "If this bot step uses quick-reply buttons, use a User value that exactly matches the button text."
    )


def wait_for_bot_response(scope: Any, config: Dict[str, Any], before_messages: List[str], user_text: str) -> List[str]:
    deadline = time.time() + max(5, int(config.get("response_timeout_seconds", 40)))
    stable_seconds = max(0.5, float(config.get("stability_seconds", 2.0)))
    last_combined = ""
    stable_since: Optional[float] = None
    latest = before_messages

    while time.time() < deadline:
        current = collect_messages(scope, config["message_selector"])
        if current:
            latest = current
        actual = extract_actual_response(before_messages, current, user_text, allow_fallback=False)
        combined = actual.strip()
        if combined and combined != last_combined:
            last_combined = combined
            stable_since = time.time()
        elif combined and stable_since and time.time() - stable_since >= stable_seconds:
            return current
        try:
            scope.page.wait_for_timeout(450)
        except Exception:
            time.sleep(0.45)
    return latest


def extract_actual_response(before_messages: List[str], after_messages: List[str], user_text: str, allow_fallback: bool = True) -> str:
    before_count = len(before_messages)
    user_clean = clean_message_text(user_text).lower()
    candidates = after_messages[before_count:] if len(after_messages) > before_count else []
    user_index = -1
    for index, item in enumerate(candidates):
        if clean_message_text(item).lower() == user_clean:
            user_index = index
    if user_index >= 0:
        candidates = candidates[user_index + 1 :]
    filtered = []
    for item in candidates:
        cleaned = clean_message_text(item)
        if cleaned and cleaned.lower() != user_clean:
            filtered.append(cleaned)
    if filtered:
        return filtered[-1]
    if not allow_fallback:
        return ""
    for item in reversed(after_messages):
        cleaned = clean_message_text(item)
        if cleaned and cleaned.lower() != user_clean:
            return cleaned
    return ""


def clean_message_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "")
    return value.strip()


def capture_setup_artifact(page: Any, flow: Dict[str, Any], artifact_dir: Path, run_id: str) -> Dict[str, str]:
    screenshot_rel = ""
    try:
        screenshot_path = artifact_dir / f"{run_id}_{slugify(flow.get('name', 'flow'))}_setup_error.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        screenshot_rel = str(screenshot_path.relative_to(artifact_dir.parent.parent))
    except Exception:
        pass
    return {"screenshot_path": screenshot_rel} if screenshot_rel else {}


def setup_error_result(flow: Dict[str, Any], config: Dict[str, Any], message: str, extra_artifacts: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    artifacts = {
        "chat_endpoint": config.get("url", ""),
        "flow_name": flow.get("name", ""),
        "error": message,
    }
    if extra_artifacts:
        artifacts.update(extra_artifacts)
    return {
        "channel": "chat",
        "adapter": "playwright_web_widget",
        "adapter_status": "setup_error",
        "transcript": [
            {
                "turn": 1,
                "speaker": "system",
                "text": message,
                "timestamp_ms": 0,
            }
        ],
        "artifacts": artifacts,
    }


def evaluate_flow(flow: Dict[str, Any], result: Dict[str, Any], setting_value: Callable[[str, str], str]) -> Dict[str, Any]:
    if result.get("adapter_status") != "executed":
        message = result.get("artifacts", {}).get("error") or "Automation did not execute."
        return {
            "score": {
                "overall_score": 0.0,
                "status": "setup_error",
                "metrics": {"execution": 0.0, "response_match": 0.0, "turn_completion": 0.0},
                "observed": {"turn_count": len(result.get("transcript", [])), "avg_latency_seconds": 0},
                "issues": [message],
            },
            "turn_evaluations": [],
        }

    bot_turns = [turn for turn in result.get("transcript", []) if turn.get("speaker") == "bot"]
    evaluations = []
    for turn, bot_turn in zip(flow.get("turns", []), bot_turns):
        evaluations.append(evaluate_turn(turn.get("expected_bot_response", ""), bot_turn.get("text", ""), setting_value))
    if not evaluations:
        evaluations.append({"passed": False, "score": 0.0, "reason": "No bot responses captured."})

    avg_score = round(sum(float(item.get("score", 0)) for item in evaluations) / len(evaluations), 3)
    latency_values = [turn.get("latency_seconds", 0) for turn in bot_turns if turn.get("latency_seconds") is not None]
    avg_latency = round(sum(latency_values) / max(1, len(latency_values)), 2)
    issues = [item.get("reason", "Response mismatch") for item in evaluations if not item.get("passed")]
    if len(bot_turns) < len(flow.get("turns", [])):
        issues.append("Fewer bot responses were captured than scripted turns.")
    all_turns_passed = all(bool(item.get("passed")) for item in evaluations)
    return {
        "score": {
            "overall_score": avg_score,
            "status": "pass" if all_turns_passed and not issues else "review",
            "metrics": {
                "execution": 1.0,
                "response_match": avg_score,
                "turn_completion": min(1.0, len(bot_turns) / max(1, len(flow.get("turns", [])))),
            },
            "observed": {
                "turn_count": len(result.get("transcript", [])),
                "avg_latency_seconds": avg_latency,
            },
            "issues": issues,
        },
        "turn_evaluations": evaluations,
    }


def evaluate_turn(expected: str, actual: str, setting_value: Callable[[str, str], str]) -> Dict[str, Any]:
    expected = clean_message_text(expected)
    actual = clean_message_text(actual)
    if not expected:
        return {"passed": bool(actual), "score": 1.0 if actual else 0.0, "reason": "No expected text was provided."}
    if not actual:
        return {"passed": False, "score": 0.0, "reason": "No bot response was captured."}
    if expected.lower().startswith("bot should continue toward the stated goal"):
        if terminal_failure_text(actual):
            return {"passed": False, "score": 0.35, "reason": "Bot returned a terminal failure message."}
        return {"passed": True, "score": 0.85, "reason": "Bot responded; goal-level evaluator judges the final journey outcome."}
    ai_result = openai_semantic_eval(expected, actual, setting_value)
    if ai_result:
        return ai_result
    return keyword_eval(expected, actual)


def openai_semantic_eval(expected: str, actual: str, setting_value: Callable[[str, str], str]) -> Optional[Dict[str, Any]]:
    api_key = setting_value("OPENAI_API_KEY", "")
    if not api_key:
        return None
    model = setting_value("OPENAI_MODEL", "gpt-4.1-mini")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["passed", "score", "reason"],
        "properties": {
            "passed": {"type": "boolean"},
            "score": {"type": "number"},
            "reason": {"type": "string"},
        },
    }
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "Compare chatbot ACTUAL response to EXPECTED response. Wording can differ. "
                    "Pass if the actual response fulfills the same user-facing purpose and key information is present."
                ),
            },
            {"role": "user", "content": json.dumps({"expected": expected, "actual": actual})},
        ],
        "text": {"format": {"type": "json_schema", "name": "chat_turn_eval", "strict": True, "schema": schema}},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
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
    return {
        "passed": bool(parsed.get("passed")),
        "score": max(0.0, min(1.0, float(parsed.get("score", 0)))),
        "reason": str(parsed.get("reason") or "LLM semantic evaluation completed."),
    }


def keyword_eval(expected: str, actual: str) -> Dict[str, Any]:
    expected_words = useful_words(expected)
    actual_words = useful_words(actual)
    if not expected_words:
        return {"passed": True, "score": 1.0, "reason": "Expected response had no scorable keywords."}
    overlap = len(expected_words.intersection(actual_words))
    score = round(overlap / max(1, len(expected_words)), 3)
    return {
        "passed": score >= 0.6,
        "score": score,
        "reason": f"Keyword fallback matched {overlap}/{len(expected_words)} important words.",
    }


def useful_words(value: str) -> set:
    stop = {"the", "and", "you", "your", "for", "with", "that", "this", "can", "are", "will", "please", "share"}
    return {word for word in re.findall(r"[a-z0-9]{3,}", value.lower()) if word not in stop}


def recommendations_for_result(case: Dict[str, Any], result: Dict[str, Any], evaluation: Dict[str, Any]) -> List[Dict[str, str]]:
    issues = evaluation["score"].get("issues", [])
    if not issues:
        return [
            {
                "area": case["flow_name"],
                "module": "Chat execution",
                "failure_mode": "Regression guardrail",
                "recommendation": "Keep this script in regression and add nearby negative paths.",
                "yellow_ai_hint": "No platform edit was made. Use this as a recurring web-widget smoke test.",
            }
        ]
    recommendations = []
    for issue in issues[:5]:
        if "selector" in issue.lower() or "input" in issue.lower() or "browser" in issue.lower():
            recommendations.append(
                {
                    "area": "Chat widget setup",
                    "module": "Chat execution",
                    "failure_mode": "Automation setup",
                    "recommendation": "Review chat URL, iframe hint, input selector, message selector, and send button selector.",
                    "yellow_ai_hint": "This is a test harness configuration issue unless the widget itself is unavailable.",
                }
            )
        else:
            recommendations.append(
                {
                    "area": case["flow_name"],
                    "module": "Conversation design",
                    "failure_mode": "Expected-vs-actual mismatch",
                    "recommendation": "Review the failed turn transcript and tighten the bot response, routing, KB answer, or workflow branch.",
                    "yellow_ai_hint": "Map the failed turn back to the relevant Yellow.ai agent, workflow, KB, or fallback branch.",
                }
            )
    return recommendations


def adapter_summary(case_results: List[Dict[str, Any]]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for item in case_results:
        adapter = item.get("result", {}).get("adapter", "unknown")
        summary[adapter] = summary.get(adapter, 0) + 1
    return summary


def flatten_recommendations(case_results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    seen = set()
    flattened = []
    for item in case_results:
        for recommendation in item.get("recommendations", []):
            key = (recommendation.get("area"), recommendation.get("recommendation"))
            if key in seen:
                continue
            seen.add(key)
            flattened.append({"flow_name": item.get("flow_name", ""), "channel": "chat", **recommendation})
    return flattened[:20]
