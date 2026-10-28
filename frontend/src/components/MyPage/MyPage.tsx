import { useEffect, useRef, useState } from 'react';
import { useSessionStore } from '../../store/sessionStore';
import { useSongStore } from '../../store/songStore';
import { useGenerationStore } from '../../store/generationStore';
import { usePlayStore } from '../../store/playStore';
import {
  buildExportSpec, downloadExportBlob, requestMidiExport, safeExportFilename,
} from '../../engine/exportSpec';
import {
  applyPlayConfig, schedulePlayback, startPlayback, stopPlayback, pausePlayback, resumePlayback,
} from '../../engine/playback';
import { computeArrangement } from '../../engine/arrangement';
import { enginePlayConfig, playSettingsFromSession, resolveVoicingMode } from '../../engine/playSettings';
import type { SavedSession } from '../../models/types';
import SessionStaff from './SessionStaff';

const buttonStyle = {
  background: 'var(--btn-bg)', color: 'var(--text-primary)', border: '1px solid var(--border)',
};
const primaryButtonStyle = { background: 'var(--text-heading)', color: 'var(--bg-primary)' };
const mutedStyle = { color: 'var(--text-muted)' };

interface SessionRowProps {
  session: SavedSession;
  activeSessionId: string | null;
  loadingSessionId: string | null;
  exportingId: string | null;
  isPaused: boolean;
  onTogglePlay: (session: SavedSession) => void;
  onOpen: (session: SavedSession) => void;
  onDelete: (session: SavedSession) => void;
  onFavorite: (session: SavedSession) => void;
  onExportMidi: (session: SavedSession) => void;
}

function SessionRow({
  session, activeSessionId, loadingSessionId, exportingId, isPaused,
  onTogglePlay, onOpen, onDelete, onFavorite, onExportMidi,
}: SessionRowProps) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const isActive = activeSessionId === session.id;
  const isLoading = loadingSessionId === session.id;
  const buttonLabel = isLoading ? 'Loading…' : !isActive ? '▶ Play' : isPaused ? '▶ Resume' : '⏸ Pause';
  const effectiveGenre = session.generation.genre ?? session.song.genre;
  const meta = [
    session.song.key, effectiveGenre?.replaceAll('_', ' '), `${session.song.bpm} BPM`,
    session.song.timeSignature.join('/'), `${session.song.measures.length} bars`,
  ].filter(Boolean).join(' · ');

  return (
    <article className="p-4 space-y-3" style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderLeft: session.starred ? '3px solid var(--brand-yellow)' : '1px solid var(--border)',
    }}>
      <div className="flex items-start gap-3 flex-wrap">
        <button onClick={() => onFavorite(session)} className="text-xl leading-none shrink-0 mt-1"
          style={{ color: session.starred ? 'var(--brand-yellow)' : 'var(--text-muted)', background: 'transparent' }}
          title={session.starred ? 'Remove from favorites' : 'Favorite for future inspiration'}
          aria-label={`${session.starred ? 'Unfavorite' : 'Favorite'} ${session.name}`} aria-pressed={session.starred}>
          {session.starred ? '★' : '☆'}
        </button>
        <div className="flex-1 min-w-40">
          <h3 className="font-display text-xl break-words" style={{ color: 'var(--text-heading)', fontWeight: 600 }}>
            {session.name}
          </h3>
          <div className="text-xs mt-1" style={mutedStyle}>{meta}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => onTogglePlay(session)} disabled={loadingSessionId !== null}
            className="px-3 py-2 text-xs font-bold disabled:opacity-50"
            style={isActive ? primaryButtonStyle : buttonStyle}
            title={!isActive ? 'Play with the instruments and levels saved in this project' : isPaused ? 'Resume playback' : 'Pause playback'}>
            {buttonLabel}
          </button>
          <button onClick={() => onOpen(session)} className="px-3 py-2 text-xs font-bold" style={primaryButtonStyle}
            title="Edit in the editor; current work is preserved in Projects first">Edit</button>
          <button onClick={() => onExportMidi(session)} disabled={exportingId !== null}
            className="px-3 py-2 text-xs disabled:opacity-50" style={buttonStyle}
            title="Download harmony, bass and drums as a MIDI file for your DAW">
            {exportingId === session.id ? 'Exporting…' : 'MIDI'}
          </button>
          <button onClick={() => onDelete(session)} className="px-3 py-2 text-xs" style={buttonStyle}>Delete</button>
        </div>
      </div>
      <details onToggle={(event) => setPreviewOpen(event.currentTarget.open)}>
        <summary className="text-xs cursor-pointer select-none" style={mutedStyle}>Preview score</summary>
        {previewOpen && (
          <div className="mt-3 overflow-x-auto" style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)' }}>
            <SessionStaff song={session.song} />
          </div>
        )}
      </details>
    </article>
  );
}

