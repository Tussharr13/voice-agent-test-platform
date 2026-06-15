-- Bot QA Workbench product schema
--
-- This is the normalized multi-user schema for the real product model:
-- users -> projects -> analyzer/docs chats + testing suites/runs/reports.
--
-- Safe to run after creating the Supabase project. It avoids DROP statements.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  full_name text,
  role text not null default 'qa_user',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  description text,
  bot_profile jsonb not null default '{}'::jsonb,
  yellow_ai_target jsonb not null default '{}'::jsonb,
  goal_test_brief jsonb not null default '{}'::jsonb,
  goal_test_briefs jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.chats (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  title text not null default 'New chat',
  mode text not null default 'analyzer',
  attached_artifacts jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chats_mode_check check (mode in ('analyzer', 'docs'))
);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  chat_id uuid not null references public.chats(id) on delete cascade,
  role text not null,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint chat_messages_role_check check (role in ('user', 'assistant', 'system'))
);

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  filename text not null,
  content_type text,
  size_bytes bigint not null default 0,
  storage_path text,
  text_preview text,
  extracted_text text,
  analysis_status text not null default 'uploaded',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.change_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  document_id uuid references public.documents(id) on delete set null,
  title text not null default 'Change plan',
  summary text,
  status text not null default 'pending',
  suggested_changes jsonb not null default '[]'::jsonb,
  suggested_test_cases jsonb not null default '[]'::jsonb,
  execution_status text,
  execution_note text,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint change_plans_status_check check (status in ('pending', 'approved', 'rejected'))
);

create table if not exists public.test_suites (
  id uuid primary key default gen_random_uuid(),
  app_suite_id text,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  name text not null,
  source text,
  bot_profile jsonb not null default '{}'::jsonb,
  coverage_matrix jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.test_cases (
  id uuid primary key default gen_random_uuid(),
  app_case_id text,
  app_suite_id text,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  suite_id uuid not null references public.test_suites(id) on delete cascade,
  name text not null,
  channel text not null default 'chat',
  scenario_type text,
  persona text,
  goal text,
  steps jsonb not null default '[]'::jsonb,
  expected_outcome text,
  evaluator_instructions text,
  metrics jsonb not null default '[]'::jsonb,
  yellow_ai jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint test_cases_channel_check check (channel in ('chat', 'voice'))
);

alter table public.test_cases
  add column if not exists metadata jsonb not null default '{}'::jsonb;

alter table public.test_suites
  add column if not exists app_suite_id text;

alter table public.test_cases
  add column if not exists app_case_id text,
  add column if not exists app_suite_id text;

create table if not exists public.test_runs (
  id uuid primary key default gen_random_uuid(),
  app_run_id text,
  app_suite_id text,
  app_report_id text,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  suite_id uuid references public.test_suites(id) on delete set null,
  channel_filter text not null default 'all',
  status text not null default 'completed',
  average_score numeric,
  total_cases integer not null default 0,
  run_summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.reports (
  id uuid primary key default gen_random_uuid(),
  app_report_id text,
  app_run_id text,
  app_suite_id text,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  run_id uuid references public.test_runs(id) on delete cascade,
  suite_id uuid references public.test_suites(id) on delete set null,
  summary jsonb not null default '{}'::jsonb,
  case_results jsonb not null default '[]'::jsonb,
  yellow_ai_recommendations jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.user_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.test_runs
  add column if not exists app_run_id text,
  add column if not exists app_suite_id text,
  add column if not exists app_report_id text;

alter table public.reports
  add column if not exists app_report_id text,
  add column if not exists app_run_id text,
  add column if not exists app_suite_id text;

create index if not exists projects_user_id_idx on public.projects(user_id);
create index if not exists chats_user_project_idx on public.chats(user_id, project_id);
create index if not exists chat_messages_chat_id_idx on public.chat_messages(chat_id);
create index if not exists documents_user_project_idx on public.documents(user_id, project_id);
create index if not exists change_plans_user_project_idx on public.change_plans(user_id, project_id);
create index if not exists test_suites_user_project_idx on public.test_suites(user_id, project_id);
create index if not exists test_cases_suite_id_idx on public.test_cases(suite_id);
create index if not exists test_runs_user_project_idx on public.test_runs(user_id, project_id);
create index if not exists reports_user_project_idx on public.reports(user_id, project_id);
create index if not exists test_suites_app_suite_id_idx on public.test_suites(app_suite_id);
create index if not exists test_cases_app_case_id_idx on public.test_cases(app_case_id);
create index if not exists test_runs_app_run_id_idx on public.test_runs(app_run_id);
create index if not exists test_runs_app_report_id_idx on public.test_runs(app_report_id);
create index if not exists reports_app_report_id_idx on public.reports(app_report_id);
create index if not exists reports_app_run_id_idx on public.reports(app_run_id);

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
  if not exists (select 1 from pg_trigger where tgname = 'profiles_set_updated_at') then
    create trigger profiles_set_updated_at before update on public.profiles
    for each row execute function public.set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'projects_set_updated_at') then
    create trigger projects_set_updated_at before update on public.projects
    for each row execute function public.set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'chats_set_updated_at') then
    create trigger chats_set_updated_at before update on public.chats
    for each row execute function public.set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'documents_set_updated_at') then
    create trigger documents_set_updated_at before update on public.documents
    for each row execute function public.set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'change_plans_set_updated_at') then
    create trigger change_plans_set_updated_at before update on public.change_plans
    for each row execute function public.set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'test_suites_set_updated_at') then
    create trigger test_suites_set_updated_at before update on public.test_suites
    for each row execute function public.set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'test_cases_set_updated_at') then
    create trigger test_cases_set_updated_at before update on public.test_cases
    for each row execute function public.set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'user_settings_set_updated_at') then
    create trigger user_settings_set_updated_at before update on public.user_settings
    for each row execute function public.set_updated_at();
  end if;
