-- Optional migration for projects created before Analyzer goal-brief support.
-- Safe to run in the Supabase SQL editor.

alter table public.projects
  add column if not exists goal_test_brief jsonb not null default '{}'::jsonb,
  add column if not exists goal_test_briefs jsonb not null default '[]'::jsonb;