interface MyPageProps { onExitToEditor: () => void }
interface Notice { error: boolean; message: string }

export default function MyPage({ onExitToEditor }: MyPageProps) {
  const sessions = useSessionStore((state) => state.sessions);
  const mountedRef = useRef(true);
  const playSequence = useRef(0);
  const exportController = useRef<AbortController | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [loadingSessionId, setLoadingSessionId] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const starredCount = sessions.filter((session) => session.starred).length;

  useEffect(() => {
    mountedRef.current = true;
    playSequence.current++;
    return () => {
      mountedRef.current = false;
      exportController.current?.abort();
      stopPlayback();
    };
  }, []);

  const stopProjectPlayback = () => {
    playSequence.current++;
    stopPlayback();
    setActiveSessionId(null);
    setLoadingSessionId(null);
    setIsPaused(false);
  };

  const handleTogglePlay = async (session: SavedSession) => {
    setNotice(null);
    if (activeSessionId === session.id && !loadingSessionId) {
      try {
        if (isPaused) resumePlayback(); else pausePlayback();
        setIsPaused(!isPaused);
      } catch (error) {
        stopProjectPlayback();
        setNotice({ error: true, message: error instanceof Error ? error.message : 'Playback could not start. Please try again.' });
      }
      return;
    }
    const sequence = ++playSequence.current;
    stopPlayback();
    setActiveSessionId(session.id);
    setLoadingSessionId(session.id);
    setIsPaused(false);
    try {
      const effectiveGenre = session.generation.genre ?? session.song.genre ?? null;
      const settings = playSettingsFromSession(session.generation);
      const songForPlay = { ...session.song, genre: effectiveGenre };
      const stored = session.arrangement;
      const arrangement = stored && !Array.isArray(stored) && 'bassPattern' in stored
        ? stored : computeArrangement(songForPlay);
      applyPlayConfig(enginePlayConfig(settings, effectiveGenre));
      schedulePlayback(songForPlay, () => {}, undefined, resolveVoicingMode(settings, effectiveGenre), () => {
        if (mountedRef.current && sequence === playSequence.current) {
          setActiveSessionId(null);
          setIsPaused(false);
        }
      }, arrangement, false);
      const started = await startPlayback();
      if (mountedRef.current && sequence === playSequence.current && !started) {
        setActiveSessionId(null);
        setNotice({ error: true, message: 'Playback could not start. Press Play to try again.' });
      }
    } catch (error) {
      if (mountedRef.current && sequence === playSequence.current) {
        stopPlayback();
        setActiveSessionId(null);
        setNotice({ error: true, message: error instanceof Error ? error.message : 'Playback could not start. Please try again.' });
      }
    } finally {
      if (mountedRef.current && sequence === playSequence.current) setLoadingSessionId(null);
    }
  };

  const handleOpen = (session: SavedSession) => {
    // Keep the editor snapshot before replacing it. A failed browser save
    // throws before setSong, so the current score remains available.
    const current = useSongStore.getState().song;
    const model = useGenerationStore.getState().modelKey;
    const settings = usePlayStore.getState().settings;
    const currentJson = JSON.stringify(current);
    const settingsJson = JSON.stringify(settings);
    const alreadyKept = useSessionStore.getState().sessions.some((saved) =>
      JSON.stringify(saved.song) === currentJson && saved.generation.model === model &&
      JSON.stringify(playSettingsFromSession(saved.generation)) === settingsJson);
    try {
      if (!alreadyKept) {
        useSessionStore.getState().add(current, { model, genre: current.genre, ...settings }, current.title.trim() || 'Untitled');
      }
    } catch (error) {
      setNotice({ error: true, message: `Your current work could not be saved, so this project was not opened. ${
        error instanceof Error ? error.message : 'Check browser storage, then try again.'
      }` });
      return;
    }
    stopProjectPlayback();
    useSongStore.getState().setSong({ ...session.song, genre: session.generation.genre ?? session.song.genre ?? null });
    useGenerationStore.getState().setModelKey(session.generation.model);
    usePlayStore.getState().replaceSettings(playSettingsFromSession(session.generation));
    onExitToEditor();
  };

  const handleDelete = (session: SavedSession) => {
    if (!window.confirm(`Delete "${session.name}" from this browser?`)) return;
    try {
      useSessionStore.getState().remove(session.id);
      if (activeSessionId === session.id) stopProjectPlayback();
      setNotice({ error: false, message: `Deleted “${session.name}” from this browser.` });
    } catch (error) {
      setNotice({ error: true, message: error instanceof Error ? error.message : 'The project could not be deleted. Please try again.' });
    }
  };

  const handleFavorite = (session: SavedSession) => {
    try {
      useSessionStore.getState().toggleStar(session.id);
      setNotice(null);
    } catch (error) {
      setNotice({ error: true, message: error instanceof Error ? error.message : 'This change could not be saved. Please try again.' });
    }
  };

  const handleExportMidi = async (session: SavedSession) => {
    if (exportController.current) return;
    const controller = new AbortController();
    exportController.current = controller;
    setExportingId(session.id);
    setNotice(null);
    try {
      const song = { ...session.song, genre: session.generation.genre ?? session.song.genre ?? null };
      const spec = buildExportSpec(song, playSettingsFromSession(session.generation));
      const blob = await requestMidiExport(spec, controller.signal);
      if (!mountedRef.current || controller.signal.aborted) return;
      downloadExportBlob(blob, safeExportFilename(session.name, 'mid'));
      setNotice({ error: false, message: `MIDI download started for “${session.name}”.` });
    } catch (error) {
      if (mountedRef.current && !controller.signal.aborted) {
        setNotice({ error: true, message: error instanceof Error ? error.message : 'MIDI export failed. Please try again.' });
      }
    } finally {
      if (exportController.current === controller) exportController.current = null;
      if (mountedRef.current) setExportingId(null);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto p-6 space-y-5">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div className="max-w-xl">
            <h2 className="font-display text-3xl" style={{ color: 'var(--text-heading)', fontWeight: 700 }}>Projects</h2>
            <p className="text-sm mt-1" style={mutedStyle}>Recent work saved in this browser.</p>
          </div>
        </div>
        {notice && (
          <p role={notice.error ? 'alert' : 'status'} className="text-sm px-3 py-2" style={{
            color: 'var(--text-primary)',
            background: 'var(--bg-surface)', border: '1px solid var(--border)',
            borderLeft: notice.error ? '3px solid var(--brand-yellow)' : undefined,
          }}>{notice.message}</p>
        )}
        {sessions.length > 0 ? (
          <>
            <div className="flex justify-between flex-wrap gap-2 text-xs" style={mutedStyle}>
              <span>{sessions.length} saved{starredCount > 0 ? ` · ★ ${starredCount} favorites` : ''}</span>
              <span>Editing a project keeps unsaved editor work here first.</span>
            </div>
            <div className="space-y-3">
              {sessions.map((session) => (
                <SessionRow key={session.id} session={session} activeSessionId={activeSessionId}
                  loadingSessionId={loadingSessionId} exportingId={exportingId} isPaused={isPaused}
                  onTogglePlay={(item) => void handleTogglePlay(item)} onOpen={handleOpen}
                  onDelete={handleDelete} onFavorite={handleFavorite} onExportMidi={(item) => void handleExportMidi(item)} />
              ))}
            </div>
          </>
        ) : (
          <div className="py-16 text-center space-y-3" style={mutedStyle}>
            <p className="font-display text-2xl" style={{ color: 'var(--text-heading)' }}>Your next idea starts here.</p>
            <p className="text-sm">Save a sketch from the editor to keep it here.</p>
            <button onClick={onExitToEditor} className="px-4 py-2 text-xs font-bold" style={primaryButtonStyle}>Back to editor</button>
          </div>
        )}
      </div>
    </div>
  );
}
