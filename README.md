# Yellow.ai Chat QA Workbench

Local MVP for Yellow.ai chat testing, failure analysis, and debugging acceleration.

## What This Builds

- AI-generated chat test ideas for bot flows.
- Coverage matrix across flows, scenario types, and personas.
- Real Playwright web-widget chat automation.
- Read-only Yellow.ai platform snapshots for automated Analyzer context.
- Deterministic and AI-ready evaluation metrics.
- Reports with Yellow.ai-style failure analysis and improvement recommendations.
- Project-level Yellow.ai target metadata and widget selectors.

The Python backend runs without external package dependencies. The browser workbench is now React-based and currently loads React/Babel from CDN scripts in `static/index.html`. If `OPENAI_API_KEY` is present, the generator can call OpenAI for structured test generation. Without it, the app uses a deterministic fallback generator so the platform still works.

Most bot-specific IDs, Yellow.ai keys, widget URLs, and selectors can be changed from the dashboard without editing environment files.

## Workspace Layout

The dashboard is now a project-based workbench:

- **Analyzer**: real OpenAI-backed project chat with docs, suites, reports, and Yellow.ai target context.
- **Platform snapshots**: read-only Playwright capture of Yellow.ai Studio/Automation text, relevant links, and network metadata from a logged-in session for automated Analyzer context.
- **Testing**: bot profile, chat script execution, scoring, failure analysis, and reports.
- **Docs**: handbook/search/docs assistant plus project document upload and change plans.

Existing suites, runs, reports, documents, and plans are attached to a default `Yellow.ai Chat QA Workbench` project on first load.

## Code Layout

- `app.py` keeps the local HTTP server, testing logic, document extraction, scoring, and API routing.
- `backend/storage.py` owns local JSON or Supabase persistence.
- `backend/workspace.py` owns project migration, project/chat state, docs pages/search, and OpenAI analyzer/docs chat context.
- `static/index.html`, `static/App.jsx`, and `static/styles.css` own the React browser workbench UI.

## Run

```bash
cd /Users/tussharsingh/Documents/Projects/rag-work/voice-agent-test-platform
python3 app.py
```

Open:

```text
http://127.0.0.1:8787
```

Optional environment:

```bash
export OPENAI_API_KEY="..."
export OPENAI_MODEL="gpt-4.1-mini"
export APP_PORT=8787
```

For local development, you can also create `.env` next to `app.py`:

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
```

`.env` is ignored by git. This local MVP also reads `.env.example` as a fallback because this workspace currently has credentials there, but the safer habit is to keep real keys in `.env` and leave `.env.example` as placeholders.

Use `.env.example` as the integration checklist for OpenAI, Supabase, and Yellow.ai credentials.

## Supabase Persistence

By default, workspace state is saved to `data/state.json`. To persist projects,
chats, documents, suites, runs, reports, and settings in Supabase instead, create
one JSONB-backed state table in Supabase SQL editor.

Print the schema:

```bash
python3 scripts/supabase_state.py schema
```

Paste that SQL into Supabase SQL editor and run it.

Then configure `.env`:

```bash
SUPABASE_ENABLED=true
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_TABLE=bot_qa_state
SUPABASE_STATE_ID=default
```

Seed the current local workspace into Supabase:

```bash
python3 scripts/supabase_state.py seed
```

Use the service-role key only on the backend/local machine; never expose it in
browser code. When Supabase is configured and no state row exists yet, the app
seeds Supabase from the existing local `data/state.json`. If Supabase is
temporarily unavailable, the app falls back to local JSON unless
`SUPABASE_STRICT=true`.

For the normalized multi-user model, create the product tables and seed them
under a Supabase Auth user:

```bash
python3 scripts/supabase_state.py product-schema
python3 scripts/supabase_product.py check
python3 scripts/supabase_product.py users --save-first
python3 scripts/supabase_product.py seed --source supabase
```

If there are no Auth users yet, create a local dev owner first:

```bash
python3 scripts/supabase_product.py create-user \
  --email botqa-dev@example.com \
  --full-name "Bot QA Dev Owner" \
  --generate-password \
  --save-env
