/**
 * Play-panel store: harmony instrument and comping rhythm, drums, bass,
 * visual mode and drum level, plus which pane is open. Persisted under
 * `theartist-play` and mirrored into the playback engine on every change —
 * whichever pane is mounted — so the next note that fires already uses it.
 * The engine resolves Auto against the editor song's genre, and re-syncs
 * when that genre changes.
 */
import { create } from 'zustand';
import type { PlaySettings, VisualMode } from '../models/types';
import {
  DEFAULT_PLAY_SETTINGS,
  enginePlayConfig,
  sanitizePlaySettings,
} from '../engine/playSettings';
import { applyPlayConfig } from '../engine/playback';
import { useSongStore } from './songStore';

export type PlayPane = 'visual' | 'instrument' | 'rhythm' | 'drums';
const PANES: PlayPane[] = ['visual', 'instrument', 'rhythm', 'drums'];

const STORAGE_KEY = 'theartist-play';
/** The drum pick saved before the Play panel existed: an id, or 'null' (off). */
const LEGACY_DRUM_KEY = 'theartist-drum-pattern';

interface Persisted {
  settings: PlaySettings;
  pane: PlayPane;
}

function load(): Persisted {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as { settings?: unknown; pane?: unknown };
      return {
        settings: sanitizePlaySettings(parsed.settings),
        pane: PANES.includes(parsed.pane as PlayPane) ? (parsed.pane as PlayPane) : 'visual',
      };
    }
    // First load with the Play panel: keep a drum pick made before it.
    const legacy = localStorage.getItem(LEGACY_DRUM_KEY);
    if (legacy !== null) {
      return {
        settings: sanitizePlaySettings({
          ...DEFAULT_PLAY_SETTINGS,
          drumMode: 'manual',
          drumPatternId: legacy === 'null' ? null : Number(legacy),
        }),
        pane: 'visual',
      };
    }
  } catch {
    // storage unavailable or corrupt — start from the defaults
  }
  return { settings: DEFAULT_PLAY_SETTINGS, pane: 'visual' };
}

interface PlayState {
  settings: PlaySettings;
  pane: PlayPane;

  setPane: (pane: PlayPane) => void;
  /** A GM name from HARMONY_INSTRUMENTS; null = the genre default. */
  setHarmonyOverride: (name: string | null) => void;
  /** A HARMONY_RHYTHM_PRESETS id; null = Auto (the genre's rhythm). */
  setHarmonyRhythmId: (id: string | null) => void;
  /** Drums follow the song's genre. */
  setDrumAuto: () => void;
  /** A fixed drum pattern, or null for no drums; kept across genre changes. */
  setDrumPattern: (id: number | null) => void;
  setBassEnabled: (on: boolean) => void;
  setVisualMode: (mode: VisualMode) => void;
  /** Drum bus gain, clamped to 0..1. */
  setDrumVolume: (volume: number) => void;
  /** Replace every setting at once (MyPage Load restores a session's). */
  replaceSettings: (settings: PlaySettings) => void;
}

const initial = load();

export const usePlayStore = create<PlayState>((set) => {
  const update = (patch: Partial<PlaySettings>) =>
    set((state) => ({ settings: { ...state.settings, ...patch } }));
  return {
    settings: initial.settings,
    pane: initial.pane,

    setPane: (pane) => set({ pane }),
    setHarmonyOverride: (harmonyOverride) => update({ harmonyOverride }),
    setHarmonyRhythmId: (harmonyRhythmId) => update({ harmonyRhythmId }),
    setDrumAuto: () => update({ drumMode: 'auto' }),
    setDrumPattern: (drumPatternId) => update({ drumMode: 'manual', drumPatternId }),
    setBassEnabled: (bassEnabled) => update({ bassEnabled }),
    setVisualMode: (visualMode) => update({ visualMode }),
    setDrumVolume: (volume) => update({ drumVolume: Math.max(0, Math.min(1, volume)) }),
    replaceSettings: (settings) => set({ settings: sanitizePlaySettings(settings) }),
  };
});

function persist(state: Persisted): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ settings: state.settings, pane: state.pane }));
  } catch {
    // quota or disabled storage — the in-memory settings still apply
  }
}

/**
 * Put the editor's play settings, resolved against the editor song's
 * genre, into the playback engine. Runs on every change; the editor
 * transport also calls it before it schedules, because MyPage applies a
 * saved session's settings to the same engine.
 */
export function applyEditorPlayConfig(): void {
  applyPlayConfig(enginePlayConfig(usePlayStore.getState().settings, useSongStore.getState().song.genre));
}

usePlayStore.subscribe((state, prev) => {
  if (state.settings !== prev.settings || state.pane !== prev.pane) persist(state);
  if (state.settings !== prev.settings) applyEditorPlayConfig();
});

useSongStore.subscribe((state, prev) => {
  if (state.song.genre !== prev.song.genre) applyEditorPlayConfig();
});

applyEditorPlayConfig();
