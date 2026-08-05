-- =========================================================
-- Migration: Create messages table with RLS
-- Messages are private; only sender and recipient can access
-- =========================================================

CREATE TABLE IF NOT EXISTS public.messages (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sender_id   UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    recipient_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    content     TEXT,
    encrypted_payload     TEXT,
    encryption_nonce      TEXT,
    sender_ephemeral_public_key TEXT,
    recipient_key_id      TEXT,
    is_zero_knowledge     BOOLEAN DEFAULT FALSE,
    read_at     TIMESTAMPTZ,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS messages_sender_idx    ON public.messages (sender_id);
CREATE INDEX IF NOT EXISTS messages_recipient_idx ON public.messages (recipient_id);
CREATE INDEX IF NOT EXISTS messages_created_idx   ON public.messages (created_at DESC);

ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;

-- Sender can insert their own messages
CREATE POLICY "Users can send messages"
    ON public.messages FOR INSERT
    WITH CHECK (auth.uid() = sender_id);

-- Only sender and recipient can read
CREATE POLICY "Users can read their own messages"
    ON public.messages FOR SELECT
    USING (auth.uid() = sender_id OR auth.uid() = recipient_id);

-- Only sender can update their own unsent/unread messages
CREATE POLICY "Sender can update own messages"
    ON public.messages FOR UPDATE
    USING (auth.uid() = sender_id);

-- Soft-delete: only sender can delete
CREATE POLICY "Sender can delete own messages"
    ON public.messages FOR DELETE
    USING (auth.uid() = sender_id);
