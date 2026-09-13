import React, { useEffect, useMemo, useState } from 'react';
import { apiJson } from '../../utils/socialApi';
import { prefetchMedia } from '../../utils/mediaCache';

interface Post {
  id: string;
  author: string;
  likes: number;
  caption: string;
  tags: string[];
  mentions: string[];
  location: string;
  visibility?: string;
  created_at?: string;
  image_url?: string | null;
  comments_count?: number;
  impression_count?: number;
  shares_count?: number;
}

type FeedFilter = 'all' | 'followers' | 'private';

export function HomeFeed({ onInteraction }: { onInteraction: (type: string, tag: string) => void }) {
  const [posts, setPosts] = useState<Post[]>([]);
  const [likedPosts, setLikedPosts] = useState<string[]>([]);
  const [dislikedPosts, setDislikedPosts] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FeedFilter>('all');
  const [privacyMode, setPrivacyMode] = useState<'public' | 'followers' | 'private'>('public');
  const [draftPost, setDraftPost] = useState('');
  const [posting, setPosting] = useState(false);
  const [commentInputs, setCommentInputs] = useState<Record<string, string>>({});
  const [statusMessage, setStatusMessage] = useState('');
  const [feedOffset, setFeedOffset] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);

  const trackEvent = async (postId: string, interactionType: string, metadata: Record<string, unknown> = {}) => {
    await apiJson('/api/posts/' + postId + '/interactions', {
      method: 'POST',
      body: JSON.stringify({ interaction_type: interactionType, metadata }),
    });
  };

  useEffect(() => {
    const loadPosts = async () => {
      try {
        const data = await apiJson<{ success: boolean; posts: Record<string, unknown>[] }>('/api/posts/feed', {
          query: { limit: 5, offset: 0 },
        });
        if (data?.success) {
          const mappedPosts = (data.posts ?? []).map((post: Record<string, unknown>) => ({
            id: typeof post.id === 'string' ? post.id : `post-${String(post.content ?? Date.now())}`,
            author: post.user_id ? `user_${String(post.user_id).slice(0, 6)}` : 'omni_user',
            likes: typeof post.likes === 'number' ? post.likes : 0,
            caption: typeof post.content === 'string' ? post.content : 'Shared from the private network',
            tags: Array.isArray(post.tags) ? post.tags.filter((tag): tag is string => typeof tag === 'string') : ['#OMNIX', '#Live'],
            mentions: Array.isArray(post.mentions) ? post.mentions.filter((mention): mention is string => typeof mention === 'string') : [],
            location: typeof post.location === 'string' ? post.location : 'Secure feed',
            visibility: typeof post.visibility === 'string' ? post.visibility : 'public',
            created_at: typeof post.created_at === 'string' ? post.created_at : undefined,
            image_url: typeof post.image_url === 'string' ? post.image_url : null,
            comments_count: typeof post.comments_count === 'number' ? post.comments_count : 0,
            shares_count: typeof post.shares_count === 'number' ? post.shares_count : 0,
            impression_count: typeof post.impression_count === 'number' ? post.impression_count : 0,
          }));
          setPosts(mappedPosts);
          setFeedOffset(mappedPosts.length);
          void prefetchMedia(mappedPosts.map((item) => item.image_url ?? '').filter(Boolean), 5);
          for (const item of mappedPosts) void trackEvent(item.id, 'impression', { source: 'home_feed' });
        }
      } catch (error) {
        console.error('Unable to load feed posts', error);
        setPosts([
          { id: 'fallback-1', author: 'Aadil_724', likes: 1424, caption: 'Building the cleanest ecosystem network live.', tags: ['#Ecosystem', '#BITE', '#Privacy'], mentions: ['@shadow_dev'], location: 'Secure Server Grid', visibility: 'public' },
          { id: 'fallback-2', author: 'shadow_dev', likes: 890, caption: 'Self-healing recommendation pipeline integrated successfully.', tags: ['#Algorithm', '#AI', '#NextGen'], mentions: ['@Aadil_724'], location: 'Distributed Node 4', visibility: 'followers' },
        ]);
      } finally {
        setLoading(false);
      }
    };
    void loadPosts();
  }, []);

  const loadMore = async () => {
    if (loadingMore) return;
    setLoadingMore(true);
    try {
      const data = await apiJson<{ success: boolean; posts: Record<string, unknown>[] }>('/api/posts/feed', { query: { limit: 5, offset: feedOffset } });
      if (!data?.success) return;
      const next = (data.posts ?? []).map((post: Record<string, unknown>) => ({
        id: typeof post.id === 'string' ? post.id : `post-${String(post.content ?? Date.now())}`,
        author: post.user_id ? `user_${String(post.user_id).slice(0, 6)}` : 'omni_user',
        likes: typeof post.likes === 'number' ? post.likes : 0,
        caption: typeof post.content === 'string' ? post.content : 'Shared from the private network',
        tags: Array.isArray(post.tags) ? post.tags.filter((tag): tag is string => typeof tag === 'string') : [],
        mentions: Array.isArray(post.mentions) ? post.mentions.filter((mention): mention is string => typeof mention === 'string') : [],
        location: typeof post.location === 'string' ? post.location : 'Secure feed',
        visibility: typeof post.visibility === 'string' ? post.visibility : 'public',
        created_at: typeof post.created_at === 'string' ? post.created_at : undefined,
        image_url: typeof post.image_url === 'string' ? post.image_url : null,
        comments_count: typeof post.comments_count === 'number' ? post.comments_count : 0,
        shares_count: typeof post.shares_count === 'number' ? post.shares_count : 0,
        impression_count: typeof post.impression_count === 'number' ? post.impression_count : 0,
      }));
      setPosts((current) => [...current, ...next.filter((item) => !current.some((existing) => existing.id === item.id))]);
      setFeedOffset((current) => current + next.length);
      void prefetchMedia(next.map((item) => item.image_url ?? '').filter(Boolean), 5);
    } finally {
      setLoadingMore(false);
    }
  };

  const toggledPosts = useMemo(() => posts.filter((post) => {
    if (filter === 'followers') return post.visibility === 'followers' || post.visibility === 'public';
    if (filter === 'private') return post.visibility === 'private';
    return true;
  }), [filter, posts]);

  const handleCreatePost = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draftPost.trim()) return;
    setPosting(true);
    try {
      const data = await apiJson<{ success: boolean; data: Record<string, unknown> }>('/api/posts', {
        method: 'POST',
        body: JSON.stringify({ content: draftPost.trim(), image_url: null, visibility: privacyMode, location: 'Secure feed', tags: [`#${privacyMode}`], mentions: [] }),
      });
      if (data.success) {
        const created = data.data;
        const createdId = typeof created?.id === 'string' ? created.id : `local-${Date.now()}`;
        const createdCaption = typeof created?.content === 'string' ? created.content : draftPost.trim();
        const createdLikes = typeof created?.likes === 'number' ? created.likes : 0;
        const createdTags = Array.isArray(created?.tags) ? created.tags.filter((value): value is string => typeof value === 'string') : [`#${privacyMode}`];
        const createdMentions = Array.isArray(created?.mentions) ? created.mentions.filter((value): value is string => typeof value === 'string') : [];
        const createdLocation = typeof created?.location === 'string' ? created.location : 'Secure feed';
        const createdVisibility = typeof created?.visibility === 'string' ? created.visibility : privacyMode;
        const createdAt = typeof created?.created_at === 'string' ? created.created_at : new Date().toISOString();
        const createdImage = typeof created?.image_url === 'string' ? created.image_url : null;
        const createdComments = typeof created?.comments_count === 'number' ? created.comments_count : 0;
        const createdShares = typeof created?.shares_count === 'number' ? created.shares_count : 0;
        const createdImpressions = typeof created?.impression_count === 'number' ? created.impression_count : 0;
        setPosts((prev) => [{ id: createdId, author: 'you', likes: createdLikes, caption: createdCaption, tags: createdTags, mentions: createdMentions, location: createdLocation, visibility: createdVisibility, created_at: createdAt, image_url: createdImage, comments_count: createdComments, shares_count: createdShares, impression_count: createdImpressions }, ...prev]);
        setDraftPost('');
        setStatusMessage('Post published and synced to backend feed.');
      }
    } catch (error) {
      console.error('Unable to create post', error);
      setStatusMessage(error instanceof Error ? error.message : 'Unable to create post now');
    } finally {
      setPosting(false);
    }
  };

  const handleLike = async (postId: string, tags: string[]) => {
    const currentlyLiked = likedPosts.includes(postId);
    setLikedPosts(currentlyLiked ? likedPosts.filter((id) => id !== postId) : [...likedPosts, postId]);
    setDislikedPosts((current) => current.filter((id) => id !== postId));
    setPosts((current) => current.map((post) => post.id === postId ? { ...post, likes: Math.max(0, post.likes + (currentlyLiked ? -1 : 1)) } : post));
    onInteraction(currentlyLiked ? 'Unlike Triggered' : 'Like Action Registered', tags.join(', '));
    try { await trackEvent(postId, currentlyLiked ? 'dislike' : 'like', { tags }); } catch { /* optimistic UI */ }
  };

  const handleDislike = async (postId: string) => {
    const currentlyDisliked = dislikedPosts.includes(postId);
    setDislikedPosts(currentlyDisliked ? dislikedPosts.filter((id) => id !== postId) : [...dislikedPosts, postId]);
    if (!currentlyDisliked) {
      setLikedPosts((current) => current.filter((id) => id !== postId));
      setPosts((current) => current.map((post) => post.id === postId ? { ...post, likes: Math.max(0, post.likes - 1) } : post));
    }
    try { await trackEvent(postId, 'dislike', { source: 'feed_action' }); onInteraction('Dislike Triggered', postId); } catch { /* optimistic UI */ }
  };

  const handleShare = async (postId: string) => {
    setPosts((current) => current.map((post) => post.id === postId ? { ...post, shares_count: (post.shares_count ?? 0) + 1 } : post));
    try { await trackEvent(postId, 'share', { destination: 'native_sheet' }); setStatusMessage('Post share event sent to recommendation pipeline.'); onInteraction('Share Triggered', postId); } catch (error) { setStatusMessage(error instanceof Error ? error.message : 'Unable to share now'); }
  };

  const handleComment = async (postId: string) => {
    const nextComment = (commentInputs[postId] || '').trim();
    if (!nextComment) return;
    try {
      await apiJson(`/api/posts/${postId}/comments`, { method: 'POST', body: JSON.stringify({ comment: nextComment }) });
      await trackEvent(postId, 'comment', { length: nextComment.length });
      setPosts((current) => current.map((post) => post.id === postId ? { ...post, comments_count: (post.comments_count ?? 0) + 1 } : post));
      setCommentInputs((current) => ({ ...current, [postId]: '' }));
      setStatusMessage('Comment posted and analytics event tracked.');
      onInteraction('Comment Added', postId);
    } catch (error) { setStatusMessage(error instanceof Error ? error.message : 'Unable to comment now'); }
  };

  return (
    <div style={{ maxWidth: '470px', margin: '0 auto', width: '100%', boxSizing: 'border-box', padding: '10px 0' }}>
      <form onSubmit={handleCreatePost} style={{ display: 'flex', gap: '8px', padding: '0 14px 12px' }}>
        <input type="text" value={draftPost} onChange={(event) => setDraftPost(event.target.value)} placeholder="Share a secure update..." style={{ flex: 1, padding: '10px 12px', borderRadius: '999px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', outline: 'none' }} />
        <button type="submit" disabled={posting} style={{ borderRadius: '999px', border: 'none', background: '#7c3aed', color: '#fff', padding: '10px 12px', cursor: 'pointer' }}>{posting ? 'Posting…' : 'Post'}</button>
      </form>
      <div style={{ display: 'flex', gap: '8px', padding: '0 14px 10px', flexWrap: 'wrap' }}>
        <button type="button" onClick={() => setFilter('all')} style={{ borderRadius: '999px', border: filter === 'all' ? '1px solid #7c3aed' : '1px solid #1f2937', background: filter === 'all' ? '#312e81' : '#0f172a', color: '#f8fafc', padding: '6px 10px', cursor: 'pointer' }}>All</button>
        <button type="button" onClick={() => setFilter('followers')} style={{ borderRadius: '999px', border: filter === 'followers' ? '1px solid #22c55e' : '1px solid #1f2937', background: filter === 'followers' ? '#14532d' : '#0f172a', color: '#f8fafc', padding: '6px 10px', cursor: 'pointer' }}>Followers</button>
        <button type="button" onClick={() => setFilter('private')} style={{ borderRadius: '999px', border: filter === 'private' ? '1px solid #f59e0b' : '1px solid #1f2937', background: filter === 'private' ? '#78350f' : '#0f172a', color: '#f8fafc', padding: '6px 10px', cursor: 'pointer' }}>Private</button>
      </div>
      {statusMessage ? <div style={{ color: '#7dd3fc', fontSize: '12px', padding: '0 14px 8px' }}>{statusMessage}</div> : null}
      {loading ? <div style={{ padding: '20px 14px', color: '#94a3b8' }}>Loading secure feed…</div> : null}
      {!loading && toggledPosts.length === 0 ? <div style={{ padding: '20px 14px', color: '#94a3b8' }}>No posts available for this filter.</div> : null}
      {toggledPosts.map((post) => (
        <article key={post.id} style={{ margin: '0 14px 12px', padding: '14px', border: '1px solid #1f2937', borderRadius: '18px', background: '#0b1220' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px' }}><strong style={{ color: '#f8fafc' }}>{post.author}</strong><span style={{ color: '#64748b', fontSize: '11px' }}>{post.visibility}</span></div>
          <p style={{ color: '#e2e8f0', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{post.caption}</p>
          {post.image_url ? <img src={post.image_url} alt="Post media" loading="lazy" style={{ width: '100%', borderRadius: '14px', maxHeight: '520px', objectFit: 'cover' }} /> : null}
          <div style={{ display: 'flex', gap: '8px', marginTop: '10px', flexWrap: 'wrap' }}>
            <button type="button" onClick={() => void handleLike(post.id, post.tags)}>Like {post.likes}</button>
            <button type="button" onClick={() => void handleDislike(post.id)}>Dislike</button>
            <button type="button" onClick={() => void handleShare(post.id)}>Share {post.shares_count ?? 0}</button>
          </div>
          <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
            <input value={commentInputs[post.id] ?? ''} onChange={(event) => setCommentInputs((current) => ({ ...current, [post.id]: event.target.value }))} maxLength={2000} placeholder="Add a comment" style={{ flex: 1, borderRadius: '999px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '8px 10px' }} />
            <button type="button" onClick={() => void handleComment(post.id)}>Send</button>
          </div>
        </article>
      ))}
      {!loading && toggledPosts.length > 0 ? <button type="button" disabled={loadingMore} onClick={() => void loadMore()} style={{ display: 'block', margin: '0 auto 20px' }}>{loadingMore ? 'Loading…' : 'Load more'}</button> : null}
    </div>
  );
}
