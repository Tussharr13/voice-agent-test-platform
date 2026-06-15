-- Add visible app-facing IDs to normalized QA tables.
-- Safe to run repeatedly in Supabase SQL Editor.

alter table public.test_suites
  add column if not exists app_suite_id text;

alter table public.test_cases
  add column if not exists app_case_id text,
  add column if not exists app_suite_id text;

alter table public.test_runs
  add column if not exists app_run_id text,
  add column if not exists app_suite_id text,
  add column if not exists app_report_id text;

alter table public.reports
  add column if not exists app_report_id text,
  add column if not exists app_run_id text,
  add column if not exists app_suite_id text;

create index if not exists test_suites_app_suite_id_idx on public.test_suites(app_suite_id);
create index if not exists test_cases_app_case_id_idx on public.test_cases(app_case_id);
create index if not exists test_runs_app_run_id_idx on public.test_runs(app_run_id);
create index if not exists test_runs_app_report_id_idx on public.test_runs(app_report_id);
create index if not exists reports_app_report_id_idx on public.reports(app_report_id);
create index if not exists reports_app_run_id_idx on public.reports(app_run_id);
