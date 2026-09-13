-- Beta feed performance + safe server-side visibility filtering.
-- The API uses the RPC with the service role, so the function itself enforces visibility.

alter table public.posts add column if not exists deleted_at timestamptz;

create index if not exists posts_feed_created_idx
  on public.posts (created_at desc, id desc)
  where deleted_at is null;

create index if not exists posts_user_created_idx
  on public.posts (user_id, created_at desc, id desc)
  where deleted_at is null;

create or replace function public.get_feed_posts(
  viewer_id uuid,
  page_limit integer default 20,
  page_offset integer default 0
)
returns setof public.posts
language sql
stable
security definer
set search_path = public
as $$
  select p.*
  from public.posts p
  where p.deleted_at is null
    and public.can_view_post(p.user_id, viewer_id, p.visibility)
  order by p.created_at desc, p.id desc
  limit least(greatest(coalesce(page_limit, 20), 1), 50)
  offset greatest(coalesce(page_offset, 0), 0);
$$;

revoke all on function public.get_feed_posts(uuid, integer, integer) from public;
grant execute on function public.get_feed_posts(uuid, integer, integer) to authenticated;
