/**
 * Play-panel store: harmony instrument and comping rhythm, drums, bass,
 * visual mode and master/part levels, plus which pane is open. Persisted under
 * `theartist-play` and mirrored into the playback engine on every change —
 * whichever pane is mounted — so the next note that fires already uses it.
 * The separate Piano/Guitar display preference is saved without updating audio.
 * The engine resolves Auto against the editor song's genre, and re-syncs
 * when that genre changes.
 */
import { create } from 'zustand';
import type { PlaySettings, VisualMode } from '../models/types';
import {
  DEFAULT_PLAY_SETTINGS,
  enginePlayConfig,
  sanitizePlaySettings,
  sanitizeVolume,
} from '../engine/playSettings';
import { applyPlayConfig } from '../engine/playback';
import { useSongStore } from './songStore';
import {
  playResumeState,
  setDrumAutoState,
  setDrumPatternState,
  setDrumsEnabledState,
  setHarmonyEnabledState,
  setHarmonyVolumeState,
} from './playMuteState';
import type { PlayResumeState } from './playMuteState';

export type PlayPane = 'instrument' | 'rhythm' | 'drums';
export type VisualDisplayMode = 'piano' | 'guitar';
const PANES: PlayPane[] = ['instrument', 'rhythm', 'drums'];

const STORAGE_KEY = 'theartist-play';
/** The drum pick saved before the Play panel existed: an id, or 'null' (off). */
const LEGACY_DRUM_KEY = 'theartist-drum-pattern';

interface Persisted extends PlayResumeState {
  settings: PlaySettings;
  pane: PlayPane;
  displayMode: VisualDisplayMode;
}

function load(): Persisted {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as { settings?: unknown; pane?: unknown; displayMode?: unknown };
      const settings = sanitizePlaySettings(parsed.settings);
      return {
        settings,
        ...playResumeState(settings, parsed),
        pane: PANES.includes(parsed.pane as PlayPane) ? (parsed.pane as PlayPane) : 'instrument',
        displayMode: parsed.displayMode === 'piano' || parsed.displayMode === 'guitar'
          ? parsed.displayMode : settings.visualMode === 'guitar' ? 'guitar' : 'piano',
      };
    }
    // First load with the Play panel: keep a drum pick made before it.
    const legacy = localStorage.getItem(LEGACY_DRUM_KEY);
    if (legacy !== null) {
      const settings = sanitizePlaySettings({
        ...DEFAULT_PLAY_SETTINGS,
        drumMode: 'manual',
        drumPatternId: legacy === 'null' ? null : Number(legacy),
      });
      return {
        settings,
        ...playResumeState(settings),
        pane: 'instrument',
        displayMode: 'piano',
      };
    }
  } catch {
    // storage unavailable or corrupt — start from the defaults
  }
  return { settings: DEFAULT_PLAY_SETTINGS, ...playResumeState(DEFAULT_PLAY_SETTINGS), pane: 'instrument', displayMode: 'piano' };
}

interface PlayState extends PlayResumeState {
  settings: PlaySettings;
  pane: PlayPane;
  displayMode: VisualDisplayMode;

  setPane: (pane: PlayPane) => void;
  /** Drawing preference only; changing it does not reconfigure playback. */
  setDisplayMode: (mode: VisualDisplayMode) => void;
  /** A GM name from HARMONY_INSTRUMENTS; null = the genre default. */
  setHarmonyOverride: (name: string | null) => void;
  /** A HARMONY_RHYTHM_PRESETS id; null = Auto (the genre's rhythm). */
  setHarmonyRhythmId: (id: string | null) => void;
  /** Drums follow the song's genre. */
  setDrumAuto: () => void;
  /** Explicit off pauses drum scheduling; on restores its previous Auto/pattern. */
  setDrumsEnabled: (on: boolean) => void;
  /** A fixed drum pattern, or null for no drums; kept across genre changes. */
  setDrumPattern: (id: number | null) => void;
  setBassEnabled: (on: boolean) => void;
  /** Gain mute only; the instrument and rhythm choices stay intact. */
  setHarmonyEnabled: (on: boolean) => void;
  setVisualMode: (mode: VisualMode) => void;
  /** Live mixer gains, clamped to 0..1. */
  setMasterVolume: (volume: number) => void;
  setHarmonyVolume: (volume: number) => void;
  setBassVolume: (volume: number) => void;
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
    lastHarmonyVolume: initial.lastHarmonyVolume,
    resumeDrum: initial.resumeDrum,
    pane: initial.pane,
    displayMode: initial.displayMode,

    setPane: (pane) => set({ pane }),
    setDisplayMode: (displayMode) => set({ displayMode }),
    setHarmonyOverride: (harmonyOverride) => update({ harmonyOverride }),
    setHarmonyRhythmId: (harmonyRhythmId) => update({ harmonyRhythmId }),
    setDrumAuto: () => set(setDrumAutoState),
    setDrumsEnabled: (on) => set((state) => setDrumsEnabledState(state, on)),
    setDrumPattern: (id) => set((state) => setDrumPatternState(state, id)),
    setBassEnabled: (bassEnabled) => update({ bassEnabled }),
    setHarmonyEnabled: (on) => set((state) => setHarmonyEnabledState(state, on)),
    setVisualMode: (visualMode) => update({ visualMode }),
    setMasterVolume: (volume) => update({ masterVolume: sanitizeVolume(volume, DEFAULT_PLAY_SETTINGS.masterVolume) }),
    setHarmonyVolume: (volume) => set((state) => setHarmonyVolumeState(state, volume)),
    setBassVolume: (volume) => update({ bassVolume: sanitizeVolume(volume, DEFAULT_PLAY_SETTINGS.bassVolume) }),
    setDrumVolume: (volume) => update({ drumVolume: sanitizeVolume(volume, DEFAULT_PLAY_SETTINGS.drumVolume) }),
    replaceSettings: (raw) => {
      const settings = sanitizePlaySettings(raw);
      set({ settings, ...playResumeState(settings) });
    },
  };
});

function persist(state: Persisted): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      settings: state.settings, pane: state.pane, displayMode: state.displayMode,
      lastHarmonyVolume: state.lastHarmonyVolume, resumeDrum: state.resumeDrum,
    }));
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
  if (state.settings !== prev.settings || state.pane !== prev.pane || state.displayMode !== prev.displayMode
    || state.lastHarmonyVolume !== prev.lastHarmonyVolume || state.resumeDrum !== prev.resumeDrum) persist(state);
  if (state.settings !== prev.settings) applyEditorPlayConfig();
});

useSongStore.subscribe((state, prev) => {
  if (state.song.genre !== prev.song.genre) applyEditorPlayConfig();
});

applyEditorPlayConfig();
