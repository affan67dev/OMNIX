-- OMNIX username integrity hardening
-- Usernames are normalized to lowercase by the API and uniquely enforced by PostgreSQL.
-- This migration intentionally fails if legacy data contains case-insensitive duplicates;
-- resolve those records explicitly before production deployment rather than silently renaming users.

update public.profiles
set username = lower(trim(username))
where username is not null
  and username <> lower(trim(username));

do $$
declare
  duplicate_count integer;
begin
  select count(*) into duplicate_count
  from (
    select lower(trim(username)) as normalized_username
    from public.profiles
    where username is not null
    group by lower(trim(username))
    having count(*) > 1
  ) duplicates;

  if duplicate_count > 0 then
    raise exception 'OMNIX username migration blocked: % case-insensitive duplicate username group(s) exist', duplicate_count;
  end if;
end $$;

create unique index if not exists profiles_username_ci_unique
  on public.profiles (lower(trim(username)))
  where username is not null;

alter table public.profiles
  drop constraint if exists profiles_username_format_check;

alter table public.profiles
  add constraint profiles_username_format_check
  check (username is null or username ~ '^[a-z0-9_]{3,30}$');

create index if not exists profiles_username_lookup_idx
  on public.profiles (lower(username));
