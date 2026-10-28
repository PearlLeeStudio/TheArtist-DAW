import * as Tone from 'tone';
import type { Song, SlotAddress, Chord, Arrangement } from '../models/types';
import { resolvePianoVoicing, generateGuitarVoicing } from './voicingEngine';
import { scheduleDrumMeasure, clearDrumSchedule, setCurrentDrumPattern, setDrumVolume, swingDelay } from './drums';
import { playChordOnInstrument, preloadInstruments } from './instruments';
import { scheduleBassSlot, setBassEnabled } from './arrangement';
import { getInstrumentOutput, setMixerVolumes } from './mixer';
import {
  HARMONY_GRID,
  autoRhythmPreset,
  genreHarmonyInstrument,
  harmonyStrikesForChords,
  secondsPerMeterBeat,
} from './playSettings';
import type { EnginePlayConfig, VoicingMode } from './playSettings';

// Live play state. Transport callbacks read these when a note fires, so the
// Play panel's instrument, rhythm, voicing, drum and bass changes are heard
// on the next strike without a reschedule. The editor store keeps them in
// sync (playStore.ts); MyPage applies a session's before it plays.

/**
 * User-picked GM instrument that replaces the genre's harmony default;
 * `null` falls back to the played song's genre (genreHarmonyInstrument).
 */
let harmonyOverride: string | null = null;
/** Picked comping rhythm (beat positions); `null` = the played song's genre
 *  rhythm, the plan's `override ?? GENRE_HARMONY_RHYTHM[genre] ?? Block`. */
let harmonyRhythmOverride: number[] | null = null;
/** Set by the first startPlayback(): from then on samples may load on a
 *  pick. Before it, loading would open the AudioContext ahead of a gesture,
 *  and startPlayback() preloads anyway. */
let audioStarted = false;
/** Genre of the song scheduled last; Auto's instrument is its default. */
let scheduledGenre: string | null = null;

export function setHarmonyOverride(name: string | null): void {
  if (name === harmonyOverride) return;
  harmonyOverride = name;
  // Fetch the samples as soon as the user picks the instrument (Auto: the
  // playing song's genre default), so a mid-playback swap has them ready by
  // the next trigger instead of dropping a few bars to the synth fallback.
  if (audioStarted) void preloadInstruments([name ?? genreHarmonyInstrument(scheduledGenre)]);
}

export function setHarmonyRhythmOverride(pattern: number[] | null): void {
  harmonyRhythmOverride = pattern;
}

/** Apply every Play-panel setting at once (playSettings.ts enginePlayConfig). */
export function applyPlayConfig(config: EnginePlayConfig): void {
  setMixerVolumes(config);
  setHarmonyOverride(config.harmonyOverride);
  setHarmonyRhythmOverride(config.harmonyRhythmOverride);
  currentInstrument = config.voicingMode;
  setCurrentDrumPattern(config.drumPatternId);
  setDrumVolume(config.drumVolume);
  setBassEnabled(config.bassEnabled);
}

/** Sampled instruments the current schedule needs; awaited by
 *  startPlayback(). Set by schedulePlayback(). */
let pendingHarmonyInstrument: string | null = null;
let pendingBassInstrument: string | null = null;
/** The schedule's harmony is the built-in piano (no genre, no pick), whose
 *  samples startPlayback() waits for as well. */
let pendingPiano = false;
/** Bumped by every schedule, stop and pause: a startPlayback() still waiting
 *  on samples sees the change and does not start. */
let scheduleGeneration = 0;

// Piano uses real Salamander Grand Piano samples (Yamaha C5, recorded by
// Alexander Holm, CC BY 3.0) hosted on tonejs.github.io. Sounds like an
// acoustic Steinway-class grand instead of the previous sine-wave
// PolySynth, which read as a thin EP. Sampler shares the same
// triggerAttackRelease/releaseAll API as PolySynth, so the rest of the
// pipeline doesn't need to know which one is in play.
let pianoSampler: Tone.Sampler | null = null;
let guitarSynth: Tone.PolySynth | null = null;
/** Keyboard or guitar voicing for the harmony layer, read per strike. */
let currentInstrument: VoicingMode = 'piano';
let scheduledEvents: number[] = [];
let isPlaying = false;
let isPaused = false;
/** The editor's Loop key. */
let loopEnabled = false;
/** The running schedule repeats while the Loop key is on (MyPage's do not). */
let scheduleFollowsLoop = true;
let currentMeasureIndex = 0;
let scheduledSlots: SlotAddress[] = [];
/** Where Transport time 0 sits in its bar (a selection may start on the
 *  second chord slot) and the bar length — for getPlaybackStep(). */
let scheduleStartBeat = 0;
let scheduleBeatsPerMeasure = 4;

