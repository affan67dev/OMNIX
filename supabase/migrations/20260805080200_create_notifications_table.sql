-- =========================================================
-- Migration: Create notifications table with RLS
-- Push and in-app notification records per user
-- =========================================================

CREATE TABLE IF NOT EXISTS public.notifications (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    type        TEXT NOT NULL CHECK (type IN (
                    'like', 'comment', 'follow', 'follow_request',
                    'message', 'mention', 'system'
                )),
    actor_id    UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    entity_type TEXT,          -- 'post', 'comment', 'message', etc.
    entity_id   UUID,
    body        TEXT,
    read_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS notifications_user_idx     ON public.notifications (user_id);
CREATE INDEX IF NOT EXISTS notifications_created_idx  ON public.notifications (created_at DESC);
CREATE INDEX IF NOT EXISTS notifications_unread_idx   ON public.notifications (user_id, read_at)
    WHERE read_at IS NULL;

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- Users can only see their own notifications
CREATE POLICY "Users can view own notifications"
    ON public.notifications FOR SELECT
    USING (auth.uid() = user_id);

-- Only backend (service role) inserts notifications; no direct user inserts
-- To allow this: ensure service-role key is used for inserts from backend
CREATE POLICY "Service role can insert notifications"
    ON public.notifications FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

-- Users can mark notifications as read
CREATE POLICY "Users can update own notifications"
    ON public.notifications FOR UPDATE
    USING (auth.uid() = user_id);

-- Users can delete their own notifications
CREATE POLICY "Users can delete own notifications"
    ON public.notifications FOR DELETE
    USING (auth.uid() = user_id);
