-- ============================================================================
-- MIGRATION 1: Scans table (for scan history)
-- Run this in Supabase SQL Editor
-- ============================================================================

create table public.scans (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade,
  system_prompt_preview text not null,
  summary jsonb not null,
  results jsonb not null,
  fixes text,
  preventive_recommendations text,
  total_issues int not null default 0,
  created_at timestamptz default now()
);

create index scans_user_id_idx on public.scans(user_id);
create index scans_created_at_idx on public.scans(created_at desc);

alter table public.scans enable row level security;

create policy "Users can read own scans"
  on public.scans for select
  using (auth.uid() = user_id);

create policy "Service role can insert scans"
  on public.scans for insert
  with check (true);


-- ============================================================================
-- MIGRATION 2: API Keys table (for CI/CD integration)
-- Run this in Supabase SQL Editor
-- ============================================================================

create table public.api_keys (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  key_hash text not null,
  key_prefix text not null,
  name text not null default 'Default',
  created_at timestamptz default now(),
  last_used_at timestamptz,
  is_active boolean default true
);

create index api_keys_key_hash_idx on public.api_keys(key_hash);
create index api_keys_user_id_idx on public.api_keys(user_id);

alter table public.api_keys enable row level security;

create policy "Users can read own keys"
  on public.api_keys for select
  using (auth.uid() = user_id);

create policy "Users can insert own keys"
  on public.api_keys for insert
  with check (auth.uid() = user_id);

create policy "Users can update own keys"
  on public.api_keys for update
  using (auth.uid() = user_id);

create policy "Service role full access on api_keys"
  on public.api_keys for all
  using (true)
  with check (true);


-- ============================================================================
-- MIGRATION 3: Add full system_prompt column to scans table
-- Run this in Supabase SQL Editor
-- ============================================================================

alter table public.scans add column system_prompt text;
