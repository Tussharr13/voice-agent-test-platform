"""
Document generator — converts discovery results into a comprehensive Markdown document.
"""

import json
from datetime import datetime
from api_client import BOT_ID, BASE_URL


def generate_document(results, bot_info):
    """Generate a detailed markdown document from discovery results."""
    lines = []
    a = lines.append

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Header ─────────────────────────────
    a("# Yellow.ai Agent Discovery Documentation\n")
    a(f"**Generated:** {ts}  ")
    a(f"**Bot ID:** `{BOT_ID}`  ")
    a(f"**Platform:** `{BASE_URL}`  ")
    a(f"**Total Probes Sent:** {bot_info.get('total_probes', 0)}  ")
    a(f"**Successful Responses:** {bot_info.get('successful', 0)}  ")
    a(f"**Errors:** {bot_info.get('errors', 0)}  ")
    a(f"**Time Taken:** {bot_info.get('elapsed', 0):.1f}s  ")
    a("\n---\n")

    # ── Table of Contents ──────────────────
    a("## 📑 Table of Contents\n")
    a("1. [Executive Summary](#executive-summary)")
    a("2. [Agent Identity & Capabilities](#agent-identity--capabilities)")
    categories = list(results.keys())
    for i, cat in enumerate(categories, 3):
        title = cat.replace("_", " ").title()
        anchor = cat.replace("_", "-")
        a(f"{i}. [{title}](#{anchor})")
    a(f"{len(categories) + 3}. [Raw API Response Samples](#raw-api-response-samples)")
    a(f"{len(categories) + 4}. [Error Analysis](#error-analysis)")
    a("\n---\n")

    # ── Executive Summary ──────────────────
    a("## Executive Summary\n")
    total = bot_info.get("total_probes", 0)
    success = bot_info.get("successful", 0)
    errors = bot_info.get("errors", 0)

    a(f"The agent was tested with **{total} discovery probes** across "
      f"**{len(categories)} categories**.\n")
    a(f"| Metric | Value |")
    a(f"|--------|-------|")
    a(f"| Total Probes | {total} |")
    a(f"| Successful Responses | {success} |")
    a(f"| Errors / Failures | {errors} |")
    a(f"| Response Rate | {(success/total*100) if total else 0:.1f}% |")
    a("")

    # Capabilities summary
    a("### Capabilities Detected\n")
    for cat, probes in results.items():
        responded = sum(1 for p in probes if p["success"])
        total_cat = len(probes)
        icon = "✅" if responded == total_cat else "⚠️" if responded > 0 else "❌"
        title = cat.replace("_", " ").title()
        a(f"- {icon} **{title}**: {responded}/{total_cat} probes got responses")
    a("\n---\n")

    # ── Agent Identity ─────────────────────
    a("## Agent Identity & Capabilities\n")
    identity_probes = results.get("greeting_and_identity", [])
    if identity_probes:
        for probe in identity_probes:
            a(f"**User:** {probe['input']}  ")
            a(f"**Bot:** {probe['response']}\n")
    a("\n---\n")

    # ── Category Sections ──────────────────
    for cat, probes in results.items():
        if cat == "greeting_and_identity":
            continue  # Already shown above

        title = cat.replace("_", " ").title()
        a(f"## {title}\n")

        # Category description
        desc = probes[0].get("category_desc", "") if probes else ""
        if desc:
            a(f"*{desc}*\n")

        # Summary table
        responded = sum(1 for p in probes if p["success"])
        a(f"**Probes:** {len(probes)} | **Responded:** {responded} | "
          f"**Errors:** {len(probes) - responded}\n")

        # Each probe and response
        a("| # | User Input | Bot Response | Status |")
        a("|---|-----------|-------------|--------|")
        for i, probe in enumerate(probes, 1):
            status = "✅" if probe["success"] else "❌"
            # Truncate response for table, escape pipes
            resp = probe["response"].replace("|", "\\|").replace("\n", " ")
            if len(resp) > 200:
                resp = resp[:200] + "..."
            inp = probe["input"].replace("|", "\\|")
            a(f"| {i} | {inp} | {resp} | {status} |")
        a("")

        # Detailed responses
        a(f"### Detailed Responses\n")
        for i, probe in enumerate(probes, 1):
            a(f"#### Probe {i}: \"{probe['input']}\"\n")
            if probe["success"]:
                a(f"```\n{probe['response']}\n```\n")
            else:
                a(f"> ❌ **Error:** `{probe['response'][:300]}`\n")
        a("---\n")

    # ── Raw API Samples ────────────────────
    a("## Raw API Response Samples\n")
    a("First successful response from each category for debugging/reference:\n")
    for cat, probes in results.items():
        title = cat.replace("_", " ").title()
        success_probe = next((p for p in probes if p["success"]), None)
        if success_probe:
            a(f"### {title}\n")
            a(f"**Input:** `{success_probe['input']}`\n")
            raw_str = json.dumps(success_probe.get("raw", {}), indent=2, default=str)
            if len(raw_str) > 1500:
                raw_str = raw_str[:1500] + "\n... (truncated)"
            a(f"```json\n{raw_str}\n```\n")
    a("---\n")

    # ── Error Analysis ─────────────────────
    a("## Error Analysis\n")
    all_errors = []
    for cat, probes in results.items():
        for p in probes:
            if not p["success"]:
                all_errors.append({
                    "category": cat.replace("_", " ").title(),
                    "input": p["input"],
                    "error": p["response"][:200],
                })

    if all_errors:
        a(f"**Total Errors:** {len(all_errors)}\n")
        a("| Category | Input | Error |")
        a("|----------|-------|-------|")
        for err in all_errors:
            a(f"| {err['category']} | {err['input']} | `{err['error']}` |")
    else:
        a("✅ No errors encountered during discovery.\n")

    a("\n---\n")
    a(f"*Document generated automatically by Yellow.ai Agent Documenter on {ts}*")

    return "\n".join(lines)
