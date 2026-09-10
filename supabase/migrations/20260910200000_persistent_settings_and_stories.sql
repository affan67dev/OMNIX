-- Persistent settings/legacy-state elimination.
-- All user-owned rows are keyed by auth.users(id) and protected with RLS.
create extension if not exists pgcrypto;

create table if not exists public.user_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  account jsonb not null default '{}'::jsonb,
  security jsonb not null default '{}'::jsonb,
  content_preferences jsonb not null default '{}'::jsonb,
  story_settings jsonb not null default '{}'::jsonb,
  storage_settings jsonb not null default '{}'::jsonb,
  notification_settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.settings_password_resets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  channel text not null check (channel in ('email','sms')),
  destination text not null,
  otp_hash text not null,
  expires_at timestamptz not null,
  attempts smallint not null default 0 check (attempts between 0 and 10),
  verified_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists settings_password_resets_user_idx on public.settings_password_resets(user_id, created_at desc);

create table if not exists public.settings_2fa_challenges (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  method text not null check (method in ('sms','totp')),
  secret_ciphertext text,
  verification_hash text,
  expires_at timestamptz not null default (now() + interval '10 minutes'),
  verified_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists settings_2fa_challenges_user_idx on public.settings_2fa_challenges(user_id, created_at desc);

create table if not exists public.data_export_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  status text not null default 'queued' check (status in ('queued','ready','failed','expired')),
  scope jsonb not null default '{}'::jsonb,
  download_path text,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);
create index if not exists data_export_requests_user_idx on public.data_export_requests(user_id, created_at desc);

create table if not exists public.archived_content (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  content_type text not null check (content_type in ('post','story')),
  title text,
  payload jsonb not null default '{}'::jsonb,
  archived_at timestamptz not null default now()
);
create index if not exists archived_content_user_idx on public.archived_content(user_id, content_type, archived_at desc);

create table if not exists public.stories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  media_name text not null,
  media_type text not null default 'image',
  caption text default '',
  mentions jsonb not null default '[]'::jsonb,
  location_name text default '',
  music_track text default '',
  overlay_text text default '',
  overlay_emoji text default '',
  overlay_x numeric default 0.5,
  overlay_y numeric default 0.5,
  overlay_scale numeric default 1.0,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  deleted_at timestamptz
);
create index if not exists stories_user_active_idx on public.stories(user_id, expires_at desc) where deleted_at is null;

alter table public.user_settings enable row level security;
alter table public.settings_password_resets enable row level security;
alter table public.settings_2fa_challenges enable row level security;
alter table public.data_export_requests enable row level security;
alter table public.archived_content enable row level security;
alter table public.stories enable row level security;

create policy user_settings_own on public.user_settings for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy password_resets_own on public.settings_password_resets for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy twofa_challenges_own on public.settings_2fa_challenges for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy exports_own on public.data_export_requests for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy archive_own on public.archived_content for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy stories_own on public.stories for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

revoke all on public.settings_password_resets from anon;
revoke all on public.settings_2fa_challenges from anon;