type PositionCallback = (measureIndex: number, slotIndex: 0 | 1, chord: Chord | null) => void;
let positionCallback: PositionCallback | null = null;

function getPianoSynth(): Tone.Sampler {
  if (!pianoSampler) {
    // One sample every ~minor-third spans the keyboard; Tone.Sampler
    // pitch-shifts to fill the gaps. mp3 is small enough for fast first
    // decode while sounding broadly indistinguishable from the full set.
    pianoSampler = new Tone.Sampler({
      urls: {
        A0: 'A0.mp3',
        C1: 'C1.mp3',
        'D#1': 'Ds1.mp3',
        'F#1': 'Fs1.mp3',
        A1: 'A1.mp3',
        C2: 'C2.mp3',
        'D#2': 'Ds2.mp3',
        'F#2': 'Fs2.mp3',
        A2: 'A2.mp3',
        C3: 'C3.mp3',
        'D#3': 'Ds3.mp3',
        'F#3': 'Fs3.mp3',
        A3: 'A3.mp3',
        C4: 'C4.mp3',
        'D#4': 'Ds4.mp3',
        'F#4': 'Fs4.mp3',
        A4: 'A4.mp3',
        C5: 'C5.mp3',
        'D#5': 'Ds5.mp3',
        'F#5': 'Fs5.mp3',
        A5: 'A5.mp3',
        C6: 'C6.mp3',
        'D#6': 'Ds6.mp3',
        'F#6': 'Fs6.mp3',
        A6: 'A6.mp3',
        C7: 'C7.mp3',
        'D#7': 'Ds7.mp3',
        'F#7': 'Fs7.mp3',
        A7: 'A7.mp3',
        C8: 'C8.mp3',
      },
      baseUrl: 'https://tonejs.github.io/audio/salamander/',
      release: 1,
    }).connect(getInstrumentOutput('harmony'));
    pianoSampler.volume.value = -6;
  }
  return pianoSampler;
}

function getGuitarSynth(): Tone.PolySynth {
  if (!guitarSynth) {
    guitarSynth = new Tone.PolySynth(Tone.FMSynth, {
      harmonicity: 3.01,
      modulationIndex: 1.5,
      oscillator: { type: 'triangle' },
      modulation: { type: 'square' },
      envelope: {
        attack: 0.002,
        decay: 1.2,
        sustain: 0.0,
        release: 0.8,
      },
      modulationEnvelope: {
        attack: 0.002,
        decay: 0.4,
        sustain: 0.0,
        release: 0.5,
      },
    }).connect(getInstrumentOutput('harmony'));
    guitarSynth.volume.value = -8;
  }
  return guitarSynth;
}

/** Resolves once the built-in piano's samples are in, or after `timeoutMs`
 *  — like preloadInstruments(), a dead CDN still lets playback start. */
function pianoLoaded(timeoutMs = 8000): Promise<void> {
  if (getPianoSynth().loaded) return Promise.resolve();
  return Promise.race([
    Tone.loaded().then(() => undefined, () => undefined),
    new Promise<void>((resolve) => setTimeout(resolve, timeoutMs)),
  ]);
}

function midiToFreq(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12);
}

function clearSchedule(): void {
  scheduledEvents.forEach(id => Tone.getTransport().clear(id));
  scheduledEvents = [];
}

const OPEN_STRINGS = [40, 45, 50, 55, 59, 64];

/** MIDI notes for a chord in the live voicing mode (keyboard or guitar). */
function voiceChord(chord: Chord): number[] {
  if (currentInstrument === 'guitar') {
    return generateGuitarVoicing(chord)
      .map((f, i) => (f >= 0 ? OPEN_STRINGS[i] + f : -1))
      .filter((m) => m >= 0);
  }
  return resolvePianoVoicing(chord);
}

/** Strike a chord on the live harmony instrument (the pick, else the played
 *  song's genre default), falling back to the built-in piano/guitar synth
 *  while samples load so playback never goes silent. The built-in piano is
 *  sampled too: until it has loaded, the guitar synth stands in. */
function strikeChord(chord: Chord, genre: string | null, time: number, duration: number): void {
  const voicing = voiceChord(chord);
  const sfInstrument = harmonyOverride ?? genreHarmonyInstrument(genre);
  if (sfInstrument && playChordOnInstrument(sfInstrument, voicing, time, duration, 0.7)) return;
  const piano = currentInstrument === 'piano' ? getPianoSynth() : null;
  const synth = piano?.loaded ? piano : getGuitarSynth();
  try {
    synth.triggerAttackRelease(voicing.map(midiToFreq), duration, time);
  } catch (err) {
    console.warn('chord trigger failed:', err);
  }
}

// Fires when playback ends naturally (song completes without loop), so the
// UI can flip its play/pause icon back instead of showing "pause" over silence.
let endCallback: (() => void) | null = null;

