-- Study_Gateway AI: run this ONCE in Supabase -> SQL Editor -> New query -> Run.
-- It creates the tables, turns on Row Level Security (RLS) and makes the PDF bucket private.

-- 1. Tables -----------------------------------------------------------------
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  display_name text,
  role text not null default 'student' check (role in ('student','admin')),
  session_epoch text not null default replace(gen_random_uuid()::text,'-',''),
  focus_minutes integer not null default 0 check (focus_minutes >= 0),
  sessions integer not null default 0 check (sessions >= 0),
  created_at timestamptz not null default now()
);

create table if not exists public.tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (char_length(title) between 1 and 200),
  subject text not null default 'General' check (char_length(subject) between 1 and 80),
  done boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists tasks_user_id_idx on public.tasks(user_id);

-- Reserved for the future AI Creator history (nothing writes here yet).
create table if not exists public.ai_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  prompt text not null,
  output text,
  created_at timestamptz not null default now()
);
create index if not exists ai_history_user_id_idx on public.ai_history(user_id);

create table if not exists public.books (
  id bigint generated always as identity primary key,
  title text not null,
  class_name text not null check (class_name in ('Class 9','Class 10','Class 11','Class 12','Other')),
  subject text not null,
  description text not null default '',
  storage_path text not null unique check (storage_path ~ '^books/[0-9a-f]{32}\.pdf$'),
  original_filename text,
  created_at timestamptz not null default now()
);

-- 2. Row Level Security ---------------------------------------------------------
alter table public.profiles   enable row level security;
alter table public.tasks      enable row level security;
alter table public.ai_history enable row level security;
alter table public.books      enable row level security;

-- Least privilege: the public (anon) and signed-in (authenticated) database roles get NOTHING.
-- Only your Flask server (service_role key, kept secret) can touch these tables.
revoke all on public.profiles, public.tasks, public.ai_history, public.books from anon, authenticated;

-- Safety net: if you ever grant access later, users can still only see their own rows.
create policy "own profile"  on public.profiles   for select to authenticated using (id = (select auth.uid()));
create policy "own tasks"    on public.tasks      for all    to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "own history"  on public.ai_history for all    to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- 3. Atomic counter used by the focus timer --------------------------------------
create or replace function public.add_focus(p_user uuid, p_minutes integer)
returns public.profiles language sql security invoker set search_path = public as $$
  update public.profiles
     set focus_minutes = focus_minutes + greatest(p_minutes, 0), sessions = sessions + 1
   where id = p_user
  returning *;
$$;
revoke execute on function public.add_focus(uuid, integer) from public, anon, authenticated;
grant  execute on function public.add_focus(uuid, integer) to service_role;

-- 4. Private storage bucket for PDFs ----------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('study-pdfs', 'study-pdfs', false, 20971520, array['application/pdf'])
on conflict (id) do update set public = false, file_size_limit = 20971520, allowed_mime_types = array['application/pdf'];
-- No policies on storage.objects = browsers cannot list/read/write files directly.
-- Downloads happen only through short-lived signed links created by the server.
