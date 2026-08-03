import React, { useEffect, useMemo, useState } from 'react';
import { apiJson, getCurrentUserId } from '../../utils/socialApi';
import type { FollowRequest, MuteDuration, MuteType, ReportReason, SocialOverview, SocialUser } from '../../types/social';

type DiscoverControlState = Record<string, { muteType: MuteType; duration: MuteDuration; reportReason: ReportReason; reportDescription: string }>;

function relationshipLabel(user: SocialUser): string {
  const relationship = user.relationship;
  if (!relationship) {
    return 'View';
  }
  if (relationship.blocked_by_current_user) {
    return 'Blocked';
  }
  if (relationship.blocked_by_target_user) {
    return 'Unavailable';
  }
  if (relationship.is_following) {
    return 'Following';
  }
  if (relationship.outgoing_follow_request) {
    return 'Requested';
  }
  return user.is_private ? 'Request follow' : 'Follow';
}

export function Profile({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [activeSegment, setActiveSegment] = useState<'posts' | 'requests' | 'network'>('posts');
  const [overview, setOverview] = useState<SocialOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [busyKey, setBusyKey] = useState('');
  const [controls, setControls] = useState<DiscoverControlState>({});

  const loadOverview = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiJson<{ success: boolean } & SocialOverview>('/api/social/me/overview');
      setOverview({
        me: data.me,
        pending_incoming: data.pending_incoming,
        pending_outgoing: data.pending_outgoing,
        discover: data.discover,
        followers: data.followers,
        following: data.following,
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load social graph');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadOverview();
  }, []);

  const updateDiscoverUser = (userId: string, updater: (user: SocialUser) => SocialUser) => {
    setOverview((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        discover: current.discover.map((user) => (user.id === userId ? updater(user) : user)),
      };
    });
  };

  const setControlValue = (userId: string, patch: Partial<DiscoverControlState[string]>) => {
    setControls((current) => ({
      ...current,
      [userId]: {
        muteType: current[userId]?.muteType ?? 'user',
        duration: current[userId]?.duration ?? 'always',
        reportReason: current[userId]?.reportReason ?? 'spam',
        reportDescription: current[userId]?.reportDescription ?? '',
        ...patch,
      },
    }));
  };

  const counts = useMemo(() => {
    if (!overview) {
      return { posts: 0, followers: 0, following: 0 };
    }
    return {
      posts: overview.me.posts_count,
      followers: overview.me.followers_count,
      following: overview.me.following_count,
    };
  }, [overview]);

  const runAction = async (actionKey: string, action: () => Promise<void>) => {
    setBusyKey(actionKey);
    setStatusMessage('');
    try {
      await action();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Action failed');
    } finally {
      setBusyKey('');
    }
  };

  const handlePrivacyToggle = async (isPrivate: boolean) => {
    if (!overview) {
      return;
    }

    const previous = overview.me.is_private;
    setOverview({ ...overview, me: { ...overview.me, is_private: isPrivate } });

    setBusyKey('privacy-toggle');
    setStatusMessage('');
    setError('');
    try {
      const response = await apiJson<{ success: boolean; user: SocialUser }>('/api/users/me/privacy', {
        method: 'PATCH',
        body: JSON.stringify({
          is_private: isPrivate,
          is_blocked_from_search: overview.me.is_blocked_from_search,
        }),
      });
      setOverview((current) => (current ? { ...current, me: response.user } : current));
      setStatusMessage(`Account switched to ${response.user.is_private ? 'private' : 'public'} mode.`);
    } catch (requestError) {
      setOverview((current) => (current ? { ...current, me: { ...current.me, is_private: previous } } : current));
      setError(requestError instanceof Error ? requestError.message : 'Action failed');
    } finally {
      setBusyKey('');
    }
  };

  const handleSearchVisibilityToggle = async (hideFromSearch: boolean) => {
    if (!overview) {
      return;
    }

    const previous = overview.me.is_blocked_from_search;
    setOverview({ ...overview, me: { ...overview.me, is_blocked_from_search: hideFromSearch } });

    setBusyKey('search-visibility-toggle');
    setStatusMessage('');
    setError('');
    try {
      const response = await apiJson<{ success: boolean; user: SocialUser }>('/api/users/me/privacy', {
        method: 'PATCH',
        body: JSON.stringify({
          is_private: overview.me.is_private,
          is_blocked_from_search: hideFromSearch,
        }),
      });
      setOverview((current) => (current ? { ...current, me: response.user } : current));
      setStatusMessage(response.user.is_blocked_from_search ? 'Search visibility disabled.' : 'Search visibility restored.');
    } catch (requestError) {
      setOverview((current) => (current ? { ...current, me: { ...current.me, is_blocked_from_search: previous } } : current));
      setError(requestError instanceof Error ? requestError.message : 'Action failed');
    } finally {
      setBusyKey('');
    }
  };

  const handleFollowToggle = async (user: SocialUser) => {
    const relationship = user.relationship;
    if (!overview || !relationship) {
      return;
    }

    await runAction(`follow-${user.id}`, async () => {
      if (relationship.is_following) {
        updateDiscoverUser(user.id, (current) => ({
          ...current,
          followers_count: Math.max(0, current.followers_count - 1),
          relationship: current.relationship ? { ...current.relationship, is_following: false } : current.relationship,
        }));
        setOverview((current) => (current ? { ...current, me: { ...current.me, following_count: Math.max(0, current.me.following_count - 1) } } : current));
        await apiJson(`/api/users/${user.id}/follow`, { method: 'DELETE' });
        setStatusMessage(`Unfollowed ${user.display_name}.`);
      } else {
        updateDiscoverUser(user.id, (current) => ({
          ...current,
          relationship: current.relationship
            ? {
                ...current.relationship,
                is_following: !current.is_private,
                outgoing_follow_request: current.is_private
                  ? {
                      id: `temp-${current.id}`,
                      requester_id: getCurrentUserId(),
                      target_id: current.id,
                      status: 'pending',
                      created_at: new Date().toISOString(),
                      responded_at: null,
                    }
                  : null,
              }
            : current.relationship,
        }));
        if (!user.is_private) {
          setOverview((current) => (current ? { ...current, me: { ...current.me, following_count: current.me.following_count + 1 } } : current));
        }
        const response = await apiJson<{ success: boolean; status: string }>('/api/users/' + user.id + '/follow', { method: 'POST' });
        setStatusMessage(response.status === 'pending' ? `Follow request sent to ${user.display_name}.` : `Now following ${user.display_name}.`);
      }
      await loadOverview();
    });
  };

  const handleRequestAction = async (request: FollowRequest, action: 'accept' | 'reject') => {
    await runAction(`${action}-${request.id}`, async () => {
      await apiJson(`/api/follow-requests/${request.id}/${action}`, { method: 'POST' });
      setOverview((current) => current ? { ...current, pending_incoming: current.pending_incoming.filter((item) => item.id !== request.id) } : current);
      setStatusMessage(`Follow request ${action}ed.`);
      await loadOverview();
    });
  };

  const handleMute = async (user: SocialUser) => {
    const control = controls[user.id] ?? { muteType: 'user', duration: 'always', reportReason: 'spam', reportDescription: '' };
    await runAction(`mute-${user.id}`, async () => {
      const response = await apiJson<{ success: boolean; mute: NonNullable<NonNullable<SocialUser['relationship']>['mutes'][MuteType]> }>(`/api/users/${user.id}/mute`, {
        method: 'POST',
        body: JSON.stringify({ mute_type: control.muteType, duration: control.duration }),
      });
      updateDiscoverUser(user.id, (current) => ({
        ...current,
        relationship: current.relationship
          ? { ...current.relationship, mutes: { ...current.relationship.mutes, [control.muteType]: response.mute } }
          : current.relationship,
      }));
      setStatusMessage(`${user.display_name} muted for ${control.muteType}.`);
    });
  };

  const handleUnmute = async (user: SocialUser, muteType: MuteType) => {
    await runAction(`unmute-${user.id}-${muteType}`, async () => {
      await apiJson(`/api/users/${user.id}/mute`, { method: 'DELETE', query: { mute_type: muteType } });
      updateDiscoverUser(user.id, (current) => ({
        ...current,
        relationship: current.relationship
          ? { ...current.relationship, mutes: { ...current.relationship.mutes, [muteType]: null } }
          : current.relationship,
      }));
      setStatusMessage(`${user.display_name} unmuted for ${muteType}.`);
    });
  };

  const handleBlockToggle = async (user: SocialUser) => {
    await runAction(`block-${user.id}`, async () => {
      if (user.relationship?.blocked_by_current_user) {
        await apiJson(`/api/users/${user.id}/block`, { method: 'DELETE' });
        setStatusMessage(`${user.display_name} unblocked.`);
      } else {
        await apiJson(`/api/users/${user.id}/block`, {
          method: 'POST',
          body: JSON.stringify({ reason: 'user_action' }),
        });
        setStatusMessage(`${user.display_name} blocked app-wide.`);
      }
      await loadOverview();
    });
  };

  const handleReport = async (user: SocialUser) => {
    const control = controls[user.id] ?? { muteType: 'user', duration: 'always', reportReason: 'spam', reportDescription: '' };
    await runAction(`report-${user.id}`, async () => {
      await apiJson(`/api/reports/users/${user.id}`, {
        method: 'POST',
        body: JSON.stringify({ reason: control.reportReason, description: control.reportDescription }),
      });
      setStatusMessage(`Report for ${user.display_name} submitted for review.`);
      setControlValue(user.id, { reportDescription: '' });
    });
  };

  return (
    <div style={{ flex: 1, minHeight: '100vh', background: 'radial-gradient(circle at top, #102033 0%, #020617 60%, #000000 100%)', color: '#ffffff' }}>
      <div style={{ padding: '22px 16px 18px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '18px', marginBottom: '18px' }}>
          <div style={{ width: '78px', height: '78px', borderRadius: '50%', background: 'linear-gradient(135deg, #22d3ee, #2563eb)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#020617', fontWeight: 900, fontSize: '22px' }}>
            {username.slice(0, 2).toUpperCase()}
          </div>

          <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', textAlign: 'center' }}>
            <div><div style={{ fontSize: '18px', fontWeight: 800 }}>{counts.posts}</div><div style={{ fontSize: '11px', color: '#94a3b8' }}>Posts</div></div>
            <div><div style={{ fontSize: '18px', fontWeight: 800 }}>{counts.followers}</div><div style={{ fontSize: '11px', color: '#94a3b8' }}>Followers</div></div>
            <div><div style={{ fontSize: '18px', fontWeight: 800 }}>{counts.following}</div><div style={{ fontSize: '11px', color: '#94a3b8' }}>Following</div></div>
          </div>
        </div>

        <div style={{ fontSize: '15px', fontWeight: 800 }}>{overview?.me.display_name ?? username}</div>
        <div style={{ fontSize: '12px', color: '#7dd3fc', marginTop: '4px' }}>@{overview?.me.username ?? username}</div>
        <div style={{ fontSize: '13px', color: '#cbd5e1', lineHeight: 1.5, marginTop: '8px', maxWidth: '560px' }}>
          {overview?.me.bio ?? 'Loading privacy-aware profile controls…'}
        </div>

        <div style={{ display: 'flex', gap: '10px', marginTop: '16px', flexWrap: 'wrap' }}>
          <button type="button" style={{ border: 'none', borderRadius: '999px', background: '#0f766e', color: '#ecfeff', padding: '10px 14px', cursor: 'pointer' }}>
            {overview?.me.is_private ? 'Private account' : 'Public account'}
          </button>
          <button type="button" onClick={onLogout} style={{ border: '1px solid #334155', borderRadius: '999px', background: 'transparent', color: '#f8fafc', padding: '10px 14px', cursor: 'pointer' }}>
            Logout
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '8px', padding: '0 16px 14px' }}>
        {([
          ['posts', 'Privacy'],
          ['requests', `Requests ${overview?.pending_incoming.length ?? 0}`],
          ['network', 'Network'],
        ] as const).map(([segment, label]) => (
          <button
            key={segment}
            type="button"
            onClick={() => setActiveSegment(segment)}
            style={{
              flex: 1,
              borderRadius: '999px',
              border: activeSegment === segment ? '1px solid #22d3ee' : '1px solid #1e293b',
              background: activeSegment === segment ? 'rgba(34, 211, 238, 0.12)' : '#020617',
              color: '#e2e8f0',
              padding: '10px 12px',
              cursor: 'pointer',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={{ padding: '0 16px 24px', display: 'grid', gap: '14px' }}>
        {loading ? <div style={{ color: '#94a3b8' }}>Loading profile controls…</div> : null}
        {!loading && error ? <div style={{ color: '#fca5a5' }}>{error}</div> : null}
        {!loading && statusMessage ? <div style={{ color: '#86efac' }}>{statusMessage}</div> : null}

        {activeSegment === 'posts' && overview ? (
          <>
            <section style={{ background: 'rgba(15, 23, 42, 0.84)', border: '1px solid #1e293b', borderRadius: '20px', padding: '16px' }}>
              <div style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px' }}>Account privacy</div>
              <div style={{ display: 'grid', gap: '12px' }}>
                <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#e2e8f0' }}>
                  Private account
                  <input type="checkbox" checked={overview.me.is_private} onChange={(event) => void handlePrivacyToggle(event.target.checked)} disabled={busyKey === 'privacy-toggle'} />
                </label>
                <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#e2e8f0' }}>
                  Hide from search
                  <input type="checkbox" checked={overview.me.is_blocked_from_search} onChange={(event) => void handleSearchVisibilityToggle(event.target.checked)} disabled={busyKey === 'search-visibility-toggle'} />
                </label>
                <div style={{ fontSize: '12px', color: '#94a3b8', lineHeight: 1.5 }}>
                  Private mode restricts posts, stories, and follower lists to approved followers. Search visibility suppresses discovery without affecting existing relationships.
                </div>
              </div>
            </section>

            <section style={{ background: 'rgba(15, 23, 42, 0.84)', border: '1px solid #1e293b', borderRadius: '20px', padding: '16px' }}>
              <div style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px' }}>Post visibility summary</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '10px' }}>
                {(overview.me.posts ?? []).map((post) => (
                  <div key={post.id} style={{ borderRadius: '16px', border: '1px solid #334155', background: '#020617', padding: '12px' }}>
                    <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#7dd3fc', marginBottom: '6px' }}>{post.visibility}</div>
                    <div style={{ fontSize: '13px', color: '#f8fafc', lineHeight: 1.4 }}>{post.caption}</div>
                  </div>
                ))}
              </div>
            </section>
          </>
        ) : null}

        {activeSegment === 'requests' && overview ? (
          <section style={{ background: 'rgba(15, 23, 42, 0.84)', border: '1px solid #1e293b', borderRadius: '20px', padding: '16px' }}>
            <div style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px' }}>Pending follow requests</div>
            <div style={{ display: 'grid', gap: '10px' }}>
              {overview.pending_incoming.map((request) => {
                const requester = overview.discover.find((user) => user.id === request.requester_id) ?? overview.followers.find((user) => user.id === request.requester_id);
                return (
                  <div key={request.id} style={{ borderRadius: '16px', border: '1px solid #334155', background: '#020617', padding: '14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
                    <div>
                      <div style={{ fontSize: '14px', fontWeight: 700 }}>{requester?.display_name ?? request.requester_id}</div>
                      <div style={{ fontSize: '12px', color: '#94a3b8' }}>Requested {new Date(request.created_at).toLocaleString()}</div>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button type="button" onClick={() => void handleRequestAction(request, 'accept')} style={{ borderRadius: '999px', border: 'none', background: '#166534', color: '#f0fdf4', padding: '8px 12px', cursor: 'pointer' }}>
                        {busyKey === `accept-${request.id}` ? 'Accepting…' : 'Accept'}
                      </button>
                      <button type="button" onClick={() => void handleRequestAction(request, 'reject')} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '8px 12px', cursor: 'pointer' }}>
                        {busyKey === `reject-${request.id}` ? 'Rejecting…' : 'Reject'}
                      </button>
                    </div>
                  </div>
                );
              })}
              {!overview.pending_incoming.length ? <div style={{ color: '#94a3b8', fontSize: '13px' }}>No pending follow requests.</div> : null}
            </div>
          </section>
        ) : null}

        {activeSegment === 'network' && overview ? (
          <section style={{ background: 'rgba(15, 23, 42, 0.84)', border: '1px solid #1e293b', borderRadius: '20px', padding: '16px' }}>
            <div style={{ fontSize: '14px', fontWeight: 700, marginBottom: '12px' }}>Relationship controls</div>
            <div style={{ display: 'grid', gap: '14px' }}>
              {overview.discover.map((user) => {
                const control = controls[user.id] ?? { muteType: 'user', duration: 'always', reportReason: 'spam', reportDescription: '' };
                return (
                  <div key={user.id} style={{ borderRadius: '18px', border: '1px solid #334155', background: '#020617', padding: '14px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '10px' }}>
                      <div>
                        <div style={{ fontSize: '15px', fontWeight: 700 }}>{user.display_name}</div>
                        <div style={{ fontSize: '12px', color: '#7dd3fc' }}>@{user.username}</div>
                        <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '6px', lineHeight: 1.45 }}>{user.bio}</div>
                      </div>
                      <div style={{ fontSize: '11px', color: '#94a3b8' }}>{relationshipLabel(user)}</div>
                    </div>

                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
                      <button type="button" onClick={() => void handleFollowToggle(user)} disabled={user.relationship?.blocked_by_target_user} style={{ borderRadius: '999px', border: 'none', background: '#2563eb', color: '#eff6ff', padding: '8px 12px', cursor: 'pointer', opacity: user.relationship?.blocked_by_target_user ? 0.5 : 1 }}>
                        {busyKey === `follow-${user.id}` ? 'Updating…' : relationshipLabel(user)}
                      </button>
                      <button type="button" onClick={() => void handleBlockToggle(user)} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '8px 12px', cursor: 'pointer' }}>
                        {busyKey === `block-${user.id}` ? 'Updating…' : user.relationship?.blocked_by_current_user ? 'Unblock' : 'Block'}
                      </button>
                    </div>

                    <div style={{ display: 'grid', gap: '10px', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
                      <select value={control.muteType} onChange={(event) => setControlValue(user.id, { muteType: event.target.value as MuteType })} style={{ borderRadius: '12px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '9px 10px' }}>
                        <option value="user">Mute user</option>
                        <option value="posts">Mute posts</option>
                        <option value="stories">Mute stories</option>
                      </select>
                      <select value={control.duration} onChange={(event) => setControlValue(user.id, { duration: event.target.value as MuteDuration })} style={{ borderRadius: '12px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '9px 10px' }}>
                        <option value="8_hours">8 Hours</option>
                        <option value="1_week">1 Week</option>
                        <option value="always">Always</option>
                      </select>
                      <button type="button" onClick={() => void handleMute(user)} style={{ borderRadius: '999px', border: 'none', background: '#6d28d9', color: '#f5f3ff', padding: '8px 12px', cursor: 'pointer' }}>
                        {busyKey === `mute-${user.id}` ? 'Muting…' : 'Apply mute'}
                      </button>
                      <button type="button" onClick={() => void handleUnmute(user, control.muteType)} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '8px 12px', cursor: 'pointer' }}>
                        {busyKey === `unmute-${user.id}-${control.muteType}` ? 'Removing…' : 'Remove mute'}
                      </button>
                    </div>

                    <div style={{ display: 'grid', gap: '10px', marginTop: '12px' }}>
                      <select value={control.reportReason} onChange={(event) => setControlValue(user.id, { reportReason: event.target.value as ReportReason })} style={{ borderRadius: '12px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '9px 10px' }}>
                        <option value="spam">Spam</option>
                        <option value="harassment">Harassment</option>
                        <option value="inappropriate_content">Inappropriate Content</option>
                        <option value="fraud">Fraud</option>
                      </select>
                      <textarea value={control.reportDescription} onChange={(event) => setControlValue(user.id, { reportDescription: event.target.value })} placeholder="Optional report notes" rows={3} style={{ borderRadius: '12px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '9px 10px', resize: 'vertical' }} />
                      <button type="button" onClick={() => void handleReport(user)} style={{ borderRadius: '999px', border: 'none', background: '#92400e', color: '#fffbeb', padding: '8px 12px', cursor: 'pointer' }}>
                        {busyKey === `report-${user.id}` ? 'Reporting…' : 'Report user'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}
