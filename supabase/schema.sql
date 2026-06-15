-- Bot QA Workbench Supabase schema
--
-- Run this in the Supabase SQL editor before enabling Supabase persistence
-- in the app's .env file.

create table if not exists public.bot_qa_state (
  id text primary key,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists bot_qa_state_updated_at_idx
  on public.bot_qa_state (updated_at desc);

create or replace function public.set_bot_qa_state_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists bot_qa_state_set_updated_at on public.bot_qa_state;

create trigger bot_qa_state_set_updated_at
before update on public.bot_qa_state
for each row
execute function public.set_bot_qa_state_updated_at();

-- Keep browser/client access closed. The local Python backend should use the
-- Supabase service-role key from .env; never expose that key in frontend code.
alter table public.bot_qa_state enable row level security;

-- Create the default workspace row. The app will replace this empty JSON with
-- the current local state on first Supabase-backed save/load.
insert into public.bot_qa_state (id, data)
values ('default', '{}'::jsonb)
on conflict (id) do nothing;
