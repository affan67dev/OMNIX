-- Real Reels persistence and engagement. No mock/demo rows are inserted.
create table if not exists public.reels (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  video_url text not null,
  caption text not null default '',
  duration numeric,
  view_count bigint not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists reels_created_idx on public.reels(created_at desc);
create index if not exists reels_user_created_idx on public.reels(user_id, created_at desc);

alter table public.reels enable row level security;
drop policy if exists reels_read_authenticated on public.reels;
drop policy if exists reels_insert_own on public.reels;
drop policy if exists reels_update_own on public.reels;
drop policy if exists reels_delete_own on public.reels;
create policy reels_read_authenticated on public.reels for select to authenticated using (true);
create policy reels_insert_own on public.reels for insert to authenticated with check (auth.uid() = user_id);
create policy reels_update_own on public.reels for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy reels_delete_own on public.reels for delete to authenticated using (auth.uid() = user_id);

create or replace function public.increment_reel_view(target_reel_id uuid)
returns void
language sql
security invoker
set search_path = public
as $$
  update public.reels set view_count = view_count + 1 where id = target_reel_id;
$$;
revoke all on function public.increment_reel_view(uuid) from public;
grant execute on function public.increment_reel_view(uuid) to authenticated;
