import React, { useEffect, useMemo, useRef, useState } from 'react';
import { apiJson, apiUpload } from '../../utils/socialApi';

type StoryItem = {
  id: string;
  user_id: string;
  username: string;
  media_name: string;
  media_type: string;
  caption: string;
  mentions: string[];
  location_name: string;
  music_track: string;
  overlay_text: string;
  overlay_emoji: string;
  overlay_x: number;
  overlay_y: number;
  overlay_scale: number;
  expires_at: string;
  viewers: string[];
};

type MentionCandidate = { id: string; username: string; display_name: string };

export function Stories({ username }: { username: string }) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [stories, setStories] = useState<StoryItem[]>([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [selectedMediaName, setSelectedMediaName] = useState('');
  const [selectedMediaFile, setSelectedMediaFile] = useState<File | null>(null);
  const [selectedMediaType, setSelectedMediaType] = useState<'image' | 'video'>('image');
  const [caption, setCaption] = useState('');
  const [musicSearch, setMusicSearch] = useState('');
  const [locationSearch, setLocationSearch] = useState('');
  const [mentionSearch, setMentionSearch] = useState('');
  const [musicOptions, setMusicOptions] = useState<string[]>([]);
  const [locationOptions, setLocationOptions] = useState<string[]>([]);
  const [mentionOptions, setMentionOptions] = useState<MentionCandidate[]>([]);
  const [selectedMentions, setSelectedMentions] = useState<string[]>([]);
  const [selectedMusicTrack, setSelectedMusicTrack] = useState('');
  const [selectedLocation, setSelectedLocation] = useState('');
  const [overlayText, setOverlayText] = useState('');
  const [overlayEmoji, setOverlayEmoji] = useState('');
  const [overlayX, setOverlayX] = useState(50);
  const [overlayY, setOverlayY] = useState(40);
  const [overlayScale, setOverlayScale] = useState(100);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  const loadStories = async () => {
    try {
      const response = await apiJson<{ success: boolean; stories: StoryItem[] }>('/api/stories/feed');
      setStories(response.stories ?? []);
    } catch {
      setStories([]);
    }
  };

  useEffect(() => {
    void loadStories();
  }, []);

  useEffect(() => {
    const loadSupportData = async () => {
      try {
        const [musicRes, locationRes, mentionRes] = await Promise.all([
          apiJson<{ success: boolean; tracks: string[] }>('/api/stories/music/search', { query: { q: musicSearch } }),
          apiJson<{ success: boolean; locations: string[] }>('/api/stories/location/search', { query: { q: locationSearch } }),
          apiJson<{ success: boolean; results: MentionCandidate[] }>('/api/stories/mentions', { query: { q: mentionSearch } }),
        ]);
        setMusicOptions(musicRes.tracks ?? []);
        setLocationOptions(locationRes.locations ?? []);
        setMentionOptions(mentionRes.results ?? []);
      } catch {
        setMusicOptions([]);
        setLocationOptions([]);
        setMentionOptions([]);
      }
    };

    if (!editorOpen) return;
    void loadSupportData();
  }, [editorOpen, musicSearch, locationSearch, mentionSearch]);

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const onMediaSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setSelectedMediaName(file.name);
    setSelectedMediaFile(file);
    setSelectedMediaType(file.type.startsWith('video') ? 'video' : 'image');
    setEditorOpen(true);
    setStatus('');
  };

  const editorPreview = useMemo(() => {
    if (!selectedMediaName) return 'No media selected';
    return `${selectedMediaType.toUpperCase()} • ${selectedMediaName}`;
  }, [selectedMediaName, selectedMediaType]);

  const publishStory = async () => {
    if (!selectedMediaName) {
      setStatus('Pick a media file first.');
      return;
    }
    setBusy(true);
    setStatus('Publishing story…');
    try {
      if (!selectedMediaFile) throw new Error('Selected media is no longer available. Please choose it again.');
      const upload = await apiUpload<{ success: boolean; path: string; media_type: 'image' | 'video' }>('/api/stories/upload', selectedMediaFile);
      await apiJson('/api/stories', {
        method: 'POST',
        body: JSON.stringify({
          media_name: upload.path,
          media_type: upload.media_type,
          caption,
          mentions: selectedMentions,
          location_name: selectedLocation,
          music_track: selectedMusicTrack,
          overlay_text: overlayText,
          overlay_emoji: overlayEmoji,
          overlay_x: overlayX / 100,
          overlay_y: overlayY / 100,
          overlay_scale: overlayScale / 100,
        }),
      });
      setStatus('Story published. It will auto-expire in 24 hours.');
      setEditorOpen(false);
      setSelectedMediaName('');
      setSelectedMediaFile(null);
      setCaption('');
      setSelectedMentions([]);
      setSelectedLocation('');
      setSelectedMusicTrack('');
      setOverlayText('');
      setOverlayEmoji('');
      void loadStories();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Story publish failed');
    } finally {
      setBusy(false);
    }
  };

  const markViewed = async (storyId: string) => {
    try {
      await apiJson(`/api/stories/${storyId}/view`, { method: 'POST' });
      void loadStories();
    } catch {
      // Ignore optimistic failures.
    }
  };

  return (
    <>
      <div style={{
        display: 'flex',
        gap: '16px',
        padding: '14px 16px',
        overflowX: 'auto',
        backgroundColor: '#000000',
        borderBottom: '1px solid #121212'
      }}>
        <input ref={fileInputRef} type="file" accept="image/*,video/*" style={{ display: 'none' }} onChange={onMediaSelected} />

        <button type="button" onClick={openFilePicker} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '5px', flexShrink: 0, border: 'none', background: 'transparent', cursor: 'pointer', color: '#fff' }}>
          <div style={{ width: '64px', height: '64px', borderRadius: '50%', backgroundColor: '#1a1a1a', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #262626' }}>
            <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#a855f7' }}>PFP</span>
            <div style={{
              position: 'absolute', bottom: '2px', right: '2px',
              width: '18px', height: '18px', borderRadius: '50%',
              backgroundColor: '#0095f6', display: 'flex', alignItems: 'center',
              justifyContent: 'center', border: '2px solid #000', fontSize: '12px', fontWeight: 'bold', color: '#fff'
            }}>+</div>
          </div>
          <span style={{ fontSize: '11px', color: '#8e8e8e' }}>Your Story</span>
        </button>

        {stories.map((story) => (
          <button key={story.id} type="button" onClick={() => void markViewed(story.id)} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '5px', flexShrink: 0, border: 'none', background: 'transparent', cursor: 'pointer', color: '#fff' }}>
            <div style={{ padding: '2px', borderRadius: '50%', background: 'linear-gradient(45deg, #f09433, #dc2743, #bc1888)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ width: '58px', height: '58px', borderRadius: '50%', backgroundColor: '#000000', border: '2px solid #000', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', color: '#a855f7', fontWeight: '600' }}>
                {story.media_type === 'video' ? 'VID' : 'IMG'}
              </div>
            </div>
            <span style={{ fontSize: '11px', color: '#f5f5f5', maxWidth: '66px', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{story.username}</span>
          </button>
        ))}
      </div>

      {editorOpen ? (
        <div style={{ position: 'fixed', inset: 0, zIndex: 250, background: 'rgba(2, 6, 23, 0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '12px' }}>
          <div style={{ width: '100%', maxWidth: '760px', maxHeight: '90vh', overflowY: 'auto', borderRadius: '20px', border: '1px solid #1f2937', background: '#020617', color: '#f8fafc', padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div>
                <div style={{ fontSize: '11px', color: '#38bdf8', textTransform: 'uppercase', letterSpacing: '0.16em' }}>Story Editor</div>
                <div style={{ fontSize: '17px', fontWeight: 700 }}>{editorPreview}</div>
              </div>
              <button type="button" onClick={() => setEditorOpen(false)} style={{ borderRadius: '999px', border: '1px solid #334155', background: 'transparent', color: '#f8fafc', padding: '8px 12px', cursor: 'pointer' }}>Close</button>
            </div>

            <div style={{ width: '100%', aspectRatio: '16/9', borderRadius: '16px', border: '1px solid #1f2937', background: 'linear-gradient(140deg, #0f172a, #1e293b)', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', marginBottom: '12px' }}>
              <div style={{ position: 'absolute', left: `${overlayX}%`, top: `${overlayY}%`, transform: `translate(-50%, -50%) scale(${overlayScale / 100})`, color: '#f8fafc', fontWeight: 700 }}>
                {overlayEmoji} {overlayText}
              </div>
              <span style={{ color: '#7dd3fc', fontSize: '13px' }}>[ {editorPreview} ]</span>
            </div>

            <textarea value={caption} onChange={(event) => setCaption(event.target.value)} placeholder="Story caption" style={{ width: '100%', minHeight: '70px', borderRadius: '12px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '10px', marginBottom: '10px', boxSizing: 'border-box' }} />

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px', marginBottom: '12px' }}>
              <div>
                <input value={musicSearch} onChange={(event) => setMusicSearch(event.target.value)} placeholder="Search music" style={{ width: '100%', borderRadius: '10px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '8px' }} />
                <select value={selectedMusicTrack} onChange={(event) => setSelectedMusicTrack(event.target.value)} style={{ width: '100%', marginTop: '6px', borderRadius: '10px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '8px' }}>
                  <option value="">Choose track</option>
                  {musicOptions.map((track) => <option key={track} value={track}>{track}</option>)}
                </select>
              </div>

              <div>
                <input value={locationSearch} onChange={(event) => setLocationSearch(event.target.value)} placeholder="Search location" style={{ width: '100%', borderRadius: '10px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '8px' }} />
                <select value={selectedLocation} onChange={(event) => setSelectedLocation(event.target.value)} style={{ width: '100%', marginTop: '6px', borderRadius: '10px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '8px' }}>
                  <option value="">Choose location</option>
                  {locationOptions.map((location) => <option key={location} value={location}>{location}</option>)}
                </select>
              </div>

              <div>
                <input value={mentionSearch} onChange={(event) => setMentionSearch(event.target.value)} placeholder="@mention users" style={{ width: '100%', borderRadius: '10px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '8px' }} />
                <select onChange={(event) => {
                  const nextMention = event.target.value;
                  if (!nextMention) return;
                  if (!selectedMentions.includes(nextMention)) {
                    setSelectedMentions((current) => [...current, nextMention]);
                  }
                  event.currentTarget.value = '';
                }} style={{ width: '100%', marginTop: '6px', borderRadius: '10px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '8px' }}>
                  <option value="">Choose mention</option>
                  {mentionOptions.map((user) => <option key={user.id} value={`@${user.username}`}>@{user.username}</option>)}
                </select>
                <div style={{ marginTop: '6px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {selectedMentions.map((mention) => <span key={mention} style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '999px', padding: '2px 7px', fontSize: '11px' }}>{mention}</span>)}
                </div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '10px' }}>
              <input value={overlayText} onChange={(event) => setOverlayText(event.target.value)} placeholder="Overlay text" style={{ borderRadius: '10px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '8px' }} />
              <input value={overlayEmoji} onChange={(event) => setOverlayEmoji(event.target.value)} placeholder="Emoji" style={{ borderRadius: '10px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '8px' }} />
            </div>

            <div style={{ marginBottom: '12px' }}>
              <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8' }}>Overlay X</label>
              <input type="range" min={5} max={95} value={overlayX} onChange={(event) => setOverlayX(Number(event.target.value))} style={{ width: '100%' }} />
              <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8' }}>Overlay Y</label>
              <input type="range" min={5} max={95} value={overlayY} onChange={(event) => setOverlayY(Number(event.target.value))} style={{ width: '100%' }} />
              <label style={{ display: 'block', fontSize: '12px', color: '#94a3b8' }}>Overlay Scale</label>
              <input type="range" min={60} max={170} value={overlayScale} onChange={(event) => setOverlayScale(Number(event.target.value))} style={{ width: '100%' }} />
            </div>

            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <button type="button" onClick={() => void publishStory()} disabled={busy} style={{ borderRadius: '999px', border: 'none', background: '#7c3aed', color: '#fff', padding: '10px 14px', cursor: 'pointer' }}>{busy ? 'Publishing…' : 'Publish Story'}</button>
              <button type="button" onClick={openFilePicker} style={{ borderRadius: '999px', border: '1px solid #334155', background: 'transparent', color: '#f8fafc', padding: '10px 14px', cursor: 'pointer' }}>Replace Media</button>
            </div>
            {status ? <div style={{ marginTop: '10px', color: '#7dd3fc', fontSize: '12px' }}>{status}</div> : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
