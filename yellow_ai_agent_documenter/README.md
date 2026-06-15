# Yellow.ai Agent Documenter

Small utility for discovering and documenting a Yellow.ai bot by sending safe,
read-only probes to the bot API.

It is separate from the main React QA workbench. Use it when you want a raw
agent capability map that can later be uploaded into the main app's Docs tab.

## What It Does

```text
Discovery probes -> Yellow.ai sync message API -> bot responses -> Markdown + JSON
```

The probes are grouped around identity, routing, order/status flows, complaints,
refund/payment handling, fallback behavior, handoff, memory, safety, and
voice-readiness.

## Files

```text
documenter.py        CLI entry point
api_client.py        Standard-library Yellow.ai sync-message client
discovery_probes.py  Safe read-only probe prompts
doc_generator.py     Markdown report generator
dashboard_scraper.py Optional Playwright dashboard scraper
extract_cookies.py   Optional Chrome cookie extraction helper
output/              Generated reports and scraper dumps
```

## Required Config

Create or update `yellow_ai_agent_documenter/.env`:

```bash
YELLOW_AI_BOT_ID=...
YELLOW_AI_API_KEY=...
YELLOW_AI_BASE_URL=https://cloud.yellow.ai
```

Recommended if your workspace route differs:

```bash
YELLOW_AI_SYNC_URL=https://your-region.yellow.ai/api/...
```

`YELLOW_AI_SYNC_URL` can include `{bot_id}` and `{base_url}` placeholders.

Optional:

```bash
YELLOW_AI_CHANNEL=api
YELLOW_AI_SENDER_STRATEGY=per_probe
YELLOW_AI_FETCH_VARIABLES=variable_one,variable_two
YELLOW_AI_TIMEOUT=35
```

Keep real secrets in `.env` only. Do not commit API keys or passwords.

## Usage

```bash
cd yellow_ai_agent_documenter
python3 documenter.py --dry-run
python3 documenter.py --quick
python3 documenter.py
python3 documenter.py --category handoff --delay 2.0
```

Outputs:

```text
output/agent_doc_<timestamp>.md
output/agent_raw_<timestamp>.json
```

## Optional Dashboard Scraping

`dashboard_scraper.py` and `extract_cookies.py` are experimental helpers and are
not required by `documenter.py`.

They need optional packages:

```bash
pip install playwright browser-cookie3
python3 -m playwright install chromium
```

Use dashboard scraping only in a logged-in/local session and avoid making edits
on Yellow.ai unless an explicit approval flow is added.