end
$$;

alter table public.profiles enable row level security;
alter table public.projects enable row level security;
alter table public.chats enable row level security;
alter table public.chat_messages enable row level security;
alter table public.documents enable row level security;
alter table public.change_plans enable row level security;
alter table public.test_suites enable row level security;
alter table public.test_cases enable row level security;
alter table public.test_runs enable row level security;
alter table public.reports enable row level security;
alter table public.user_settings enable row level security;

do $$
begin
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'profiles' and policyname = 'profiles_select_own') then
    create policy profiles_select_own on public.profiles for select using (id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'profiles' and policyname = 'profiles_insert_own') then
    create policy profiles_insert_own on public.profiles for insert with check (id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'profiles' and policyname = 'profiles_update_own') then
    create policy profiles_update_own on public.profiles for update using (id = auth.uid()) with check (id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'projects' and policyname = 'projects_all_own') then
    create policy projects_all_own on public.projects for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'chats' and policyname = 'chats_all_own') then
    create policy chats_all_own on public.chats for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'chat_messages' and policyname = 'chat_messages_all_own') then
    create policy chat_messages_all_own on public.chat_messages for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'documents' and policyname = 'documents_all_own') then
    create policy documents_all_own on public.documents for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'change_plans' and policyname = 'change_plans_all_own') then
    create policy change_plans_all_own on public.change_plans for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'test_suites' and policyname = 'test_suites_all_own') then
    create policy test_suites_all_own on public.test_suites for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'test_cases' and policyname = 'test_cases_all_own') then
    create policy test_cases_all_own on public.test_cases for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'test_runs' and policyname = 'test_runs_all_own') then
    create policy test_runs_all_own on public.test_runs for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'reports' and policyname = 'reports_all_own') then
    create policy reports_all_own on public.reports for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'user_settings' and policyname = 'user_settings_all_own') then
    create policy user_settings_all_own on public.user_settings for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
end
$$;
