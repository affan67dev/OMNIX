create table if not exists public.post_moderation (
  post_id uuid primary key references public.posts(id) on delete cascade,
  status text not null check (status in ('pending', 'approved', 'rejected')),
  approved_by text,
  approved_at timestamptz,
  updated_at timestamptz not null default now()
);

alter table public.post_moderation enable row level security;

create index if not exists post_moderation_status_idx
  on public.post_moderation(status, updated_at desc);
