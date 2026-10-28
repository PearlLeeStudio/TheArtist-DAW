/**
 * Play-panel transport, one row of keys: stop and go to start, back 4
 * measures, play/pause, forward 4 measures, loop, play the whole song.
 * Play follows the staff selection: it pauses while playing, resumes a
 * paused schedule while the selection and the score are unchanged, and
 * otherwise schedules the selection (or the whole song) afresh. Every
 * schedule carries the Play-panel settings, voicing and bass layer.
 */
import { useCallback, useState } from 'react';
import type { SlotAddress, Song } from '../../../models/types';
import { useSongStore } from '../../../store/songStore';
import { applyEditorPlayConfig, usePlayStore } from '../../../store/playStore';
import { computeArrangement } from '../../../engine/arrangement';
import { resolveVoicingMode } from '../../../engine/playSettings';
import {
  getIsPaused,
  getIsPlaying,
  getLoopEnabled,
  pausePlayback,
  resumePlayback,
  schedulePlayback,
  setLiveBpm,
  setLoopEnabled,
  startPlayback,
  stopPlayback,
} from '../../../engine/playback';
import KeyButton from './ui/KeyButton';

/** Measures the back and forward keys move. */
const JUMP = 4;

// Key widths: play/pause takes 2.4 shares of the row, the other five 1 each.
const COLUMNS = 'repeat(2, minmax(0, 1fr)) minmax(0, 2.4fr) repeat(3, minmax(0, 1fr))';

// Monochrome 16×16 glyphs in currentColor; play/pause draws a little larger.
const ICON = 14;
const MAIN_ICON = 16;

const GO_START_ICON = (
  <svg width={ICON} height={ICON} viewBox="0 0 16 16" fill="currentColor" aria-hidden>
    <rect x="2.5" y="3" width="2" height="10" rx="0.5" />
    <path d="M14 3v10L6 8l8-5z" />
  </svg>
);
const BACK_ICON = (
  <svg width={ICON} height={ICON} viewBox="0 0 16 16" fill="currentColor" aria-hidden>
    <path d="M9 3v10L1 8l8-5z" />
    <path d="M15 3v10L7 8l8-5z" />
  </svg>
);
const PLAY_ICON = (
  <svg width={MAIN_ICON} height={MAIN_ICON} viewBox="0 0 16 16" fill="currentColor" aria-hidden>
    <path d="M3.5 2.2v11.6L13.7 8 3.5 2.2z" />
  </svg>
);
const PAUSE_ICON = (
  <svg width={MAIN_ICON} height={MAIN_ICON} viewBox="0 0 16 16" fill="currentColor" aria-hidden>
    <rect x="3.5" y="2" width="3" height="12" rx="0.5" />
    <rect x="9.5" y="2" width="3" height="12" rx="0.5" />
  </svg>
);
const FORWARD_ICON = (
  <svg width={ICON} height={ICON} viewBox="0 0 16 16" fill="currentColor" aria-hidden>
    <path d="M1 3v10l8-5-8-5z" />
    <path d="M7 3v10l8-5-8-5z" />
  </svg>
);
const LOOP_ICON = (
  <svg
    width={ICON}
    height={ICON}
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
  >
    <path d="M13.2 8a5.2 5.2 0 1 1-1.4-3.6" />
    <polyline points="13.5,2 13.5,5 10.5,5" />
  </svg>
);
// Start bar + right triangle: plays from bar 1 (GO_START goes there silently).
const PLAY_FULL_ICON = (
  <svg width={ICON} height={ICON} viewBox="0 0 16 16" fill="currentColor" aria-hidden>
    <rect x="2" y="3" width="2" height="10" rx="0.5" />
    <path d="M5 3v10l8-5z" />
  </svg>
);

function songHasAnyChord(song: Song): boolean {
  return song.measures.some((m) => m.chords.some((c) => c !== null));
}

