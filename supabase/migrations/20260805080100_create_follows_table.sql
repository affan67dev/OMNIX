-- =========================================================
-- Migration: Create follows table with RLS
-- Tracks follow relationships between users
-- =========================================================

CREATE TABLE IF NOT EXISTS public.follows (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    follower_id  UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    following_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'pending', 'blocked')),
    created_at   TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE (follower_id, following_id)
);

CREATE INDEX IF NOT EXISTS follows_follower_idx  ON public.follows (follower_id);
CREATE INDEX IF NOT EXISTS follows_following_idx ON public.follows (following_id);

ALTER TABLE public.follows ENABLE ROW LEVEL SECURITY;

-- Anyone authenticated can view follows (needed for follower/following counts on public profiles)
CREATE POLICY "Authenticated users can view follows"
    ON public.follows FOR SELECT
    USING (auth.role() = 'authenticated');

-- Users can follow others (insert their own follow rows)
CREATE POLICY "Users can follow others"
    ON public.follows FOR INSERT
    WITH CHECK (auth.uid() = follower_id);

-- Users can update their own follow rows (e.g. accept/decline pending)
CREATE POLICY "Users can manage their own follows"
    ON public.follows FOR UPDATE
    USING (auth.uid() = follower_id OR auth.uid() = following_id);

-- Users can unfollow (delete their own follow rows)
CREATE POLICY "Users can unfollow"
    ON public.follows FOR DELETE
    USING (auth.uid() = follower_id);
