-- Supabase media storage and persistent story-view state.
-- Service-role uploads are performed only by the server; client-side privileged keys are forbidden.

create extension if not exists pgcrypto;

create table if not exists public.story_views (
  id uuid primary key default gen_random_uuid(),
  story_id uuid not null references public.stories(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  viewed_at timestamptz not null default now(),
  unique (story_id, user_id)
);
create index if not exists story_views_story_idx on public.story_views(story_id, viewed_at desc);
create index if not exists story_views_user_idx on public.story_views(user_id, viewed_at desc);

alter table public.story_views enable row level security;
create policy story_views_insert_own on public.story_views for insert to authenticated
  with check (auth.uid() = user_id);
create policy story_views_read_own on public.story_views for select to authenticated
  using (auth.uid() = user_id);

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('stories', 'stories', false, 26214400, array['image/jpeg','image/png','image/webp','image/gif','video/mp4','video/webm']),
  ('posts', 'posts', false, 26214400, array['image/jpeg','image/png','image/webp','image/gif','video/mp4','video/webm']),
  ('reels', 'reels', false, 104857600, array['video/mp4','video/webm','video/quicktime'])
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- Direct client access is limited to objects under the authenticated user's own UUID prefix.
create policy storage_insert_own_media on storage.objects for insert to authenticated
  with check (
    bucket_id in ('stories','posts','reels')
    and (storage.foldername(name))[1] = auth.uid()::text
  );
create policy storage_select_own_media on storage.objects for select to authenticated
  using (
    bucket_id in ('stories','posts','reels')
    and (storage.foldername(name))[1] = auth.uid()::text
  );
create policy storage_delete_own_media on storage.objects for delete to authenticated
  using (
    bucket_id in ('stories','posts','reels')
    and (storage.foldername(name))[1] = auth.uid()::text
  );