/**
 * Schedule playback for specific measure ranges.
 * If slots is provided, only those slots play. Otherwise plays all measures.
 */
export function schedulePlayback(
  song: Song,
  onPosition: PositionCallback,
  slots?: SlotAddress[],
  /** Keyboard or guitar voicing; omitted = keep the applied play config. */
  instrument?: VoicingMode,
  onEnd?: () => void,
  /** Bass layer (computeArrangement, or a saved session's). Scheduled for
   *  every played chord slot; the Play panel's Bass key mutes it live.
   *  Omitted = harmony + drums only. */
  arrangement?: Arrangement,
  /** Repeat at the end while the editor's Loop key is on; false plays once. */
  followLoop = true,
): void {
  if (instrument) currentInstrument = instrument;
  stopPlayback();
  positionCallback = onPosition;
  endCallback = onEnd ?? null;
  scheduleFollowsLoop = followLoop;

  const bpm = song.bpm || 80;
  Tone.getTransport().bpm.value = bpm;

  const beatsPerMeasure = song.timeSignature[0];
  const beatsPerSlot = beatsPerMeasure / 2;
  const beatUnit = 4 / song.timeSignature[1];
  const secondsPerBeat = secondsPerMeterBeat(bpm, song.timeSignature[1]);
  const slotDuration = beatsPerSlot * secondsPerBeat;

  // Determine which slots to play
  if (slots && slots.length > 0) {
    scheduledSlots = slots;
  } else {
    scheduledSlots = [];
    for (let mi = 0; mi < song.measures.length; mi++) {
      scheduledSlots.push({ measureIndex: mi, slotIndex: 0 });
      scheduledSlots.push({ measureIndex: mi, slotIndex: 1 });
    }
  }
  scheduleStartBeat = (scheduledSlots[0]?.slotIndex ?? 0) * beatsPerSlot;
  scheduleBeatsPerMeasure = beatsPerMeasure;

  // The genre is read from the song at schedule time rather than from a
  // module-level global, which Vite HMR would reset to null. Its comping
  // rhythm plays unless the Play panel picked another one.
  const genre = song.genre;
  const genreRhythm = autoRhythmPreset(genre).pattern;
  scheduledGenre = genre;

  // Record which sampled instruments this schedule will reach for, so
  // startPlayback() can wait on their CDN samples before rolling the
  // Transport. Resolved here rather than at trigger time because the
  // Transport callback runs too late to await anything.
  const harmonyInstrument = harmonyOverride ?? genreHarmonyInstrument(genre);
  pendingHarmonyInstrument = harmonyInstrument;
  pendingBassInstrument = arrangement?.bassInstrument ?? null;
  pendingPiano = harmonyInstrument === null && currentInstrument === 'piano';

  let time = 0;
  const scheduledDrumMeasures = new Set<number>();

  for (const slot of scheduledSlots) {
    const measure = song.measures[slot.measureIndex];
    if (!measure) continue;
    const chord = measure.chords[slot.slotIndex];
    const slotTime = time;

    // Drums for each measure from the first of its slots played here: the
    // whole bar, or its second half when the schedule enters on slot 1.
    if (!scheduledDrumMeasures.has(slot.measureIndex)) {
      scheduleDrumMeasure(slotTime, secondsPerBeat, beatsPerMeasure, slot.slotIndex * beatsPerSlot * 4, beatUnit);
      scheduledDrumMeasures.add(slot.measureIndex);
    }

    // Position callback
    const eventId = Tone.getTransport().schedule(() => {
      currentMeasureIndex = slot.measureIndex;
      positionCallback?.(slot.measureIndex, slot.slotIndex, chord);
    }, slotTime);
    scheduledEvents.push(eventId);

    if (chord) {
      // Harmony: one event per HARMONY_GRID position inside this slot, plus
      // the slot's own start (where Block strikes in any meter). Each asks
      // the live rhythm (the pick, else the genre's) whether it strikes
      // there, so a rhythm switch is heard from the next grid position. A
      // strike lasts its harmonyStrikes() length at the tempo playing now.
      // Sparse rhythms add one boundary strike when a different second chord
      // would otherwise be omitted (also when previewing only that slot).
      const audibleChords = measure.chords.map((c, si) =>
        scheduledSlots.some((s) => s.measureIndex === slot.measureIndex && s.slotIndex === si) ? c : null,
      );
      const slotStartBeat = slot.slotIndex * beatsPerSlot;
      for (const pos of new Set([slotStartBeat, ...HARMONY_GRID])) {
        if (pos < slotStartBeat || pos >= slotStartBeat + beatsPerSlot) continue;
        const noteEventId = Tone.getTransport().schedule((t) => {
          const strike = harmonyStrikesForChords(harmonyRhythmOverride ?? genreRhythm, beatsPerMeasure, audibleChords)
            .find((s) => Math.abs(s.pos - pos) < 1e-9);
          if (!strike) return;
          // A swung "&" (drums.ts swingDelay) starts late and still ends on time.
          const delay = swingDelay(pos, beatUnit);
          strikeChord(chord, genre, t + delay, strike.dur * secondsPerMeterBeat(Tone.getTransport().bpm.value, song.timeSignature[1]) - delay);
        }, slotTime + (pos - slotStartBeat) * secondsPerBeat);
        scheduledEvents.push(noteEventId);
      }

      if (arrangement) {
        scheduleBassSlot(arrangement, chord, slot.slotIndex, slotTime, beatsPerMeasure, secondsPerBeat, scheduledEvents, beatUnit);
      }
    }

    time += slotDuration;
  }

  // End event — Tone v15 warns if scheduled callbacks call schedule-affecting
  // APIs (e.g. Transport.stop) without forwarding the passed-in `t`. Use the
  // precise scheduled time for the stop so timing stays sample-accurate.
  const endId = Tone.getTransport().schedule((t) => {
    if (loopEnabled && scheduleFollowsLoop) {
      Tone.getTransport().seconds = 0;
    } else {
      stopPlayback(t);
      if (scheduledSlots.length > 0) {
        positionCallback?.(scheduledSlots[0].measureIndex, 0, null);
      }
      // Notify caller that playback ended naturally (button icon sync).
      endCallback?.();
    }
  }, time);
  scheduledEvents.push(endId);
}

