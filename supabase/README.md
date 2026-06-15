# Supabase Setup

Use this folder to create the Supabase database layer for the Bot QA Workbench.

## 1. Create Project

Create a Supabase project from the Supabase dashboard. Keep these values ready:

```text
Project URL
Service role key
```

Use the service-role key only in backend/local `.env`. Do not put it in
`static/`, browser code, or client-side settings.

## 2. Run Current App Schema

Open the Supabase SQL editor and run the bridge schema used by the current app:

```bash
python3 scripts/supabase_state.py schema
```

Copy the output into the Supabase SQL editor and execute it.

This creates:

```text
public.bot_qa_state
```

The table stores the complete app workspace state as JSONB for now:

```text
projects, chats, documents, change plans, suites, runs, reports, settings
```

## 2b. Prepare Product Schema

The actual product model is user/project based. To create those normalized
tables too, run:

```bash
python3 scripts/supabase_state.py product-schema
```

Copy that SQL into Supabase SQL editor and execute it.

This creates:

```text
profiles
projects
chats
chat_messages
documents
change_plans
test_suites
test_cases
test_runs
reports
user_settings
```

The backend still uses `bot_qa_state` today. The normalized tables are the next
migration target for real login, user-owned projects, project chats, and
project-specific testing data.

To verify the product tables from the terminal:

```bash
python3 scripts/supabase_product.py check
```

## 2c. Create Product Owner And Seed Normalized Tables

The normalized schema uses Supabase Auth users as owners:

```text
auth.users -> profiles -> projects -> chats/docs/testing artifacts
```

If a Supabase Auth user already exists, save the first user into `.env`:

```bash
python3 scripts/supabase_product.py users --save-first
```

For a local dev owner, create a confirmed user and save its ID locally:

```bash
python3 scripts/supabase_product.py create-user \
  --email botqa-dev@example.com \
  --full-name "Bot QA Dev Owner" \
  --generate-password \
  --save-env
```

Then seed the normalized product tables from the current bridge state:

```bash
python3 scripts/supabase_product.py seed --source supabase
```

This does not replace the current app runtime yet. It prepares the real
multi-user/product tables while the Python APIs continue to read and write the
bridge row.

## 3. Configure App

In project `.env`:

```bash
SUPABASE_ENABLED=true
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_TABLE=bot_qa_state
SUPABASE_STATE_ID=default
SUPABASE_STRICT=false
SUPABASE_APP_USER_ID=
SUPABASE_APP_USER_EMAIL=
SUPABASE_PRODUCT_SYNC=
SUPABASE_PRODUCT_STRICT=false
```

Then restart the Python app.

Check local config:

```bash
python3 scripts/supabase_state.py status
```

## 4. Migration Behavior

To explicitly copy the current local workspace into Supabase:

```bash
python3 scripts/supabase_state.py seed
```

To download Supabase state into a local backup file:

```bash
python3 scripts/supabase_state.py pull --output data/state.from_supabase.json
```

If the Supabase row is missing, the app can also seed it from the local
`data/state.json` on first load through the storage adapter. Keep
`data/state.json` as a backup during the first migration.

When `SUPABASE_APP_USER_ID` is configured, the app also mirrors each saved
bridge state into the normalized product tables. Set
`SUPABASE_PRODUCT_SYNC=false` to turn that mirror off, or
`SUPABASE_PRODUCT_STRICT=true` if product-table sync failures should fail the
request instead of only being reported in `/api/config`.

## Current Model

This first version intentionally uses one JSONB row so the app can move from
local JSON to Supabase without rewriting every API endpoint.

The product schema already defines the normalized target:

```text
projects
chats
chat_messages
documents
test_suites
test_runs
reports
change_plans
```
