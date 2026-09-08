-- =========================================================
-- Migration: Harden posts RLS and add missing policies
-- Fix: posts table was missing UPDATE and DELETE policies
-- =========================================================

-- Ensure RLS is enabled (idempotent)
ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;

-- Drop duplicate/weak policies if they exist from earlier migrations
DROP POLICY IF EXISTS "Allow public read access to posts" ON public.posts;
DROP POLICY IF EXISTS "Allow authenticated users to insert posts" ON public.posts;

-- Recreate with explicit names
CREATE POLICY "posts_select_public"
    ON public.posts FOR SELECT
    USING (true);

CREATE POLICY "posts_insert_authenticated"
    ON public.posts FOR INSERT
    WITH CHECK (auth.uid() = user_id AND auth.role() = 'authenticated');

CREATE POLICY "posts_update_owner"
    ON public.posts FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "posts_delete_owner"
    ON public.posts FOR DELETE
    USING (auth.uid() = user_id);

-- Also ensure profiles table has correct DELETE policy
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view public profiles" ON public.profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles;
DROP POLICY IF EXISTS "Users can insert own profile" ON public.profiles;

CREATE POLICY "profiles_select_public"
    ON public.profiles FOR SELECT
    USING (true);

CREATE POLICY "profiles_insert_own"
    ON public.profiles FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "profiles_update_own"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "profiles_delete_own"
    ON public.profiles FOR DELETE
    USING (auth.uid() = user_id);