/** A selection as a comparable string; 'all' for the whole song. */
function slotsKey(slots: SlotAddress[] | undefined): string {
  return slots ? slots.map((s) => `${s.measureIndex}-${s.slotIndex}`).join(',') : 'all';
}

/** Every slot from `measureIndex` to the end of the song. */
function slotsFrom(song: Song, measureIndex: number): SlotAddress[] {
  const slots: SlotAddress[] = [];
  for (let mi = measureIndex; mi < song.measures.length; mi++) {
    slots.push({ measureIndex: mi, slotIndex: 0 }, { measureIndex: mi, slotIndex: 1 });
  }
  return slots;
}

/** A paused schedule still plays this score: same chords, genre and meter.
 *  Tempo is left out because the transport retimes it live. */
function sameScore(a: Song, b: Song): boolean {
  return a.measures === b.measures && a.genre === b.genre && a.timeSignature === b.timeSignature;
}

/** The selection key and song the running or paused schedule was built
 *  from. Module state like the engine's schedule, so a paused schedule
 *  still resumes after the Play panel unmounts and mounts again. */
let scheduled: { key: string; song: Song | null } = { key: '', song: null };

export default function Transport() {
  const song = useSongStore((s) => s.song);
  const selectedSlots = useSongStore((s) => s.selectedSlots);
  const playing = useSongStore((s) => s.isPlaying);
  const setPlaying = useSongStore((s) => s.setIsPlaying);
  const setPlaybackPosition = useSongStore((s) => s.setPlaybackPosition);
  const selectSlot = useSongStore((s) => s.selectSlot);
  const settings = usePlayStore((s) => s.settings);
  // The loop flag lives in the engine, which outlives this component.
  const [loop, setLoop] = useState(getLoopEnabled);

  const voicing = resolveVoicingMode(settings, song.genre);

  const onPosition = useCallback((measureIndex: number, slotIndex: 0 | 1) => {
    setPlaybackPosition({ measureIndex, slotIndex });
  }, [setPlaybackPosition]);

  // The end leaves no playhead, so the Visual pane and the back and
  // forward keys go back to the selection.
  const onEnd = useCallback(() => {
    setPlaying(false);
    setPlaybackPosition(null);
  }, [setPlaying, setPlaybackPosition]);

  /** Schedule `slots` (undefined = the whole song) without starting; `key`
   *  is the selection the main play key compares against to resume. */
  const schedule = useCallback((slots: SlotAddress[] | undefined, key: string) => {
    scheduled = { key, song };
    applyEditorPlayConfig();
    schedulePlayback(song, onPosition, slots, voicing, onEnd, computeArrangement(song));
  }, [song, onPosition, voicing, onEnd]);

  /** Schedule and start. A start called off while samples load (stop, pause,
   *  a new schedule or an edit) leaves the key showing play. */
  const play = useCallback((slots: SlotAddress[] | undefined, key: string) => {
    schedule(slots, key);
    startPlayback()
      .then((started) => { if (started) setPlaying(true); })
      .catch(() => setPlaying(false));
  }, [schedule, setPlaying]);

  // playing → pause; paused, nothing changed → resume; otherwise a fresh
  // schedule of the selection, or the whole song without one.
  const handlePlay = useCallback(() => {
    if (getIsPlaying()) {
      pausePlayback();
      setPlaying(false);
      return;
    }
    const slots = selectedSlots.length > 0 ? selectedSlots : undefined;
    const key = slotsKey(slots);
    const last = scheduled;
    if (getIsPaused() && key === last.key && last.song !== null && sameScore(last.song, song)) {
      applyEditorPlayConfig();
      setLiveBpm(song.bpm || 80);
      resumePlayback();
      setPlaying(true);
      return;
    }
    stopPlayback();
    if (!songHasAnyChord(song)) {
      setPlaying(false);
      setPlaybackPosition(null);
      return;
    }
    play(slots, key);
  }, [selectedSlots, song, play, setPlaying, setPlaybackPosition]);

  // Always from bar 1 of the whole song, whatever is selected. Keyed to the
  // selection as it stands, so pause and play resume the song.
  const handlePlayFullSong = useCallback(() => {
    stopPlayback();
    setPlaying(false);
    if (!songHasAnyChord(song)) {
      setPlaybackPosition(null);
      return;
    }
    play(undefined, slotsKey(selectedSlots.length > 0 ? selectedSlots : undefined));
  }, [song, selectedSlots, play, setPlaying, setPlaybackPosition]);

  const handleStop = useCallback(() => {
    stopPlayback();
    setPlaying(false);
    setPlaybackPosition(null);
  }, [setPlaying, setPlaybackPosition]);

  // Move the cursor `bars` measures from the playhead while one is playing
  // or paused, else from the selection. Playing: carry on from the new
  // measure. Paused: wait there, so play carries on from it to the end.
  const jump = useCallback((bars: number) => {
    const live = getIsPlaying() || getIsPaused();
    const playhead = live ? useSongStore.getState().playbackPosition : null;
    const from = playhead?.measureIndex ?? selectedSlots[0]?.measureIndex ?? 0;
    const target = Math.max(0, Math.min(song.measures.length - 1, from + bars));
    const cursor: SlotAddress = { measureIndex: target, slotIndex: 0 };
    selectSlot(cursor);
    if (!live) return;
    // Keyed to the cursor selection, so pause and play resume this schedule.
    if (getIsPlaying()) {
      stopPlayback();
      setPlaying(false);
      play(slotsFrom(song, target), slotsKey([cursor]));
      return;
    }
    schedule(slotsFrom(song, target), slotsKey([cursor]));
    pausePlayback();
    setPlaybackPosition(cursor);
  }, [selectedSlots, song, selectSlot, play, schedule, setPlaying, setPlaybackPosition]);

  const handleBack = useCallback(() => jump(-JUMP), [jump]);
  const handleForward = useCallback(() => jump(JUMP), [jump]);

  const handleLoop = useCallback(() => {
    const next = !loop;
    setLoop(next);
    setLoopEnabled(next);
  }, [loop]);

  const playTitle = playing
    ? 'Pause'
    : selectedSlots.length > 0
      ? `Play selection (${selectedSlots.length} slot${selectedSlots.length > 1 ? 's' : ''})`
      : 'Play full song';

  return (
    <div
      role="group"
      aria-label="Transport"
      className="shrink-0 grid gap-1"
      style={{ gridTemplateColumns: COLUMNS }}
    >
      <KeyButton size="md" onClick={handleStop} title="Stop and go to start" ariaLabel="Stop and go to start">
        {GO_START_ICON}
      </KeyButton>
      <KeyButton size="md" onClick={handleBack} title={`Back ${JUMP} measures`} ariaLabel={`Back ${JUMP} measures`}>
        {BACK_ICON}
      </KeyButton>
      <KeyButton
        size="md"
        onClick={handlePlay}
        title={playTitle}
        ariaLabel={playTitle}
        led={playing ? 'on' : 'off'}
      >
        {playing ? PAUSE_ICON : PLAY_ICON}
      </KeyButton>
      <KeyButton size="md" onClick={handleForward} title={`Forward ${JUMP} measures`} ariaLabel={`Forward ${JUMP} measures`}>
        {FORWARD_ICON}
      </KeyButton>
      <KeyButton
        size="md"
        onClick={handleLoop}
        title={loop ? 'Loop on' : 'Loop off'}
        ariaLabel="Loop"
        active={loop}
        led={loop ? 'on' : 'off'}
      >
        {LOOP_ICON}
      </KeyButton>
      <KeyButton
        size="md"
        onClick={handlePlayFullSong}
        title="Play full song (ignore selection)"
        ariaLabel="Play full song from the start"
      >
        {PLAY_FULL_ICON}
      </KeyButton>
    </div>
  );
}