/**
 * Start the scheduled playback. Resolves true once the Transport rolls, or
 * false, without starting, when the schedule was replaced, stopped or
 * paused (cancelPendingStart) while it waited for audio and samples.
 */
export async function startPlayback(): Promise<boolean> {
  const generation = scheduleGeneration;
  await Tone.start();
  audioStarted = true;
  // Wait for the schedule's sampled instruments before rolling the
  // Transport, so bar 1 plays on the real instrument instead of the synth
  // fallback. Bounded internally — a 404 name or dead CDN still starts.
  await Promise.all([
    preloadInstruments([pendingHarmonyInstrument]),
    preloadInstruments([pendingBassInstrument], 8000, 'bass'),
    pendingPiano ? pianoLoaded() : undefined,
  ]);
  if (generation !== scheduleGeneration) return false;
  Tone.getTransport().start();
  isPlaying = true;
  isPaused = false;
  return true;
}

/** A startPlayback() still waiting on samples will not start. */
export function cancelPendingStart(): void {
  scheduleGeneration++;
}

/** Pause; a schedule that has not started yet stays paused at its start,
 *  so resumePlayback() plays it from there. */
export function pausePlayback(): void {
  cancelPendingStart();
  Tone.getTransport().pause();
  isPlaying = false;
  isPaused = true;
}

export function resumePlayback(): void {
  Tone.getTransport().start();
  isPlaying = true;
  isPaused = false;
}

export function stopPlayback(time?: number): void {
  // When called from inside a Transport callback, `time` should be the
  // scheduled-event time so Tone v15 doesn't warn about inaccurate timing.
  // External callers (UI buttons) pass nothing → undefined defers to "now".
  cancelPendingStart();
  Tone.getTransport().stop(time);
  Tone.getTransport().seconds = 0;
  clearSchedule();
  clearDrumSchedule();
  isPlaying = false;
  isPaused = false;
  currentMeasureIndex = 0;
}

export function getIsPlaying(): boolean {
  return isPlaying;
}

export function getIsPaused(): boolean {
  return isPaused;
}

export function setLoopEnabled(enabled: boolean): void {
  loopEnabled = enabled;
}

export function getLoopEnabled(): boolean {
  return loopEnabled;
}

export function getCurrentMeasureIndex(): number {
  return currentMeasureIndex;
}

/** The step of the bar playing now — a 16th by default — for the Play
 *  panel's LED playheads; null while stopped or paused. */
export function getPlaybackStep(stepsPerBeat = 4): number | null {
  if (!isPlaying) return null;
  const transport = Tone.getTransport();
  // The position being heard now: Transport.ticks reads a look-ahead (~0.1 s) ahead of it.
  const beat = transport.getTicksAtTime(Tone.immediate()) / transport.PPQ + scheduleStartBeat;
  const steps = Math.max(1, Math.round(scheduleBeatsPerMeasure * stepsPerBeat));
  return Math.floor(beat * stepsPerBeat) % steps;
}

export function setCurrentInstrument(instrument: VoicingMode): void {
  currentInstrument = instrument;
}

/** Update transport BPM live (takes effect for both playing and paused transport). */
export function setLiveBpm(bpm: number): void {
  Tone.getTransport().bpm.value = bpm;
}
