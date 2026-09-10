-- Replace legacy permissive post policies with ownership and visibility enforcement.
-- SECURITY DEFINER is used only for this boolean authorization check and exposes no row data.
create or replace function public.can_view_post(target_user uuid, viewer uuid, post_visibility text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select
    viewer = target_user
    or post_visibility = 'public'
    or (
      post_visibility = 'followers'
      and exists (
        select 1 from public.follows f
        where f.follower_id = viewer
          and f.following_id = target_user
          and f.status = 'accepted'
      )
    )
    or (
      post_visibility is null
      and not exists (
        select 1 from public.profiles p
        where p.user_id = target_user and p.is_private = true
      )
    )
    or (
      post_visibility = 'private' and viewer = target_user
    )
    or (
      post_visibility <> 'public'
      and exists (
        select 1 from public.profiles p
        where p.user_id = target_user and p.is_private = false
      )
    );
$$;

revoke all on function public.can_view_post(uuid, uuid, text) from public;
grant execute on function public.can_view_post(uuid, uuid, text) to authenticated;

alter table public.posts add column if not exists visibility text not null default 'public';
alter table public.posts drop constraint if exists posts_visibility_check;
alter table public.posts add constraint posts_visibility_check check (visibility in ('public','followers','private'));

-- Drop historically permissive policies before recreating deterministic ones.
drop policy if exists "Allow public read access to posts" on public.posts;
drop policy if exists "Allow authenticated users to insert posts" on public.posts;
drop policy if exists posts_select_secure on public.posts;
drop policy if exists posts_insert_own on public.posts;
drop policy if exists posts_update_own on public.posts;
drop policy if exists posts_delete_own on public.posts;

create policy posts_select_secure on public.posts
  for select to authenticated
  using (public.can_view_post(user_id, auth.uid(), visibility));

create policy posts_insert_own on public.posts
  for insert to authenticated
  with check (auth.uid() = user_id);

create policy posts_update_own on public.posts
  for update to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy posts_delete_own on public.posts
  for delete to authenticated
  using (auth.uid() = user_id);

-- Engagement reads must not become a side-channel for inaccessible posts.
drop policy if exists likes_read on public.post_likes;
drop policy if exists comments_read on public.post_comments;
drop policy if exists shares_read on public.post_shares;

create policy likes_read on public.post_likes
  for select to authenticated
  using (exists (select 1 from public.posts p where p.id = post_likes.post_id and public.can_view_post(p.user_id, auth.uid(), p.visibility)));

create policy comments_read on public.post_comments
  for select to authenticated
  using (exists (select 1 from public.posts p where p.id = post_comments.post_id and public.can_view_post(p.user_id, auth.uid(), p.visibility)));

create policy shares_read on public.post_shares
  for select to authenticated
  using (exists (select 1 from public.posts p where p.id = post_shares.post_id and public.can_view_post(p.user_id, auth.uid(), p.visibility)));
