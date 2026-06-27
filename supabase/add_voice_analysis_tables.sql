-- Add voice call analysis tables for the Bot QA Workbench product schema.
--
-- Safe to run in Supabase SQL editor. It only creates missing tables,
-- indexes, triggers, and RLS policies.

create extension if not exists pgcrypto;

create table if not exists public.voice_calls (
  id uuid primary key default gen_random_uuid(),
  app_call_id text,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  bot_id text,
  started_at timestamptz,
  ended_at timestamptz,
  uid text,
  from_number text,
  to_number text,
  direction text,
  status text,
  hangup_reason text,
  hangup_source text,
  severity text,
  classification_status text,
  primary_issue text,
  summary text,
  turns jsonb not null default '[]'::jsonb,
  traces jsonb not null default '[]'::jsonb,
  issues jsonb not null default '[]'::jsonb,
  raw_cdr jsonb not null default '{}'::jsonb,
  metrics jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.voice_sync_runs (
  id uuid primary key default gen_random_uuid(),
  app_sync_id text,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  bot_id text,
  range_mode text not null default 'preset',
  date_from date,
  date_to date,
  range_label text,
  days_back integer,
  calls_pulled integer not null default 0,
  failed_calls integer not null default 0,
  messages_loaded integer not null default 0,
  pending_deep_analysis integer not null default 0,
  status text not null default 'ok',
  message text,
  message_errors jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists voice_calls_user_app_call_idx
  on public.voice_calls(user_id, app_call_id);

create index if not exists voice_calls_user_project_idx
  on public.voice_calls(user_id, project_id, started_at desc);

create index if not exists voice_calls_project_status_idx
  on public.voice_calls(project_id, classification_status);

create index if not exists voice_calls_primary_issue_idx
  on public.voice_calls(primary_issue);

create unique index if not exists voice_sync_runs_user_app_sync_idx
  on public.voice_sync_runs(user_id, app_sync_id);

create index if not exists voice_sync_runs_user_project_idx
  on public.voice_sync_runs(user_id, project_id, created_at desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

do $$
begin
  if not exists (select 1 from pg_trigger where tgname = 'voice_calls_set_updated_at') then
    create trigger voice_calls_set_updated_at before update on public.voice_calls
    for each row execute function public.set_updated_at();
  end if;
end
$$;

alter table public.voice_calls enable row level security;
alter table public.voice_sync_runs enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'voice_calls'
      and policyname = 'voice_calls_all_own'
  ) then
    create policy voice_calls_all_own on public.voice_calls
    for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'voice_sync_runs'
      and policyname = 'voice_sync_runs_all_own'
  ) then
    create policy voice_sync_runs_all_own on public.voice_sync_runs
    for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
end
$$;
