#!/usr/bin/env python3
"""
Yellow.ai Agent Documenter — Main Entry Point.

Sends discovery probes to the bot via the Sync Message API,
captures all responses, and generates a comprehensive markdown document.

Uses ONLY Python standard library — no pip packages required.

Usage:
    python documenter.py                  # Full discovery (~85 probes)
    python documenter.py --quick          # Quick run (first 3 per category)
    python documenter.py --category loans # Specific category only
    python documenter.py --delay 2.0      # Custom delay between probes
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime

from api_client import ask_bot, BOT_ID, BASE_URL, API_KEY, SYNC_URL, endpoint_candidates, mask_secret
from discovery_probes import DISCOVERY_PROBES, get_total_count
from doc_generator import generate_document


# ──────────────────────────────────────────────
#  ANSI Colors
# ──────────────────────────────────────────────

class C:
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"


def col(text, color):
    return f"{color}{text}{C.RESET}"


# ──────────────────────────────────────────────
#  Main Discovery Runner
# ──────────────────────────────────────────────

def run_discovery(quick=False, category_filter=None, delay=1.5, dry_run=False):
    """Run discovery probes and generate documentation."""

    # Validate config
    if not API_KEY:
        print(col("\n❌ YELLOW_AI_API_KEY not set in .env file.", C.RED))
        sys.exit(1)
    if not BOT_ID:
        print(col("\n❌ YELLOW_AI_BOT_ID not set in .env file.", C.RED))
        sys.exit(1)

    # Filter categories
    categories = DISCOVERY_PROBES
    if category_filter:
        matches = {k: v for k, v in categories.items()
                   if category_filter.lower() in k.lower()}
        if not matches:
            print(col(f"❌ No category matching '{category_filter}'", C.RED))
            print(f"   Available: {list(categories.keys())}")
            sys.exit(1)
        categories = matches

    # Count probes
    total_probes = 0
    for cat_data in categories.values():
        prompts = cat_data["prompts"][:3] if quick else cat_data["prompts"]
        total_probes += len(prompts)

    # Header
    print()
    print(col("=" * 65, C.CYAN))
    print(col("  🔍 Yellow.ai Agent Documenter", C.BOLD + C.CYAN))
    print(col("=" * 65, C.CYAN))
    print(f"  Bot ID:    {col(BOT_ID, C.BOLD)}")
    print(f"  Endpoint:  {col(BASE_URL, C.DIM)}")
    print(f"  API Key:   {col(mask_secret(API_KEY), C.DIM)}")
    print(f"  Sync URL:  {col(SYNC_URL or endpoint_candidates()[0], C.DIM)}")
    print(f"  Probes:    {col(str(total_probes), C.BOLD)}"
          f"{'  (quick mode)' if quick else ''}")
    print(f"  Delay:     {delay}s between probes")
    print(col("=" * 65, C.CYAN))
    print()

    if dry_run:
        print(col("  Dry run only. No API calls will be sent.", C.BOLD + C.YELLOW))
        for cat_name, cat_data in categories.items():
            prompts = cat_data["prompts"][:3] if quick else cat_data["prompts"]
            print(col(f"\n── {cat_name.replace('_', ' ').title()} ──", C.BOLD + C.CYAN))
            for prompt in prompts:
                print(f"  - {prompt}")
        print()
        return {}

    # Run probes
    results = {}
    total_done = 0
    total_success = 0
    total_errors = 0
    start_time = time.time()

    for cat_name, cat_data in categories.items():
        cat_title = cat_name.replace("_", " ").title()
        prompts = cat_data["prompts"][:3] if quick else cat_data["prompts"]

        print(col(f"\n── {cat_title} ({len(prompts)} probes) ──", C.BOLD + C.CYAN))

        cat_results = []
        for i, prompt in enumerate(prompts):
            total_done += 1
            progress = f"[{total_done}/{total_probes}]"
            print(f"  {col(progress, C.DIM)} ", end="", flush=True)

            result = ask_bot(prompt, delay=delay)
            result["category_desc"] = cat_data["description"]

            if result["success"]:
                total_success += 1
                status = col("✅", C.GREEN)
                resp_preview = result["response"][:80].replace("\n", " ")
                print(f"{status} {col(prompt[:40], C.DIM)}")
                print(f"         → {col(resp_preview, C.DIM)}")
            else:
                total_errors += 1
                status = col("❌", C.RED)
                print(f"{status} {col(prompt[:40], C.DIM)}")
                print(f"         → {col(result['response'][:80], C.YELLOW)}")

            cat_results.append(result)

        results[cat_name] = cat_results

    elapsed = time.time() - start_time

    # ── Summary ──────────────────────────────
    print()
    print(col("=" * 65, C.CYAN))
    print(col("  📊 Discovery Summary", C.BOLD + C.CYAN))
    print(col("=" * 65, C.CYAN))
    print(f"  Total Probes:  {col(str(total_probes), C.BOLD)}")
    print(f"  Successful:    {col(str(total_success), C.GREEN + C.BOLD)}")
    print(f"  Errors:        {col(str(total_errors), C.RED + C.BOLD if total_errors else C.GREEN + C.BOLD)}")
    rate = (total_success / total_probes * 100) if total_probes else 0
    print(f"  Response Rate: {col(f'{rate:.1f}%', C.GREEN + C.BOLD if rate >= 80 else C.RED + C.BOLD)}")
    print(f"  Time:          {elapsed:.1f}s ({elapsed/total_probes:.1f}s avg)")
    print()

    # ── Generate Document ────────────────────
    print(col("  📝 Generating documentation...", C.BOLD))

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bot_info = {
        "total_probes": total_probes,
        "successful": total_success,
        "errors": total_errors,
        "elapsed": elapsed,
    }

    # Markdown document
    md_path = os.path.join(output_dir, f"agent_doc_{timestamp}.md")
    md_content = generate_document(results, bot_info)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"  ✅ Markdown: {col(md_path, C.BOLD)}")

    # Raw JSON data
    json_path = os.path.join(output_dir, f"agent_raw_{timestamp}.json")
    # Strip raw responses for JSON (can be large)
    save_results = {}
    for cat, probes in results.items():
        save_results[cat] = [{
            "input": p["input"],
            "response": p["response"],
            "success": p["success"],
            "raw": p.get("raw", {}),
        } for p in probes]

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "bot_id": BOT_ID,
            "base_url": BASE_URL,
            "summary": bot_info,
            "results": save_results,
        }, f, indent=2, default=str)
    print(f"  ✅ Raw JSON: {col(json_path, C.BOLD)}")

    print()
    print(col("  🎉 Done! Documentation generated.", C.BOLD + C.GREEN))
    print(col("=" * 65, C.CYAN))
    print()

    return results


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yellow.ai Agent Documenter")
    parser.add_argument("--quick", action="store_true",
                        help="Quick mode — first 3 probes per category")
    parser.add_argument("--category", type=str, default=None,
                        help="Run only a specific category (e.g., 'loan', 'card')")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Delay between API calls in seconds (default: 1.5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print selected probes and config without calling Yellow.ai")
    args = parser.parse_args()

    run_discovery(quick=args.quick, category_filter=args.category, delay=args.delay, dry_run=args.dry_run)