```

The current Python app still runs on the `bot_qa_state` bridge row. The
normalized tables are mirrored after each bridge save for the signed-in user
or the configured `SUPABASE_APP_USER_ID`, preparing the next API migration
where each user owns their projects, chats, docs, suites, runs, and reports.
App-facing IDs such as `run_...`, `report_...`, and `suite_...` are mirrored
into `app_run_id`, `app_report_id`, and `app_suite_id` columns when the optional
`supabase/add_app_id_columns.sql` migration has been applied. Until then, the
sync falls back to the older JSON metadata fields.
Analyzer-prepared goal-driven test briefs can also be mirrored on projects after
running `supabase/add_goal_brief_columns.sql`.

## Login And Signup

The app uses simple email/password auth through the Python backend. The browser
never receives the Supabase service-role key.

- `POST /api/auth/signup` creates a confirmed Supabase Auth user.
- `POST /api/auth/login` creates an HTTP-only local session cookie.
- `POST /api/auth/logout` clears the session cookie.

Each signed-in user gets a separate bridge-state row in Supabase, and saves are
mirrored into the normalized product tables under that user.

## Runtime Settings

Open **Settings** in the dashboard to save local runtime values without editing files for every bot:

- Default bot name and chat endpoint.
- OpenAI key and model.
- Yellow.ai API values and default widget URL.

Settings are saved in the active persistence layer: `data/state.json` by default,
or Supabase when configured. Secret values are accepted by the dialog but are not
returned by `/api/config`; the UI only shows whether a secret is already
configured.

## Project Knowledge

Use **Docs > Project Knowledge** to upload bot docs, test plans, transcripts, PDFs, DOCX files, Markdown scripts, or automation guides. The app extracts readable text, analyzes it against the current project Bot Profile and Yellow.ai target fields, then creates:

- key insights,
- suggested Yellow.ai changes,
- suggested test cases,
- a pending approval plan.

No Yellow.ai change is executed automatically. Plans stay local until explicitly approved, and real platform execution should remain gated behind a separate access/approval step.

## Current MVP Behavior

The current executable path is real web-widget chat automation:

- Chat scripts are written in Markdown.
- Playwright opens the configured Yellow.ai liveBot/widget URL.
- The runner clicks quick replies, types user messages, waits for fresh bot replies, and captures transcript evidence.
- Reports map expected-vs-actual failures to likely Yellow.ai debugging areas.

Generated suites are planning artifacts. Use **Testing > Chat Testing > Chat Automation** for real execution.

## In-House Testing Model

The platform uses an evaluator-style model focused on Yellow.ai chat debugging:

- Each generated test case has evaluator instructions.
- Each test has an expected outcome.
- Each test has a persona and test profile.
- Each test carries a metric bundle.
- Real chat automation reports include transcript evidence, adapter status, DOM/browser evidence, and module-level recommendations.

This keeps the workflow practical for our team without needing a full commercial testing platform setup.

## Metrics We Track

Core metrics:

- Expected outcome
- Instruction following
- Intent accuracy
- Response relevance
- Context retention
- CSAT/sentiment-ready scoring

Chat automation evidence:

- Expected vs actual response
- Captured transcript turns
- Quick-reply/button action path
- Response latency
- Browser artifact path
- Likely Yellow.ai module

The app also exposes `/api/config`, which reports whether each integration is configured without exposing secret values.

## Chat Automation Setup

Per project, configure:

- Yellow.ai liveBot/widget URL
- launcher selector
- input selector
- message selector
- optional iframe hint
- timeout

Then paste or upload a Markdown script and run it from **Testing > Chat Testing > Chat Automation**.

## Next Integrations

Chat and analysis:

- Yellow.ai conversation API, if available.
- Better root-cause issue cards.
- One-click retest for failed flows.
- Exported transcript/import workflow.

MCP:

- Expose tools like `generate_test_suite`, `run_test`, `get_report`, and `suggest_yellow_ai_changes` after the core platform is stable.
