-- OMNIX Intelligence Core + Trust/Reputation + OG health foundation.
-- Deliberately separate recommendation state from reputation/entitlements.

create table if not exists public.omnix_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  event_type text not null,
  object_id text,
  surface text,
  occurred_at timestamptz not null default now(),
  session_id text,
  duration_ms integer,
  value double precision,
  idempotency_key text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint omnix_events_type_chk check (event_type in (
    'view','watch','completion','rewatch','like','comment','save','share','follow','unfollow',
    'search','skip','hide','not_interested','mute','block','report','story_view','reel_view',
    'chat_interaction','notification_interaction','create','session_start'
  )),
  constraint omnix_events_duration_chk check (duration_ms is null or (duration_ms >= 0 and duration_ms <= 86400000)),
  constraint omnix_events_idempotency_chk check (idempotency_key is null or length(idempotency_key) <= 200)
);

create unique index if not exists omnix_events_user_idempotency_uq
  on public.omnix_events(user_id, idempotency_key) where idempotency_key is not null;
create index if not exists omnix_events_user_time_idx on public.omnix_events(user_id, occurred_at desc);
create index if not exists omnix_events_surface_time_idx on public.omnix_events(surface, occurred_at desc);
create index if not exists omnix_events_object_time_idx on public.omnix_events(object_id, occurred_at desc) where object_id is not null;

create table if not exists public.omnix_user_intelligence (
  user_id uuid primary key,
  short_topics jsonb not null default '{}'::jsonb,
  long_topics jsonb not null default '{}'::jsonb,
  format_affinity jsonb not null default '{}'::jsonb,
  creator_affinity jsonb not null default '{}'::jsonb,
  relationship_affinity jsonb not null default '{}'::jsonb,
  recent_negative jsonb not null default '{}'::jsonb,
  session_intent jsonb not null default '{}'::jsonb,
  feature_version text not null default 'v1',
  updated_at timestamptz not null default now()
);

create table if not exists public.omnix_trust_signals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  risk_score double precision not null default 0 check (risk_score between 0 and 1),
  state text not null default 'normal' check (state in ('normal','suspicious','review','confirmed')),
  reasons jsonb not null default '[]'::jsonb,
  persistence_score double precision not null default 0 check (persistence_score between 0 and 1),
  corroboration_score double precision not null default 0 check (corroboration_score between 0 and 1),
  confirmed_abuse boolean not null default false,
  observed_at timestamptz not null default now()
);
create index if not exists omnix_trust_user_time_idx on public.omnix_trust_signals(user_id, observed_at desc);
create index if not exists omnix_trust_state_idx on public.omnix_trust_signals(state, observed_at desc);

create table if not exists public.omnix_score_snapshots (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  score double precision not null check (score between 0 and 100),
  dimensions jsonb not null default '{}'::jsonb,
  reason_codes jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists omnix_score_user_time_idx on public.omnix_score_snapshots(user_id, created_at desc);

create table if not exists public.omnix_streak_state (
  user_id uuid primary key,
  current_streak integer not null default 0 check (current_streak >= 0),
  best_streak integer not null default 0 check (best_streak >= 0),
  last_meaningful_at timestamptz,
  freeze_count integer not null default 0 check (freeze_count >= 0),
  integrity_blocked boolean not null default false,
  updated_at timestamptz not null default now()
);

create table if not exists public.omnix_og_health (
  user_id uuid primary key,
  health_score double precision not null default 100 check (health_score between 0 and 100),
  state text not null default 'green' check (state in ('green','yellow','red_grace','red_suspended')),
  dimensions jsonb not null default '{}'::jsonb,
  reason_codes jsonb not null default '[]'::jsonb,
  grace_started_at timestamptz,
  grace_until timestamptz,
  next_evaluation_at timestamptz,
  has_blue_tick boolean not null default false,
  premium_plus boolean not null default false,
  updated_at timestamptz not null default now()
);
create index if not exists omnix_og_state_eval_idx on public.omnix_og_health(state, next_evaluation_at);

create table if not exists public.omnix_decision_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  surface text,
  decision_type text not null,
  decision jsonb not null default '{}'::jsonb,
  reason_codes jsonb not null default '[]'::jsonb,
  model_version text not null default 'rule-v1',
  latency_ms integer,
  created_at timestamptz not null default now()
);
create index if not exists omnix_decision_user_time_idx on public.omnix_decision_log(user_id, created_at desc);
create index if not exists omnix_decision_type_time_idx on public.omnix_decision_log(decision_type, created_at desc);

