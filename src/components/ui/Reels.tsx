import React, { useEffect, useRef, useState } from 'react';
import { apiJson, apiUpload } from '../../utils/socialApi';

type Reel = {
  id: string;
  user_id: string;
  video_url: string;
  media_url: string;
  caption: string;
  view_count: number;
  created_at: string;
};

export function Reels() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [reels, setReels] = useState<Reel[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [caption, setCaption] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  const loadReels = async () => {
    try {
      const result = await apiJson<{ reels: Reel[] }>('/api/reels?limit=20&offset=0');
      setReels(result.reels ?? []);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Unable to load reels');
    }
  };

  useEffect(() => { void loadReels(); }, []);

  const publish = async () => {
    if (!file) { setStatus('Choose a video first.'); return; }
    setBusy(true);
    setStatus('Uploading reel…');
    try {
      const uploaded = await apiUpload<{ path: string }>('/api/reels/upload', file);
      await apiJson('/api/reels', {
        method: 'POST',
        body: JSON.stringify({ media_path: uploaded.path, caption }),
      });
      setFile(null);
      setCaption('');
      if (inputRef.current) inputRef.current.value = '';
      setStatus('Reel published.');
      await loadReels();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Reel publish failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ flex: 1, backgroundColor: '#050505', minHeight: '70vh', padding: '18px' }}>
      <div style={{ maxWidth: '760px', margin: '0 auto' }}>
        <div style={{ border: '1px solid #222', borderRadius: '14px', padding: '14px', marginBottom: '16px' }}>
          <input ref={inputRef} type="file" accept="video/mp4,video/webm,video/quicktime" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <textarea value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Reel caption" maxLength={2200} style={{ width: '100%', marginTop: '10px', minHeight: '60px', boxSizing: 'border-box', background: '#111', color: '#fff', border: '1px solid #333', borderRadius: '8px', padding: '8px' }} />
          <button type="button" disabled={busy} onClick={() => void publish()} style={{ marginTop: '10px', padding: '9px 16px', border: 0, borderRadius: '8px', cursor: busy ? 'wait' : 'pointer' }}>
            {busy ? 'Publishing…' : 'Publish Reel'}
          </button>
          {status && <div style={{ marginTop: '8px', color: '#aaa', fontSize: '12px' }}>{status}</div>}
        </div>

        {reels.map((reel) => (
          <article key={reel.id} style={{ marginBottom: '18px', border: '1px solid #1d1d1d', borderRadius: '14px', overflow: 'hidden', background: '#090909' }}>
            <video controls playsInline preload="metadata" src={reel.media_url} onPlay={() => { void apiJson(`/api/reels/${reel.id}/view`, { method: 'POST' }); }} style={{ width: '100%', maxHeight: '78vh', display: 'block', background: '#000' }} />
            <div style={{ padding: '12px', color: '#fff' }}>
              <div style={{ fontSize: '13px', whiteSpace: 'pre-wrap' }}>{reel.caption}</div>
              <div style={{ marginTop: '6px', color: '#777', fontSize: '11px' }}>{reel.view_count} views</div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
