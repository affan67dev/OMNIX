-- OMNIX social graph + engagement foundation
create extension if not exists pgcrypto;

create table if not exists public.follows (
  follower_id uuid not null references auth.users(id) on delete cascade,
  following_id uuid not null references auth.users(id) on delete cascade,
  status text not null default 'accepted' check (status in ('pending','accepted')),
  created_at timestamptz not null default now(),
  primary key (follower_id, following_id),
  check (follower_id <> following_id)
);
create index if not exists follows_following_idx on public.follows(following_id, created_at desc);

create table if not exists public.blocks (
  blocker_id uuid not null references auth.users(id) on delete cascade,
  blocked_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (blocker_id, blocked_id),
  check (blocker_id <> blocked_id)
);

create table if not exists public.mutes (
  muter_id uuid not null references auth.users(id) on delete cascade,
  muted_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (muter_id, muted_id),
  check (muter_id <> muted_id)
);

create table if not exists public.content_reports (
  id uuid primary key default gen_random_uuid(),
  reporter_id uuid not null references auth.users(id) on delete cascade,
  post_id uuid references public.posts(id) on delete cascade,
  reported_user_id uuid references auth.users(id) on delete cascade,
  reason text not null,
  details text,
  status text not null default 'open' check (status in ('open','reviewing','resolved','dismissed')),
  created_at timestamptz not null default now(),
  check (post_id is not null or reported_user_id is not null)
);
create index if not exists reports_post_idx on public.content_reports(post_id, created_at desc);
create index if not exists reports_user_idx on public.content_reports(reported_user_id, created_at desc);

create table if not exists public.post_likes (
  post_id uuid not null references public.posts(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);
create index if not exists post_likes_user_idx on public.post_likes(user_id, created_at desc);

create table if not exists public.post_comments (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references public.posts(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  parent_comment_id uuid references public.post_comments(id) on delete cascade,
  content text not null check (length(trim(content)) between 1 and 2000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists post_comments_post_idx on public.post_comments(post_id, created_at desc);

create table if not exists public.post_shares (
  post_id uuid not null references public.posts(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);

create table if not exists public.post_bookmarks (
  post_id uuid not null references public.posts(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);

create table if not exists public.post_views (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references public.posts(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  session_id text,
  watch_ms bigint not null default 0 check (watch_ms >= 0),
  created_at timestamptz not null default now()
);
create index if not exists post_views_feed_idx on public.post_views(post_id, created_at desc);

create table if not exists public.feed_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  post_id uuid references public.posts(id) on delete cascade,
  event_type text not null check (event_type in ('impression','click','like','comment','share','bookmark','view','watch')),
  value numeric,
  session_id text,
  created_at timestamptz not null default now()
);
create index if not exists feed_events_user_time_idx on public.feed_events(user_id, created_at desc);
create index if not exists feed_events_post_time_idx on public.feed_events(post_id, created_at desc);

alter table public.follows enable row level security;
alter table public.blocks enable row level security;
alter table public.mutes enable row level security;
alter table public.content_reports enable row level security;
alter table public.post_likes enable row level security;
alter table public.post_comments enable row level security;
alter table public.post_shares enable row level security;
alter table public.post_bookmarks enable row level security;
alter table public.post_views enable row level security;
alter table public.feed_events enable row level security;

create policy follows_read on public.follows for select to authenticated using (auth.uid() = follower_id or auth.uid() = following_id);
create policy follows_write on public.follows for all to authenticated using (auth.uid() = follower_id) with check (auth.uid() = follower_id);
create policy blocks_own on public.blocks for all to authenticated using (auth.uid() = blocker_id) with check (auth.uid() = blocker_id);
create policy mutes_own on public.mutes for all to authenticated using (auth.uid() = muter_id) with check (auth.uid() = muter_id);
create policy reports_own_insert on public.content_reports for insert to authenticated with check (auth.uid() = reporter_id);
create policy reports_own_read on public.content_reports for select to authenticated using (auth.uid() = reporter_id);
create policy likes_read on public.post_likes for select to authenticated using (true);
create policy likes_own_write on public.post_likes for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy comments_read on public.post_comments for select to authenticated using (true);
create policy comments_own_write on public.post_comments for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy shares_read on public.post_shares for select to authenticated using (true);
create policy shares_own_write on public.post_shares for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy bookmarks_own on public.post_bookmarks for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy views_own_insert on public.post_views for insert to authenticated with check (auth.uid() = user_id);
create policy views_own_read on public.post_views for select to authenticated using (auth.uid() = user_id);
create policy feed_events_own_insert on public.feed_events for insert to authenticated with check (auth.uid() = user_id);
create policy feed_events_own_read on public.feed_events for select to authenticated using (auth.uid() = user_id);
