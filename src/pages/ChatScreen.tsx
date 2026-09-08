import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ChatDetailsPanel } from '../components/chat/ChatDetailsPanel';
import { DMLock } from '../components/security/DMLock';
import type { ChatConversation, ChatDetails, ChatMessage, MuteDuration, ReportReason } from '../types/social';
import { apiJson, API_BASE, getAccessToken } from '../utils/socialApi';
import { decryptDirectMessage, encryptDirectMessage, fetchRemotePublicKeyBundle, syncLocalPublicKeyBundle } from '../utils/e2ee';
import { enqueuePendingMessage, flushPendingMessages } from '../utils/offlineMessageQueue';
import { hasChatLock, verifyChatLock } from '../utils/lockVault';
import { retryWithBackoff } from '../utils/retry';

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Now' : date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export function ChatScreen({ onBack, initialConversationId }: { onBack?: () => void; initialConversationId?: string }) {
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState('');
  const [draft, setDraft] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [chatError, setChatError] = useState('');
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState('');
  const [detailsStatus, setDetailsStatus] = useState('');
  const [chatDetails, setChatDetails] = useState<ChatDetails | null>(null);
  const [searchMatches, setSearchMatches] = useState<ChatMessage[]>([]);
  const [lockedConversationId, setLockedConversationId] = useState('');
  const [chatLockBusy, setChatLockBusy] = useState(false);
  const [chatLockError, setChatLockError] = useState('');
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId) ?? null,
    [conversations, activeConversationId]
  );

  const fetchConversations = async () => {
    try {
      await syncLocalPublicKeyBundle();
      const data = await retryWithBackoff(
        () => apiJson<{ success: boolean; conversations: ChatConversation[] }>('/api/chat/conversations'),
        { retries: 3, initialDelayMs: 300 },
      );
      const nextConversations = await Promise.all((data.conversations ?? []).map(async (conversation) => ({
        ...conversation,
        messages: await Promise.all(conversation.messages.map(async (message) => {
          if (message.is_zero_knowledge && message.encrypted_payload && message.encryption_nonce && message.sender_ephemeral_public_key && message.recipient_key_id) {
            try {
              const decryptedText = await decryptDirectMessage({
                conversationId: conversation.id,
                senderUserId: message.sender_id,
                encrypted_payload: message.encrypted_payload,
                encryption_nonce: message.encryption_nonce,
                sender_ephemeral_public_key: message.sender_ephemeral_public_key,
                recipient_key_id: message.recipient_key_id,
              });
              return { ...message, text: decryptedText };
            } catch {
              return { ...message, text: '[Unable to decrypt message]' };
            }
          }
          return message;
        })),
      })));
      setConversations(nextConversations);
      if (!activeConversationId && nextConversations.length > 0) {
        setActiveConversationId(nextConversations[0].id);
      }
    } catch (error) {
      console.error('Unable to load chat conversations', error);
      setChatError(error instanceof Error ? error.message : 'Unable to load chat conversations');
      setConversations([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchChatDetails = async (conversationId: string) => {
    setDetailsLoading(true);
    setDetailsError('');
    try {
      const data = await apiJson<{ success: boolean } & ChatDetails>(`/api/chat/conversations/${conversationId}/details`);
      setChatDetails({
        conversation_id: data.conversation_id,
        profile: data.profile,
        shared_media: data.shared_media,
        settings: data.settings,
        relationship: data.relationship,
      });
    } catch (error) {
      setDetailsError(error instanceof Error ? error.message : 'Unable to load chat details');
      setChatDetails(null);
    } finally {
      setDetailsLoading(false);
    }
  };

  useEffect(() => {
    void fetchConversations();
  }, []);

  useEffect(() => {
    if (initialConversationId) {
      setActiveConversationId(initialConversationId);
    }
  }, [initialConversationId]);

  useEffect(() => {
    if (!activeConversationId) return undefined;

    const openStream = () => {
      const accessToken = getAccessToken();
      if (!accessToken) {
        setChatError('Session expired. Please sign in again.');
        return;
      }

      eventSourceRef.current?.close();
      const streamUrl = new URL(`${API_BASE}/api/chat/conversations/${activeConversationId}/stream`);
      streamUrl.searchParams.set('access_token', accessToken);
      const source = new EventSource(streamUrl.toString());
      source.addEventListener('message', (event) => {
        reconnectAttemptsRef.current = 0;
        try {
          const incomingMessage = JSON.parse(event.data) as ChatMessage;
          void (async () => {
            const resolvedMessage = incomingMessage.is_zero_knowledge && incomingMessage.encrypted_payload && incomingMessage.encryption_nonce && incomingMessage.sender_ephemeral_public_key && incomingMessage.recipient_key_id
              ? {
                  ...incomingMessage,
                  text: await decryptDirectMessage({
                    conversationId: activeConversationId,
                    senderUserId: incomingMessage.sender_id,
                    encrypted_payload: incomingMessage.encrypted_payload,
                    encryption_nonce: incomingMessage.encryption_nonce,
                    sender_ephemeral_public_key: incomingMessage.sender_ephemeral_public_key,
                    recipient_key_id: incomingMessage.recipient_key_id,
                  }).catch(() => '[Unable to decrypt message]'),
                }
              : incomingMessage;

            setConversations((prev) => prev.map((conversation) => {
              if (conversation.id !== activeConversationId) return conversation;
              if (conversation.messages.some((message) => message.id === resolvedMessage.id)) {
                return conversation;
              }
              return {
                ...conversation,
                messages: [...conversation.messages, resolvedMessage],
              };
            }));
          })();
        } catch (error) {
          console.error('Unable to parse incoming chat message', error);
        }
      });
      source.onerror = () => {
        source.close();
        reconnectAttemptsRef.current += 1;
        const delay = Math.min(1000 * 2 ** (reconnectAttemptsRef.current - 1), 10000);
        reconnectTimerRef.current = window.setTimeout(openStream, delay);
      };
      eventSourceRef.current = source;
    };

    openStream();

    return () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
  }, [activeConversationId]);

  useEffect(() => {
    if (detailsOpen && activeConversationId) {
      void fetchChatDetails(activeConversationId);
    }
  }, [detailsOpen, activeConversationId]);

  useEffect(() => {
    const flush = async () => {
      try {
        await flushPendingMessages();
        await fetchConversations();
      } catch {
        // Keep queue for the next online transition.
      }
    };
    const handler = () => { void flush(); };
    window.addEventListener('online', handler);
    void flush();
    return () => window.removeEventListener('online', handler);
  }, []);

  const updateConversation = (conversationId: string, updater: (conversation: ChatConversation) => ChatConversation) => {
    setConversations((prev) => prev.map((conversation) => (conversation.id === conversationId ? updater(conversation) : conversation)));
  };

  const handleConversationSelect = async (conversationId: string) => {
    if (await hasChatLock(conversationId)) {
      setLockedConversationId(conversationId);
      setChatLockError('');
      return;
    }
    setActiveConversationId(conversationId);
  };

  const handleSend = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.trim() || !activeConversationId || !activeConversation) return;

    const messageText = draft.trim();
    setDraft('');
    setChatError('');

    const optimisticId = Date.now();
    updateConversation(activeConversationId, (conversation) => ({
      ...conversation,
      messages: [...conversation.messages, {
        id: optimisticId,
        conversation_id: activeConversationId,
        sender_id: 'me',
        sender_name: 'You',
        text: messageText,
        created_at: new Date().toISOString(),
        is_zero_knowledge: true,
        delivery_state: navigator.onLine ? 'sent' : 'queued',
      }],
    }));

    try {
      const recipientBundle = await fetchRemotePublicKeyBundle(activeConversation.partner_user_id);
      const envelope = await encryptDirectMessage({
        conversationId: activeConversationId,
        recipientUserId: activeConversation.partner_user_id,
        recipientBundle,
        plaintext: messageText,
      });
      const requestPayload = {
        sender_id: 'me',
        sender_name: 'You',
        encrypted_payload: envelope.encrypted_payload,
        encryption_nonce: envelope.encryption_nonce,
        sender_ephemeral_public_key: envelope.sender_ephemeral_public_key,
        recipient_key_id: envelope.recipient_key_id,
        encryption_algorithm: envelope.encryption_algorithm,
      };

      if (!navigator.onLine) {
        await enqueuePendingMessage({
          id: `pending-${optimisticId}`,
          conversationId: activeConversationId,
          payload: requestPayload,
          createdAt: new Date().toISOString(),
        });
        setChatError('');
        return;
      }

      const data = await retryWithBackoff(
        () => apiJson<{ success: boolean; message: ChatMessage }>(`/api/chat/conversations/${activeConversationId}/messages`, {
          method: 'POST',
          body: JSON.stringify(requestPayload),
        }),
        { retries: 4, initialDelayMs: 350 },
      );
      updateConversation(activeConversationId, (conversation) => ({
        ...conversation,
        messages: conversation.messages.map((message) => message.id === optimisticId ? { ...data.message, text: messageText } : message),
      }));
    } catch (error) {
      console.error('Unable to send message', error);
      setChatError(error instanceof Error ? error.message : 'Unable to send message');
      updateConversation(activeConversationId, (conversation) => ({
        ...conversation,
        messages: conversation.messages.map((message) => message.id === optimisticId ? { ...message, delivery_state: 'failed' } : message),
      }));
      setDraft(messageText);
    }
  };

  const handleSaveSettings = async (payload: {
    custom_wallpaper?: string;
    custom_nickname?: string;
    is_muted?: boolean;
    mute_duration?: MuteDuration;
    notification_sound_enabled?: boolean;
    vibration_enabled?: boolean;
  }) => {
    if (!activeConversationId) {
      return;
    }

    const previousDetails = chatDetails;
    if (chatDetails) {
      const optimisticSettings = {
        ...chatDetails.settings,
        custom_wallpaper: payload.custom_wallpaper ?? chatDetails.settings.custom_wallpaper,
        custom_nickname: payload.custom_nickname ?? chatDetails.settings.custom_nickname,
        is_muted: payload.is_muted ?? chatDetails.settings.is_muted,
        notification_sound_enabled: payload.notification_sound_enabled ?? chatDetails.settings.notification_sound_enabled,
        vibration_enabled: payload.vibration_enabled ?? chatDetails.settings.vibration_enabled,
      };
      setChatDetails({ ...chatDetails, settings: optimisticSettings });
      updateConversation(activeConversationId, (conversation) => ({
        ...conversation,
        title: optimisticSettings.custom_nickname.trim() || conversation.partner.display_name,
        chat_settings: optimisticSettings,
      }));
    }

    try {
      const response = await apiJson<{ success: boolean; settings: ChatDetails['settings'] }>(`/api/chat/conversations/${activeConversationId}/settings`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      setChatDetails((current) => (current ? { ...current, settings: response.settings } : current));
      updateConversation(activeConversationId, (conversation) => ({
        ...conversation,
        title: response.settings.custom_nickname.trim() || conversation.partner.display_name,
        chat_settings: response.settings,
      }));
      setDetailsStatus('Chat settings updated.');
    } catch (error) {
      if (previousDetails) {
        setChatDetails(previousDetails);
        updateConversation(activeConversationId, (conversation) => ({
          ...conversation,
          title: previousDetails.settings.custom_nickname.trim() || conversation.partner.display_name,
          chat_settings: previousDetails.settings,
        }));
      }
      throw error;
    }
  };

  const handleResetWallpaper = async () => {
    if (!activeConversationId) {
      return;
    }
    const response = await apiJson<{ success: boolean; settings: ChatDetails['settings'] }>(`/api/chat/conversations/${activeConversationId}/reset-wallpaper`, { method: 'POST' });
    setChatDetails((current) => (current ? { ...current, settings: response.settings } : current));
    updateConversation(activeConversationId, (conversation) => ({ ...conversation, chat_settings: response.settings }));
    setDetailsStatus('Wallpaper reset to default.');
  };

  const handleSearchChat = async (query: string) => {
    if (!activeConversationId) {
      return;
    }
    const response = await apiJson<{ success: boolean; matches: ChatMessage[] }>(`/api/chat/conversations/${activeConversationId}/search`, { query: { q: query } });
    setSearchMatches(response.matches);
  };

  const handleClearHistory = async () => {
    if (!activeConversationId) {
      return;
    }
    await apiJson(`/api/chat/conversations/${activeConversationId}/clear`, { method: 'POST' });
    updateConversation(activeConversationId, (conversation) => ({ ...conversation, messages: [] }));
    setSearchMatches([]);
    setDetailsStatus('Chat history cleared for the current user.');
  };

  const handleExportChat = async () => {
    if (!activeConversationId) {
      return;
    }
    const response = await apiJson<{ success: boolean; filename: string; content: string }>(`/api/chat/conversations/${activeConversationId}/export`);
    const blob = new Blob([response.content], { type: 'text/plain;charset=utf-8' });
    const downloadUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = downloadUrl;
    anchor.download = response.filename;
    anchor.click();
    URL.revokeObjectURL(downloadUrl);
    setDetailsStatus('Chat export generated.');
  };

  const handleToggleBlock = async () => {
    if (!activeConversationId || !chatDetails) {
      return;
    }

    if (chatDetails.relationship.blocked_by_current_user) {
      await apiJson(`/api/users/${chatDetails.profile.id}/block`, { method: 'DELETE' });
      setDetailsStatus(`${chatDetails.profile.display_name} unblocked.`);
    } else {
      await apiJson(`/api/users/${chatDetails.profile.id}/block`, {
        method: 'POST',
        body: JSON.stringify({ reason: 'chat_settings' }),
      });
      setDetailsStatus(`${chatDetails.profile.display_name} blocked app-wide.`);
    }
    await fetchConversations();
    await fetchChatDetails(activeConversationId);
  };

  const handleReportUser = async (reason: ReportReason, description: string) => {
    if (!chatDetails) {
      return;
    }
    await apiJson(`/api/reports/users/${chatDetails.profile.id}`, {
      method: 'POST',
      body: JSON.stringify({ reason, description }),
    });
    setDetailsStatus(`Report for ${chatDetails.profile.display_name} sent for review.`);
  };

  const filteredConversations = useMemo(() => {
    const query = searchQuery.toLowerCase();
    return conversations.filter((conversation) => {
      const haystack = `${conversation.title} ${conversation.participants.join(' ')}`.toLowerCase();
      return haystack.includes(query);
    });
  }, [conversations, searchQuery]);

  return (
    <div style={{ minHeight: '100vh', background: 'radial-gradient(circle at top, #1a1f2b 0%, #05070c 70%)', color: '#f8fafc', display: 'flex', flexDirection: 'column' }}>
      <div style={{ borderBottom: '1px solid #1e293b', padding: '16px 18px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={() => onBack?.()}
          style={{ background: 'transparent', border: '1px solid #334155', color: '#f8fafc', borderRadius: '999px', width: '36px', height: '36px', cursor: 'pointer' }}
          type="button"
        >
          ←
        </button>
        <div>
          <div style={{ fontSize: '11px', letterSpacing: '0.24em', color: '#7dd3fc', textTransform: 'uppercase' }}>Secure chat</div>
          <div style={{ fontSize: '18px', fontWeight: 700 }}>Live comms</div>
        </div>
      </div>

      <div style={{ padding: '12px 16px' }}>
        <input
          type="text"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="Search channels..."
          style={{ width: '100%', borderRadius: '999px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '10px 14px', outline: 'none' }}
        />
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 16px 12px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {filteredConversations.map((conversation) => {
            const preview = conversation.messages[conversation.messages.length - 1]?.text ?? 'No messages yet';
            const isActive = conversation.id === activeConversationId;
            return (
              <button
                key={conversation.id}
                type="button"
                onClick={() => void handleConversationSelect(conversation.id)}
                style={{
                  textAlign: 'left',
                  border: isActive ? '1px solid #7c3aed' : '1px solid #1f2937',
                  borderRadius: '16px',
                  background: isActive ? 'rgba(124, 58, 237, 0.18)' : '#0f172a',
                  padding: '12px',
                  color: '#f8fafc',
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <strong>{conversation.title}</strong>
                  <span style={{ fontSize: '11px', color: '#94a3b8' }}>{conversation.participants.join(' • ')}</span>
                </div>
                <div style={{ fontSize: '13px', color: '#cbd5e1', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{preview}</div>
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ borderTop: '1px solid #1e293b', background: '#020617', padding: '12px 16px 20px' }}>
        {chatError ? <div style={{ color: '#fca5a5', fontSize: '13px', marginBottom: '10px' }}>{chatError}</div> : null}
        {loading ? (
          <div style={{ color: '#94a3b8', fontSize: '13px' }}>Connecting to the live channel…</div>
        ) : activeConversation ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
              <button
                type="button"
                onClick={() => {
                  setDetailsOpen(true);
                  setDetailsStatus('');
                  setSearchMatches([]);
                }}
                style={{ background: 'transparent', border: 'none', color: '#f8fafc', textAlign: 'left', padding: 0, cursor: 'pointer' }}
              >
                <div style={{ fontSize: '13px', fontWeight: 700 }}>{activeConversation.title}</div>
                <div style={{ fontSize: '11px', color: activeConversation.is_unavailable ? '#fca5a5' : '#38bdf8' }}>
                  {activeConversation.is_unavailable ? 'User unavailable' : `Live • ${activeConversation.participants.join(', ')}`}
                </div>
              </button>
              <button type="button" onClick={() => setDetailsOpen(true)} style={{ borderRadius: '999px', border: '1px solid #334155', background: 'transparent', color: '#f8fafc', padding: '8px 12px', cursor: 'pointer' }}>
                Details
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '250px', overflowY: 'auto', marginBottom: '10px' }}>
              {activeConversation.messages.map((message) => {
                const isMe = message.sender_id === 'me';
                return (
                  <div key={message.id} style={{ display: 'flex', justifyContent: isMe ? 'flex-end' : 'flex-start' }}>
                    <div style={{ maxWidth: '78%', padding: '10px 12px', borderRadius: '14px', background: isMe ? '#7c3aed' : '#111827', color: '#f8fafc' }}>
                      <div style={{ fontSize: '11px', color: isMe ? '#ddd6fe' : '#38bdf8', marginBottom: '4px' }}>{message.sender_name}</div>
                      <div style={{ fontSize: '13px', lineHeight: 1.45 }}>{message.text}</div>
                      {message.delivery_state === 'queued' ? <div style={{ fontSize: '10px', color: '#facc15', marginTop: '4px' }}>Queued offline</div> : null}
                      {message.delivery_state === 'failed' ? <div style={{ fontSize: '10px', color: '#fca5a5', marginTop: '4px' }}>Send failed</div> : null}
                      <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '4px', textAlign: 'right' }}>{formatTime(message.created_at)}</div>
                    </div>
                  </div>
                );
              })}
            </div>
            <form onSubmit={handleSend} style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={activeConversation.is_unavailable ? 'Messaging disabled for unavailable users' : 'Type a secure message...'}
                disabled={activeConversation.is_unavailable}
                style={{ flex: 1, borderRadius: '999px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '10px 14px', outline: 'none' }}
              />
              <button type="submit" disabled={activeConversation.is_unavailable} style={{ borderRadius: '999px', border: 'none', background: activeConversation.is_unavailable ? '#475569' : '#7c3aed', color: '#fff', padding: '10px 14px', cursor: activeConversation.is_unavailable ? 'not-allowed' : 'pointer' }}>
                Send
              </button>
            </form>
          </>
        ) : (
          <div style={{ color: '#94a3b8', fontSize: '13px' }}>No channel selected yet.</div>
        )}
      </div>

      {detailsOpen ? (
        <ChatDetailsPanel
          details={chatDetails}
          loading={detailsLoading}
          error={detailsError}
          statusMessage={detailsStatus}
          searchMatches={searchMatches}
          onClose={() => setDetailsOpen(false)}
          onSaveSettings={handleSaveSettings}
          onResetWallpaper={handleResetWallpaper}
          onSearch={handleSearchChat}
          onClearHistory={handleClearHistory}
          onExport={handleExportChat}
          onToggleBlock={handleToggleBlock}
          onReport={handleReportUser}
        />
      ) : null}

      {lockedConversationId ? (
        <DMLock
          title="Unlock protected chat"
          busy={chatLockBusy}
          error={chatLockError}
          onBiometricUnlock={async () => {
            setActiveConversationId(lockedConversationId);
            setLockedConversationId('');
          }}
          onSubmit={async (secret) => {
            setChatLockBusy(true);
            setChatLockError('');
            try {
              const valid = await verifyChatLock(lockedConversationId, secret);
              if (!valid) {
                setChatLockError('Incorrect chat unlock secret.');
                return;
              }
              setActiveConversationId(lockedConversationId);
              setLockedConversationId('');
            } finally {
              setChatLockBusy(false);
            }
          }}
        />
      ) : null}
    </div>
  );
}