-- Historical founding identity is independent from current benefits.
alter table public.profiles add column if not exists is_og_member boolean not null default false;
alter table public.profiles add column if not exists founding_member_number integer;
alter table public.profiles add column if not exists has_blue_tick boolean not null default false;
alter table public.profiles add column if not exists premium_plus boolean not null default false;
alter table public.profiles add column if not exists og_health_score double precision not null default 100;
create unique index if not exists profiles_founding_member_number_uq on public.profiles(founding_member_number) where founding_member_number is not null;

create table if not exists public.omnix_founding_counter (
  singleton boolean primary key default true check (singleton),
  allocated integer not null default 0 check (allocated between 0 and 1000)
);
insert into public.omnix_founding_counter(singleton, allocated)
values (true, 0)
on conflict (singleton) do nothing;

-- Atomic first-1000 allocator. Historical OG identity is never removed by health evaluation.
create or replace function public.claim_omnix_founding_member(p_user_id uuid)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_slot integer;
begin
  perform 1 from public.omnix_founding_counter where singleton = true for update;
  if exists (select 1 from public.profiles where user_id = p_user_id and is_og_member) then
    return (select founding_member_number from public.profiles where user_id = p_user_id);
  end if;
  select allocated + 1 into v_slot from public.omnix_founding_counter where singleton = true;
  if v_slot > 1000 then
    return null;
  end if;
  update public.omnix_founding_counter set allocated = v_slot where singleton = true;
  update public.profiles
     set is_og_member = true, founding_member_number = v_slot
   where user_id = p_user_id and not is_og_member;
  if not found then
    raise exception 'profile_not_found_or_already_assigned';
  end if;
  return v_slot;
end;
$$;

revoke all on function public.claim_omnix_founding_member(uuid) from public;

-- Never let health updates clear historical identity. Benefit changes are explicit.
create or replace function public.apply_omnix_og_benefits(p_user_id uuid, p_score double precision, p_compliant boolean)
returns public.omnix_og_health
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.omnix_og_health;
  v_state text;
  v_grace_started timestamptz;
  v_grace_until timestamptz;
  v_blue boolean;
  v_premium boolean;
begin
  if not exists (select 1 from public.profiles where user_id = p_user_id and is_og_member) then
    raise exception 'not_a_founding_member';
  end if;
  if not p_compliant then
    v_state := 'red_suspended'; v_blue := false; v_premium := false;
  elsif p_score >= 80 then
    v_state := 'green'; v_blue := true; v_premium := true;
  elsif p_score >= 50 then
    v_state := 'yellow'; v_blue := true; v_premium := true;
  else
    select grace_started_at, grace_until into v_grace_started, v_grace_until from public.omnix_og_health where user_id = p_user_id;
    if v_grace_started is null then
      v_grace_started := now(); v_grace_until := now() + interval '7 days';
    end if;
    if now() < v_grace_until then
      v_state := 'red_grace'; v_blue := true; v_premium := true;
    else
      v_state := 'red_suspended'; v_blue := false; v_premium := false;
    end if;
  end if;
  insert into public.omnix_og_health(user_id, health_score, state, grace_started_at, grace_until, next_evaluation_at, has_blue_tick, premium_plus, reason_codes)
  values (p_user_id, greatest(0, least(100, p_score)), v_state, v_grace_started, v_grace_until, now() + interval '1 day', v_blue, v_premium, jsonb_build_array(v_state))
  on conflict (user_id) do update set
    health_score = excluded.health_score, state = excluded.state,
    grace_started_at = excluded.grace_started_at, grace_until = excluded.grace_until,
    next_evaluation_at = excluded.next_evaluation_at, has_blue_tick = excluded.has_blue_tick,
    premium_plus = excluded.premium_plus, reason_codes = excluded.reason_codes, updated_at = now()
  returning * into v_row;
  update public.profiles set has_blue_tick = v_blue, premium_plus = v_premium, og_health_score = v_row.health_score where user_id = p_user_id;
  return v_row;
end;
$$;
revoke all on function public.apply_omnix_og_benefits(uuid, double precision, boolean) from public;
