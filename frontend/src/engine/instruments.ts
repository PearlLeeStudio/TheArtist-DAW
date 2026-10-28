/**
 * Genre-aware instrument registry — Pearl 2026-05-09 Phase 2b.
 *
 * Lazy-loads smplr Soundfont instruments (FluidR3 GM samples on CDN) so each
 * 13-genre vocab entry can play its harmony layer with a genre-appropriate
 * instrument. Replaces the previous piano/guitar/vocal-only palette.
 *
 * Architecture:
 *   - One Soundfont instance per GM instrument name, lazy-loaded from
 *     gleitz/midi-js-soundfonts CDN (~100KB-1MB per instrument).
 *   - Shares Tone's AudioContext for unified scheduling with the rest of
 *     playback (drums, MIDI input, etc.).
 *   - Cold-load grace: if instrument not ready, callers should fall back
 *     to the existing Tone.js piano/guitar/vocal so playback never silences.
 *
 * Boundary (revised 2026-05-09):
 *   Artist owns the genre→instrument decision. Voyager only sends genre.
 *   GENRE_HARMONY_INSTRUMENT / GENRE_BASS_INSTRUMENT (genreTables.ts) are
 *   the authoritative maps for the harmony and bass layers.
 */
import * as Tone from 'tone';
import { Soundfont, SplendidGrandPiano, ElectricPiano } from 'smplr';
import { GENRE_BASS_INSTRUMENT, GENRE_HARMONY_INSTRUMENT } from './genreTables';

// The genre → instrument tables live in genreTables.ts (pure data).
export { GENRE_BASS_INSTRUMENT, GENRE_HARMONY_INSTRUMENT } from './genreTables';

/**
 * Pearl 2026-05-09 — Logic Pro 퀄리티 요청. Tier-1 (curated, high quality):
 *   acoustic_grand_piano → smplr.SplendidGrandPiano (Yamaha samples, Logic
 *                          Pro Steinway/Yamaha-class)
 *   electric_piano_1     → smplr.ElectricPiano (Rhodes samples)
 * Tier-2 (FluidR3_GM Soundfont — solid GM but not Logic Pro level):
 *   everything else (acoustic_guitar_steel, drawbar_organ, sax, etc.)
 *
 * For drums see drums.ts (smplr DrumMachine TR-808 + MuldjordKit acoustic).
 */
type InstrumentLike = {
  load: Promise<unknown>;
  start: (args: { note: number | string; velocity?: number; time?: number; duration?: number }) => unknown;
};
const registry: Record<string, { sf: InstrumentLike; ready: boolean }> = {};

function getAudioContext(): AudioContext {
  return Tone.getContext().rawContext as AudioContext;
}

/** Curated smplr classes for high-quality samples (Logic Pro-equivalent
 *  free options). Falls through to FluidR3 GM Soundfont for everything else.
 *
 *  Connects to audioCtx.destination by default (not Tone.getDestination().input
 *  which can throw "value with key not found" on some Tone v15 versions).
 */
function buildCuratedInstrument(name: string): InstrumentLike | null {
  const ctx = getAudioContext();
  if (name === 'acoustic_grand_piano') {
    return new SplendidGrandPiano(ctx) as unknown as InstrumentLike;
  }
  if (name === 'electric_piano_1') {
    // smplr's ElectricPiano accepts 'CP80' (no hyphen) — 'CP-80' throws.
    // Other valid names: PianetT, WurlitzerEP200, TX81Z.
    return new ElectricPiano(ctx, { instrument: 'CP80' }) as unknown as InstrumentLike;
  }
  return null;
}

/**
 * Load (or return cached) smplr Soundfont for a GM instrument name.
 * Names follow gleitz/midi-js-soundfonts convention: snake_case English
 * (e.g. "acoustic_grand_piano", "electric_piano_1", "alto_sax",
 * "acoustic_guitar_steel", "drawbar_organ"). A name outside FluidR3_GM's
 * 128-entry list 404s on the CDN and the instrument stays permanently
 * un-ready, i.e. silent — validate additions against
 * https://gleitz.github.io/midi-js-soundfonts/FluidR3_GM/names.json.
 */
