-- Public profile discovery must use a restricted projection while the base table remains owner-only.
-- The view runs with its owner privileges so base-table RLS does not hide other public profiles;
-- every exposed column is intentionally non-secret and private/blocked profiles are filtered here.
create or replace view public.public_profiles
with (security_invoker = false, security_barrier = true)
as
select
  p.id,
  p.user_id,
  p.username,
  p.full_name,
  p.bio,
  p.profile_pic_url,
  p.cover_pic_url,
  p.is_private,
  p.is_blocked_from_search,
  p.omni_score,
  p.followers_count,
  p.following_count,
  p.posts_count,
  p.streak,
  p.created_at,
  p.updated_at
from public.profiles p
where coalesce(p.is_blocked_from_search, false) = false
  and (coalesce(p.is_private, false) = false or p.user_id = auth.uid());

revoke all on public.public_profiles from public;
grant select on public.public_profiles to anon, authenticated;
