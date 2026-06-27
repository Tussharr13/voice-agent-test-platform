import re
from typing import Any, Dict, List


FAILURE_RESPONSE_FORMAT = {
    "required_order": [
        "Pinpoint",
        "Evidence",
        "Root cause",
        "Exact Yellow.ai fix",
        "Regression test",
        "Confidence and missing evidence",
    ],
    "rules": [
        "Do not start with a generic summary when the user asks why a bot failed.",
        "Always name the most likely Yellow.ai artifact: agent, step, workflow, API, function, KB source, or fallback branch.",
        "Tie every claim to transcript turns, report IDs, snapshot IDs, page labels, URLs, or code/function snippets when available.",
        "If platform evidence is missing, say the exact page/artifact to snapshot next.",
        "Do not say only 'review routing', 'check workflow', or 'improve fallback' without naming the candidate route, branch, workflow, or function.",
        "Do not infer a different journey variant from a transcript unless the user explicitly says that variant.",
        "Do not label a post-action generic error as fallback when workflow/API/function evidence is more specific.",
    ],
    "template": (
        "Pinpoint: <Agent or module> -> <step/branch> -> <workflow/API/function>.\n"
        "Evidence: <failed turn, expected vs actual, report/snapshot/code evidence>.\n"
        "Root cause: <specific configuration/API/prompt/data issue>.\n"
        "Exact Yellow.ai fix: <what to change and where>.\n"
        "Regression test: <scenario to rerun>.\n"
        "Confidence and missing evidence: <high/medium/low plus exact missing page/log if any>."
    ),
}


def analyzer_failure_prompt() -> str:
    return (
        "When the user asks about a failed report, transcript, Yellow.ai snapshot, or root cause, behave like a senior "
        "Yellow.ai debugger. Your answer must use this diagnosis flow: Pinpoint, Evidence, Root cause, Exact Yellow.ai fix, "
        "Regression test, Confidence and missing evidence. Prefer concrete artifact names over broad categories. If the "
        "context contains failure_investigation_packets, use them first and do not ignore their candidate artifacts. "
        "If a packet includes ruled_out_artifacts, do not choose those artifacts unless you explicitly explain the contrary evidence."
    )


def failure_response_format() -> Dict[str, Any]:
    return FAILURE_RESPONSE_FORMAT


