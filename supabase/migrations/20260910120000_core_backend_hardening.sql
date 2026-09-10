-- OMNIX core backend hardening migration
-- Identity is Supabase auth.users. Backend uses service-role only for server-side persistence.

create extension if not exists pgcrypto;

create table if not exists public.auth_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  token_jti text not null unique,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz,
  ip_address inet,
  user_agent text
);
create index if not exists auth_sessions_user_idx on public.auth_sessions(user_id);
create index if not exists auth_sessions_active_idx on public.auth_sessions(user_id, expires_at) where revoked_at is null;

create table if not exists public.phone_otp_challenges (
  id uuid primary key default gen_random_uuid(),
  phone_e164 text not null,
  otp_hash text not null,
  purpose text not null default 'signup' check (purpose in ('signup','login','password_reset')),
  attempts smallint not null default 0 check (attempts >= 0 and attempts <= 10),
  max_attempts smallint not null default 5,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  created_at timestamptz not null default now(),
  requested_ip inet,
  user_id uuid references auth.users(id) on delete cascade
);
create index if not exists otp_phone_active_idx on public.phone_otp_challenges(phone_e164, purpose, created_at desc);
create index if not exists otp_expiry_idx on public.phone_otp_challenges(expires_at);

create table if not exists public.subscriptions (
  user_id uuid primary key references auth.users(id) on delete cascade,
  product_id text,
  purchase_token text unique,
  order_id text,
  status text not null default 'free' check (status in ('free','pending','active','cancelled','expired','paused','payment_issue','failed')),
  is_premium boolean not null default false,
  expiry_at timestamptz,
  renews_at timestamptz,
  cancel_at_period_end boolean not null default false,
  last_verified_at timestamptz,
  provider_payload jsonb,
  updated_at timestamptz not null default now()
);
create index if not exists subscriptions_status_idx on public.subscriptions(status, expiry_at);

create table if not exists public.purchase_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  product_id text not null,
  purchase_token text not null,
  order_id text,
  status text not null,
  verified_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb
);
create index if not exists purchase_events_user_idx on public.purchase_events(user_id, verified_at desc);
create unique index if not exists purchase_events_token_idx on public.purchase_events(purchase_token, status);

create table if not exists public.zk_key_bundles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  device_id text not null,
  algorithm text not null,
  identity_public_key text not null,
  prekey_public_key text not null,
  prekey_key_id text not null,
  updated_at timestamptz not null default now(),
  unique(user_id, device_id)
);
create index if not exists zk_key_bundles_user_idx on public.zk_key_bundles(user_id);

create table if not exists public.encrypted_vaults (
  user_id uuid primary key references auth.users(id) on delete cascade,
  encrypted_vault text not null,
  vault_nonce text not null,
  vault_salt text not null,
  vault_version integer not null check (vault_version > 0),
  recovery_hint text not null,
  updated_at timestamptz not null default now()
);

create table if not exists public.push_devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  fcm_token text not null,
  platform text not null check (platform in ('android','ios','web')),
  device_id text not null,
  app_version text,
  registered_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  unique(user_id, device_id),
  unique(fcm_token)
);
create index if not exists push_devices_user_idx on public.push_devices(user_id);

create table if not exists public.push_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  event_type text not null,
  status text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists push_events_user_idx on public.push_events(user_id, created_at desc);

-- Keep the existing profile table but tighten its direct client access.
-- Public profile data should be exposed through an intentionally limited view, not the raw row.
drop policy if exists "Users can view public profiles" on public.profiles;
drop policy if exists "Users can update own profile" on public.profiles;
drop policy if exists "Users can insert own profile" on public.profiles;

create policy "profiles_select_own" on public.profiles
  for select to authenticated using (auth.uid() = user_id);
create policy "profiles_insert_own" on public.profiles
  for insert to authenticated with check (auth.uid() = user_id);
create policy "profiles_update_own" on public.profiles
  for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

create or replace view public.public_profiles
with (security_invoker = true)
as
select id, user_id, username, full_name, bio, profile_pic_url, cover_pic_url,
       is_private, is_blocked_from_search, omni_score, followers_count,
       following_count, posts_count, streak, created_at, updated_at
from public.profiles
where is_blocked_from_search = false;

grant select on public.public_profiles to anon, authenticated;

alter table public.auth_sessions enable row level security;
alter table public.phone_otp_challenges enable row level security;
alter table public.subscriptions enable row level security;
alter table public.purchase_events enable row level security;
alter table public.zk_key_bundles enable row level security;
alter table public.encrypted_vaults enable row level security;
alter table public.push_devices enable row level security;
alter table public.push_events enable row level security;

create policy "sessions_own" on public.auth_sessions for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "otp_own" on public.phone_otp_challenges for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "subscriptions_own" on public.subscriptions for select to authenticated
  using (auth.uid() = user_id);
create policy "purchase_events_own" on public.purchase_events for select to authenticated
  using (auth.uid() = user_id);
create policy "zk_keys_public_read" on public.zk_key_bundles for select to authenticated using (true);
create policy "zk_keys_own_write" on public.zk_key_bundles for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "vault_own" on public.encrypted_vaults for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "push_devices_own" on public.push_devices for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "push_events_own" on public.push_events for select to authenticated
  using (auth.uid() = user_id);

-- Never expose raw OTP hashes or vault/key data to anonymous clients.
revoke all on public.auth_sessions from anon;
revoke all on public.phone_otp_challenges from anon;
revoke all on public.subscriptions from anon;
revoke all on public.purchase_events from anon;
revoke all on public.zk_key_bundles from anon;
revoke all on public.encrypted_vaults from anon;
revoke all on public.push_devices from anon;
revoke all on public.push_events from anon;
