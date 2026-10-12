-- Intelligence, trust, scoring and founding-member state are server-owned.
-- No browser role needs direct table access; API writes use the service_role key on the server only.
do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'omnix_events',
    'omnix_user_intelligence',
    'omnix_trust_signals',
    'omnix_score_snapshots',
    'omnix_streak_state',
    'omnix_og_health',
    'omnix_decision_log',
    'omnix_founding_counter'
  ]
  loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format('revoke all on table public.%I from anon, authenticated', table_name);
    execute format('grant all on table public.%I to service_role', table_name);
  end loop;
end
$$;