def build_failure_investigation_packets(reports: List[Dict[str, Any]], snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    packets: List[Dict[str, Any]] = []
    for report in reports[:3]:
        for case in report.get("case_results", [])[:12]:
            score = case.get("score", {}) if isinstance(case.get("score"), dict) else {}
            if not should_investigate(score):
                continue
            result = case.get("result", {}) if isinstance(case.get("result"), dict) else {}
            transcript = compact_transcript(result.get("transcript", []))
            evidence_text = case_evidence_text(case, transcript)
            classification = classify_failure(evidence_text)
            keywords = unique_terms(debug_keywords(evidence_text) + classification.get("keywords", []))
            packets.append(
                {
                    "report_id": report.get("id"),
                    "case_id": case.get("case_id"),
                    "flow_name": case.get("flow_name"),
                    "scenario_type": case.get("scenario_type"),
                    "score": {
                        "status": score.get("status"),
                        "overall_score": score.get("overall_score"),
                        "issues": score.get("issues", [])[:8],
                    },
                    "failed_turn": failed_turn(transcript),
                    "nearby_transcript": transcript[-8:],
                    "expected_response": expected_response_for_case(case, transcript),
                    "actual_response": actual_response_for_case(case, transcript),
                    "failure_type": classification["failure_type"],
                    "likely_yellow_ai_location": classification["locations"],
                    "probable_root_cause": classification["root_cause"],
                    "exact_fix_template": classification["fix"],
                    "verification_test": classification["verification"],
                    "ruled_out_artifacts": classification.get("ruled_out", []),
                    "evidence_priority": classification.get("evidence_priority", []),
                    "platform_evidence": match_snapshot_evidence(snapshots, classification["locations"], keywords),
                    "missing_evidence": missing_evidence(classification, snapshots),
                }
            )
    return packets[:15]


def build_readonly_specialist_brief(
    project: Dict[str, Any],
    reports: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build deterministic context that keeps Analyzer answers specific and read-only."""
    packets = build_failure_investigation_packets(reports[:3], snapshots)
    profile = project.get("bot_profile", {}) if isinstance(project.get("bot_profile"), dict) else {}
    platform = str(profile.get("yellow_ai_platform") or project.get("yellow_ai_target", {}).get("platform") or "yellow_ai").lower()
    return {
        "mode": "read_only_yellow_ai_qa_agent",
        "product_line": "Diagnose, recommend, and test. Do not edit.",
        "strict_no_edit_policy": [
            "Do not claim that Yellow.ai Studio, flows, agents, functions, APIs, KBs, databases, or production settings were changed.",
            "Do not provide publish instructions as an action already taken.",
            "You may recommend exact changes and regression tests, but edits require a future approval-gated executor that is out of scope right now.",
        ],
        "answer_contract": [
            "Start with the pinpointed issue, not a generic summary.",
            "Name the exact failed turn or say the transcript/log is missing.",
            "Map the issue to the most likely Yellow.ai artifact: agent, workflow/flow, step, function, API, KB source, database table, fallback branch, or debug log.",
            "Separate proven evidence from likely inference.",
            "Give the concrete fix as a recommendation, not as an executed edit.",
            "End with the regression test to rerun and the exact missing Yellow.ai page/log if confidence is not high.",
        ],
        "yellow_ai_navigation_hints": navigation_hints(platform),
        "report_failure_count": len(packets),
        "top_failure_briefs": [specialist_packet_brief(packet) for packet in packets[:8]],
        "snapshot_index": [specialist_snapshot_brief(snapshot) for snapshot in snapshots[:3]],
    }


def navigation_hints(platform: str) -> List[Dict[str, str]]:
    common = [
        {"artifact": "conversation evidence", "where": "Conversation logs / Call logs / message trace for the failed run"},
        {"artifact": "API/function evidence", "where": "Tools or Automation function/API configuration plus request/response logs"},
        {"artifact": "KB evidence", "where": "Knowledge base source document, matched answer, or no-answer policy"},
    ]
    if "nexus" in platform or "v3" in platform:
        return [
            {"artifact": "agent routing", "where": "Studio > AI Agent > Agents > active agent detail"},
            {"artifact": "super agent routing", "where": "Studio > AI Agent > Super Agent / Context Expert instructions"},
            {"artifact": "workflow step", "where": "Studio > Build > Flows > active workflow or linked classic flow"},
            *common,
        ]
    return [
        {"artifact": "flow branch", "where": "Automation > Build > Flows > active flow detail"},
        {"artifact": "intent routing", "where": "Automation > Train > Intents and utterances"},
        {"artifact": "fallback", "where": "Automation > Build > Fallback flow and fallback intent handling"},
        *common,
    ]


def specialist_packet_brief(packet: Dict[str, Any]) -> Dict[str, Any]:
    failed_turn = packet.get("failed_turn", {}) if isinstance(packet.get("failed_turn"), dict) else {}
    return {
        "report_id": packet.get("report_id"),
        "case_id": packet.get("case_id"),
        "flow_name": packet.get("flow_name"),
        "scenario_type": packet.get("scenario_type"),
        "failure_type": packet.get("failure_type"),
        "failed_turn": {
            "turn": failed_turn.get("turn"),
            "speaker": failed_turn.get("speaker"),
            "text": str(failed_turn.get("text", ""))[:500],
            "expected_text": str(failed_turn.get("expected_text", ""))[:500],
        },
        "likely_locations": packet.get("likely_yellow_ai_location", [])[:6],
        "probable_root_cause": packet.get("probable_root_cause"),
        "recommended_fix": packet.get("exact_fix_template"),
        "regression_test": packet.get("verification_test"),
        "platform_evidence": packet.get("platform_evidence", [])[:4],
        "missing_evidence": packet.get("missing_evidence", [])[:3],
        "ruled_out_artifacts": packet.get("ruled_out_artifacts", [])[:4],
    }


def specialist_snapshot_brief(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    pages = []
    for page in snapshot.get("pages", [])[:12]:
        pages.append(
            {
                "label": page.get("label"),
                "title": page.get("title"),
                "url": page.get("url"),
            }
        )
    return {
        "id": snapshot.get("id"),
        "status": snapshot.get("status"),
        "bot_id": snapshot.get("bot_id"),
        "summary": str(snapshot.get("summary", ""))[:800],
        "pages": pages,
    }


def should_investigate(score: Dict[str, Any]) -> bool:
    status = str(score.get("status") or "").lower()
    try:
        overall = float(score.get("overall_score", 0) or 0)
    except (TypeError, ValueError):
        overall = 0
    return status != "pass" or overall < 0.78 or bool(score.get("issues"))


def compact_transcript(transcript: Any) -> List[Dict[str, Any]]:
    if not isinstance(transcript, list):
        return []
    compact = []
    for turn in transcript[:30]:
        if not isinstance(turn, dict):
            continue
        compact.append(
            {
                "turn": turn.get("turn"),
                "speaker": turn.get("speaker"),
                "text": str(turn.get("text", ""))[:1200],
                "expected_text": str(turn.get("expected_text", ""))[:1200],
                "action": turn.get("action"),
                "timestamp": turn.get("timestamp"),
            }
        )
    return compact


def case_evidence_text(case: Dict[str, Any], transcript: List[Dict[str, Any]]) -> str:
    score = case.get("score", {}) if isinstance(case.get("score"), dict) else {}
    fields = [
        case.get("flow_name", ""),
        case.get("scenario_type", ""),
        case.get("goal", ""),
        case.get("expected_outcome", ""),
        " ".join(str(issue) for issue in score.get("issues", [])[:8]),
    ]
    for turn in transcript:
        fields.extend([turn.get("speaker", ""), turn.get("text", ""), turn.get("expected_text", ""), turn.get("action", "")])
    return re.sub(r"\s+", " ", " ".join(str(item or "") for item in fields)).strip()


def classify_failure(evidence_text: str) -> Dict[str, Any]:
    text = evidence_text.lower()
    if has_any(text, ["install", "installation", "new product", "delivered"]) or (
        has_any(text, ["amazon", "flipkart", "order id"]) and has_any(text, ["product", "pincode", "address", "case", "lead"])
    ):
        return {
            "failure_type": "Installation or booking journey creation failure",
            "locations": [
                artifact("agent", "Active installation/booking agent from snapshot", "The transcript shows a new installation or booking intent."),
                artifact("step", "Post-confirmation create/update step", "Failure appears after the user confirms collected details."),
                artifact("workflow", "Workflow that creates the booking/case/lead/request", "Expected to create an operational record after confirmation."),
                artifact("function", "API response or failure-message handler", "Likely maps backend/API errors into the final user-facing message."),
                artifact("api", "Create/update booking, case, lead, or service-request API", "Downstream API candidate for the post-confirmation action."),
            ],
            "root_cause": (
                "The bot likely collected enough conversational fields to reach final confirmation, but the downstream installation "
                "or booking creation returned a failure or lacked required business/API fields. The failure handler may be masking "
                "the true reason with a generic retry-later message."
            ),
            "fix": (
                "In the active installation/booking agent, validate required fields before the create/update workflow runs. In the "
                "workflow/API failure handler, preserve and branch by actual API response categories such as duplicate request, "
                "unserviceable location, missing required field, token/API timeout, validation error, and CRM/backend failure. Do not "
                "end with a generic retry-later message until the user receives the real actionable reason."
            ),
            "verification": (
                "Rerun the same installation/booking path with the failed transcript data. Expected result: either a successful created "
                "record/reference ID or a clear message requesting the missing/invalid required detail."
            ),
            "ruled_out": [
                {
                    "artifact": "Different journey variant not stated by the user",
                    "why": "Do not choose another similarly named journey from inventory unless the transcript or active snapshot names it.",
                },
                {
                    "artifact": "Generic NLU fallback",
                    "why": "If the failure appears after a deterministic confirmation/create step, inspect workflow/API/failure handlers before fallback.",
                },
                {
                    "artifact": "Missing final confirmation step",
                    "why": "If the transcript already includes detail confirmation, the problem is more likely the post-confirmation action.",
                },
            ],
            "evidence_priority": [
                "Prefer the active agent/step evidence over broad inventory matches.",
                "Prefer transcript sequence over keyword matches from Flows inventory.",
                "If a required business field is missing, inspect validation before fallback.",
                "If final bot text is retry-later after confirmation, inspect create/update workflow and API failure handlers first.",
            ],
            "keywords": [
                "installation",
                "booking",
                "confirmation",
                "create",
                "update",
                "request",
                "case",
                "lead",
                "order",
                "api",
                "workflow",
                "failure",
                "retry",
            ],
        }
    if has_any(text, ["service", "not working", "registered number", "warranty", "repair", "complaint"]):
        return {
            "failure_type": "Service workflow / registration gate failure",
            "locations": [
                artifact("agent", "Active service/support agent from snapshot", "Primary service intent agent candidate."),
                artifact("workflow", "User lookup or registration workflow", "Usually fetches user/product context before service case creation."),
                artifact("workflow", "Case/service request creation workflow", "Creates the operational service record."),
                artifact("function", "Service parameter builder or status handler", "Builds request fields or classifies API success/failure."),
                artifact("api", "Create/update service case API", "Downstream service case API candidate."),
            ],
            "root_cause": (
                "The service intent is likely reaching a registration or case-creation branch before the bot preserves the user's actual issue, "
                "or an older/common service agent is competing with the intended service agent."
            ),
            "fix": (
                "Make the active service agent acknowledge and store the issue before identity/registration validation. Then branch registered, "
                "unregistered, existing case, API failure, and handoff separately."
            ),
            "verification": "Rerun registered and non-registered service scenarios with the same product issue and verify the issue survives every branch.",
            "keywords": ["service", "registered", "case", "request", "api", "workflow", "handoff"],
        }
    if has_any(text, ["recommend", "product", "purifier", "family", "grand star", "which model", "buy"]):
        return {
            "failure_type": "Product recommendation / KB or demo-routing failure",
            "locations": [
                artifact("agent", "Active product recommendation or sales agent from snapshot", "May be triggered too early for advice queries."),
                artifact("agent", "Knowledge answer agent from snapshot", "Likely source of product facts and recommendation text."),
                artifact("knowledge_base", "Product catalog or recommendation KB", "Check whether source content biases toward one option."),
                artifact("function", "Product retrieval or ranking function", "Candidate function for product list/ranking behavior."),
                artifact("workflow", "Product card, quote, or demo workflow", "May be firing before the user confirms product/demo intent."),
            ],
            "root_cause": "The bot is probably treating advice/recommendation as a demo or product-list path before qualifying the user.",
            "fix": (
                "Change the recommendation branch to ask family size, water source/TDS, budget, and storage needs before presenting options. "
                "Only trigger product card, quote, or demo flow after user confirms that intent."
            ),
            "verification": "Rerun broad product-advice scenarios and verify the bot asks qualifying questions before naming SKUs.",
            "keywords": ["recommend", "product", "knowledge", "catalog", "ranking", "demo", "card"],
        }
    if has_any(text, ["order", "tracking", "track", "order status", "unsupported"]):
        return {
            "failure_type": "Unsupported order-tracking / fallback routing failure",
            "locations": [
                artifact("agent", "Fallback or unsupported-intent agent from snapshot", "Fallback/unsupported-intent candidate."),
                artifact("function", "Fallback/unsupported-intent classifier", "Candidate unsupported-intent classifier."),
                artifact("workflow", "Handoff or escalation workflow", "Escalation option when the bot cannot complete the request."),
            ],
            "root_cause": "The bot likely lacks an explicit unsupported order-tracking branch and falls back to a generic reset or unrelated path.",
            "fix": "Add an unsupported-intent branch that explains the limitation and offers the correct channel or handoff/escalation option.",
            "verification": "Rerun order ID/order tracking phrases and verify the bot does not reset to welcome or misroute.",
            "keywords": ["order", "tracking", "fallback", "unsupported", "handoff", "escalation"],
        }
    return {
        "failure_type": "General agent routing, workflow branch, or KB answer failure",
        "locations": [
            artifact("agent", "Candidate agent from report flow_name", "Use the report flow/scenario name to find the active agent."),
            artifact("workflow", "Candidate workflow/API from failed turn", "Inspect the workflow called immediately before the failed bot reply."),
            artifact("knowledge_base", "Candidate KB source", "Inspect KB only if expected answer is factual/static content."),
        ],
        "root_cause": "The report shows a mismatch, but available evidence does not identify a specific Yellow.ai artifact yet.",
        "fix": "Capture the active agent page, workflow/API page, debug log for the failed turn, and KB source if factual answer grounding is involved.",
        "verification": "Rerun the same scenario after capturing the missing platform pages and compare expected vs actual turn-by-turn.",
        "keywords": debug_keywords(text),
    }


def artifact(kind: str, name: str, why: str) -> Dict[str, str]:
    return {"type": kind, "name": name, "why": why}


def has_any(text: str, tokens: List[str]) -> bool:
    return any(token.lower() in text for token in tokens)


def expected_response_for_case(case: Dict[str, Any], transcript: List[Dict[str, Any]]) -> str:
    result = case.get("result", {}) if isinstance(case.get("result"), dict) else {}
    expected_texts = [str(turn.get("expected_text", "")).strip() for turn in transcript if turn.get("expected_text")]
    return result.get("expected_response") or result.get("expected_bot_response") or " | ".join(expected_texts) or str(case.get("expected_outcome", ""))


def actual_response_for_case(case: Dict[str, Any], transcript: List[Dict[str, Any]]) -> str:
    result = case.get("result", {}) if isinstance(case.get("result"), dict) else {}
    actual_texts = [str(turn.get("text", "")).strip() for turn in transcript if turn.get("speaker") == "bot" and turn.get("text")]
    return result.get("actual_response") or result.get("bot_response") or result.get("observed_response") or " | ".join(actual_texts)


def failed_turn(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    for turn in reversed(transcript):
        if turn.get("expected_text") or str(turn.get("speaker", "")).lower() == "bot":
            return turn
    return transcript[-1] if transcript else {}


def debug_keywords(value: str) -> List[str]:
    stop = {
        "actual",
        "assistant",
        "because",
        "branch",
        "case",
        "chat",
        "expected",
        "failed",
        "flow",
        "from",
        "issue",
        "message",
        "response",
        "scenario",
        "status",
        "that",
        "this",
        "turn",
        "user",
        "with",
        "yellow",
        "would",
        "should",
        "please",
        "details",
    }
    words = []
    for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", value.lower()):
        if word not in stop and word not in words:
            words.append(word)
    preferred = [
        word
        for word in words
        if word
        in {
            "agent",
            "api",
            "fallback",
            "function",
            "handoff",
            "installation",
            "intent",
            "kb",
            "knowledge",
            "lead",
            "order",
            "pincode",
            "product",
            "registered",
            "routing",
            "service",
            "workflow",
        }
    ]
    remainder = [word for word in words if word not in preferred]
    return (preferred + remainder)[:28]


def unique_terms(items: List[str]) -> List[str]:
    seen = set()
    output = []
    for item in items:
        clean = str(item or "").strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            output.append(clean)
    return output[:36]


def match_snapshot_evidence(
    snapshots: List[Dict[str, Any]],
    locations: List[Dict[str, str]],
    keywords: List[str],
) -> List[Dict[str, Any]]:
    candidates = []
    search_terms = unique_terms([item["name"] for item in locations] + keywords)
    for snapshot in snapshots:
        for page in snapshot.get("pages", [])[:18]:
            page_text = snapshot_page_search_text(page)
            if not page_text:
                continue
            matched = [term for term in search_terms if term and term.lower() in page_text]
            if not matched:
                continue
            candidates.append(
                {
                    "snapshot_id": snapshot.get("id"),
                    "page_label": page.get("label"),
                    "page_title": page.get("title"),
                    "page_url": page.get("url"),
                    "matched_terms": matched[:12],
                    "evidence_snippets": page_snippets(page_text, matched[:5]),
                }
            )
    candidates.sort(key=lambda item: len(item["matched_terms"]), reverse=True)
    return candidates[:8]


def snapshot_page_search_text(page: Dict[str, Any]) -> str:
    signals = page.get("signals", {}) if isinstance(page.get("signals"), dict) else {}
    parts = [page.get("label", ""), page.get("title", ""), page.get("url", ""), page.get("text_preview", "")]
    for key in ["headings", "buttons", "links", "inputs"]:
        for item in signals.get(key, []) if isinstance(signals.get(key, []), list) else []:
            if isinstance(item, dict):
                parts.extend([item.get("text", ""), item.get("href", ""), item.get("aria", ""), item.get("role", "")])
    for table in signals.get("tables", []) if isinstance(signals.get("tables", []), list) else []:
        if isinstance(table, list):
            parts.append(" ".join(" ".join(str(cell) for cell in row) for row in table[:25] if isinstance(row, list)))
    for snippet in signals.get("code_snippets", []) if isinstance(signals.get("code_snippets", []), list) else []:
        parts.append(str(snippet))
    return re.sub(r"\s+", " ", " ".join(str(part or "") for part in parts)).lower()


def page_snippets(page_text: str, terms: List[str]) -> List[str]:
    snippets = []
    for term in terms:
        needle = term.lower()
        index = page_text.find(needle)
        if index < 0:
            continue
        start = max(0, index - 140)
        end = min(len(page_text), index + 260)
        snippet = page_text[start:end].strip()
        if snippet and snippet not in snippets:
            snippets.append(snippet)
    return snippets[:5]


def missing_evidence(classification: Dict[str, Any], snapshots: List[Dict[str, Any]]) -> List[str]:
    if not snapshots:
        return [
            "Run a read-only platform snapshot for Agents inventory, active agent detail page, Tools > API, Tools > Functions, and the failed conversation/call debug log.",
        ]
    required = []
    for location in classification.get("locations", []):
        if location.get("type") in {"agent", "workflow", "function", "api", "knowledge_base"}:
            required.append(f"{location['type']}: {location['name']}")
    return [
        "If not present in platform_evidence, capture these exact artifacts next: " + "; ".join(required[:8])
    ]