export function getInstrument(name: string): InstrumentLike | null {
  if (!registry[name]) {
    try {
      // Try curated high-quality class first (SplendidGrandPiano,
      // ElectricPiano CP-80 etc. — closest free thing to Logic Pro
      // built-in samples). Falls back to FluidR3_GM Soundfont.
      let inst = buildCuratedInstrument(name);
      if (inst === null) {
        inst = new Soundfont(getAudioContext(), {
          instrument: name,
          kit: 'FluidR3_GM',
        }) as unknown as InstrumentLike;
      }
      registry[name] = { sf: inst, ready: false };
      inst.load.then(() => { registry[name].ready = true; })
        .catch((err) => console.warn(`Instrument '${name}' failed:`, err));
    } catch (err) {
      console.warn(`Instrument '${name}' init failed:`, err);
      return null;
    }
  }
  return registry[name].sf;
}

export function isInstrumentReady(name: string): boolean {
  return registry[name]?.ready ?? false;
}

/**
 * Warm the CDN samples for `names` and resolve once they are playable.
 *
 * Without this, playback starts the Transport immediately while the
 * Soundfont is still downloading, so `playChordOnInstrument` reports
 * not-ready and the opening bars fall through to the Tone.js synth —
 * audible as the first measures sounding thin or wrong before the real
 * instrument cuts in. Awaiting here makes the first bar sound like the
 * rest of the take.
 *
 * Never rejects and never blocks longer than `timeoutMs`: a 404 name or a
 * dead CDN degrades to the existing synth fallback rather than freezing
 * the play button.
 */
export function preloadInstruments(
  names: (string | null | undefined)[],
  timeoutMs = 8000,
): Promise<void> {
  const wanted = [...new Set(names.filter((n): n is string => !!n))];
  if (wanted.length === 0) return Promise.resolve();
  const loads = wanted.map((name) => {
    const inst = getInstrument(name);
    // getInstrument() already attached a .catch, so this .then chain only
    // has to swallow the rejection a second time for Promise.all's sake.
    return inst ? Promise.resolve(inst.load).then(() => undefined, () => undefined) : Promise.resolve();
  });
  return Promise.race([
    Promise.all(loads).then(() => undefined),
    new Promise<void>((resolve) => setTimeout(resolve, timeoutMs)),
  ]);
}

export function harmonyInstrumentForGenre(genre: string | null | undefined): string | null {
  if (!genre) return null;
  return GENRE_HARMONY_INSTRUMENT[genre.toLowerCase()] ?? null;
}

export function bassInstrumentForGenre(genre: string | null | undefined): string | null {
  if (!genre) return null;
  return GENRE_BASS_INSTRUMENT[genre.toLowerCase()] ?? null;
}

// Melody layer dropped 2026-05-10 — see arrangement.ts header for
// rationale. The Play panel's harmony instrument picker absorbs the
// variety role melody used to provide.

/**
 * Trigger a chord (one or more MIDI note numbers) on a specific GM instrument.
 * Returns true if the trigger fired through smplr; false if the instrument
 * isn't ready (caller should fall back to Tone.js synth so audio never silences).
 *
 * `time` is AudioContext seconds (matches what Tone.Transport.schedule passes
 * to its callback's first arg). `duration` is in seconds. `velocity` is 0-1.
 */
export function playChordOnInstrument(
  instrumentName: string,
  midiNotes: number[],
  time: number,
  duration: number,
  velocity: number = 1.0,
): boolean {
  const inst = getInstrument(instrumentName);
  if (!inst || !isInstrumentReady(instrumentName)) return false;
  const vel = Math.round(Math.max(0, Math.min(1, velocity)) * 127);
  for (const note of midiNotes) {
    inst.start({ note, velocity: vel, time, duration });
  }
  return true;
}
