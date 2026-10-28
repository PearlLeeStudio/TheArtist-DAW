import type { PlaySettings } from '../models/types.ts';
import { DRUM_PATTERNS } from '../engine/drumPatterns.ts';
import { DEFAULT_PLAY_SETTINGS, sanitizeVolume } from '../engine/playSettings.ts';

export type ResumeDrum = Pick<PlaySettings, 'drumMode' | 'drumPatternId'>;

/** UI-only restore values; they are not part of the saved song's audio settings. */
export interface PlayResumeState {
  lastHarmonyVolume: number;
  resumeDrum: ResumeDrum;
}

export interface PlayMuteState extends PlayResumeState {
  settings: PlaySettings;
}

const DRUM_IDS = new Set(DRUM_PATTERNS.map((pattern) => pattern.id));
const DEFAULT_DRUM: ResumeDrum = { drumMode: 'auto', drumPatternId: null };

function audibleVolume(value: unknown): number {
  const volume = sanitizeVolume(value, DEFAULT_PLAY_SETTINGS.harmonyVolume);
  return volume > 0 ? volume : DEFAULT_PLAY_SETTINGS.harmonyVolume;
}

function sanitizeResumeDrum(raw: unknown): ResumeDrum {
  const value = (typeof raw === 'object' && raw !== null ? raw : {}) as Record<string, unknown>;
  const validId = typeof value.drumPatternId === 'number' && DRUM_IDS.has(value.drumPatternId);
  if (value.drumMode === 'auto' && (value.drumPatternId === null || validId)) {
    return { drumMode: 'auto', drumPatternId: validId ? value.drumPatternId as number : null };
  }
  if (value.drumMode === 'manual' && validId) {
    return { drumMode: 'manual', drumPatternId: value.drumPatternId as number };
  }
  return { ...DEFAULT_DRUM };
}

function drumsEnabled(settings: PlaySettings): boolean {
  return settings.drumMode !== 'manual' || settings.drumPatternId !== null;
}

/** A project replacement passes no raw backup, so restore values cannot leak
 *  from the previously open project. Browser reload may restore validated prefs. */
export function playResumeState(settings: PlaySettings, raw?: unknown): PlayResumeState {
  const value = (typeof raw === 'object' && raw !== null ? raw : {}) as Record<string, unknown>;
  return {
    lastHarmonyVolume: settings.harmonyVolume > 0
      ? settings.harmonyVolume : audibleVolume(value.lastHarmonyVolume),
    resumeDrum: sanitizeResumeDrum(drumsEnabled(settings) ? settings : value.resumeDrum),
  };
}

export function setHarmonyEnabledState(state: PlayMuteState, on: boolean): PlayMuteState {
  if (on === (state.settings.harmonyVolume > 0)) return state;
  const lastHarmonyVolume = audibleVolume(on ? state.lastHarmonyVolume : state.settings.harmonyVolume);
  return {
    ...state, lastHarmonyVolume,
    settings: { ...state.settings, harmonyVolume: on ? lastHarmonyVolume : 0 },
  };
}

export function setHarmonyVolumeState(state: PlayMuteState, volume: number): PlayMuteState {
  const harmonyVolume = sanitizeVolume(volume, DEFAULT_PLAY_SETTINGS.harmonyVolume);
  if (harmonyVolume === state.settings.harmonyVolume) return state;
  return {
    ...state,
    lastHarmonyVolume: harmonyVolume > 0 ? harmonyVolume : state.lastHarmonyVolume,
    settings: { ...state.settings, harmonyVolume },
  };
}

export function setDrumsEnabledState(state: PlayMuteState, on: boolean): PlayMuteState {
  if (on === drumsEnabled(state.settings)) return state;
  const resumeDrum = sanitizeResumeDrum(on ? state.resumeDrum : state.settings);
  return {
    ...state, resumeDrum,
    settings: { ...state.settings, ...(on ? resumeDrum : { drumMode: 'manual', drumPatternId: null }) },
  };
}

export function setDrumAutoState(state: PlayMuteState): PlayMuteState {
  const resumeDrum = sanitizeResumeDrum({ drumMode: 'auto', drumPatternId: state.settings.drumPatternId });
  return { ...state, resumeDrum, settings: { ...state.settings, ...resumeDrum } };
}

export function setDrumPatternState(state: PlayMuteState, id: number | null): PlayMuteState {
  if (id === null) return setDrumsEnabledState(state, false);
  if (!DRUM_IDS.has(id)) return state;
  const resumeDrum: ResumeDrum = { drumMode: 'manual', drumPatternId: id };
  return { ...state, resumeDrum, settings: { ...state.settings, ...resumeDrum } };
}
