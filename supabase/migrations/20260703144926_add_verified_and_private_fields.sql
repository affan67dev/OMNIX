-- These fields belong to OMNIX profiles; auth.users remains the Supabase identity source.
ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS is_private BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN public.profiles.is_verified IS 'True when the profile has a verified badge';
COMMENT ON COLUMN public.profiles.is_private IS 'True when profile discovery is restricted to accepted followers';
