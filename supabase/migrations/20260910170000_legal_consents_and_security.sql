-- OMNIX legal-consent audit trail and stricter server-owned tables.
create table if not exists public.legal_consents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  document_type text not null check (document_type in ('terms','privacy')),
  document_version text not null,
  accepted_at timestamptz not null default now(),
  source text not null default 'signup',
  unique(user_id, document_type, document_version)
);
create index if not exists legal_consents_user_idx on public.legal_consents(user_id, accepted_at desc);

alter table public.legal_consents enable row level security;
create policy "legal_consents_own_read" on public.legal_consents
  for select to authenticated using (auth.uid() = user_id);
create policy "legal_consents_own_insert" on public.legal_consents
  for insert to authenticated with check (auth.uid() = user_id);
revoke all on public.legal_consents from anon;

-- Server-side purchase/push records are never writable by browser clients.
revoke insert, update, delete on public.subscriptions from authenticated;
revoke insert, update, delete on public.purchase_events from authenticated;
revoke insert, update, delete on public.push_events from authenticated;

-- Token/JTI sessions are server-owned; clients only need their own read visibility.
revoke insert, update, delete on public.auth_sessions from authenticated;
revoke insert, update, delete on public.phone_otp_challenges from authenticated;
