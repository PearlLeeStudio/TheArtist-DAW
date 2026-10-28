import type { Chord } from '../models/types';

export const HOLD_DURATION_MS = 3000;
export const PROGRESS_TICK_MS = 50;

export interface ConfirmState { candidates: Chord[]; activeIdx: number }
export interface MidiCaptureSnapshot {
  candidates: Chord[];
  activeIdx: number;
  holdProgress: number;
  confirming: ConfirmState | null;
  awaitingRelease: boolean;
}
export interface CaptureClock {
  now: () => number;
  setInterval: (callback: () => void, delay: number) => number;
  clearInterval: (id: number) => void;
}

/** Event-driven capture. Monitoring can publish live chords, but only an
 *  active input target can start a timer or commit. The clock is injectable
 *  so boundary changes are testable without a MIDI device or browser. */
export function createMidiCaptureState(options: {
  clock: CaptureClock;
  onCommit: (chord: Chord) => boolean;
  onCandidates: (chords: Chord[]) => void;
}) {
  let snapshot: MidiCaptureSnapshot = {
    candidates: [], activeIdx: 0, holdProgress: 0, confirming: null, awaitingRelease: false,
  };
  const listeners = new Set<() => void>();
  let captureActive = false;
  let target: string | null = null;
  let heldCount = 0;
  let peak: Chord[] = [];
  let committed = false;
  let timer: number | null = null;
  let holdStart = 0;
  let signature = '';

  const publish = (patch: Partial<MidiCaptureSnapshot>) => {
    const previous = snapshot;
    snapshot = { ...snapshot, ...patch };
    if (snapshot.candidates !== previous.candidates) options.onCandidates(snapshot.candidates);
    listeners.forEach((listener) => listener());
  };
  const stopTimer = () => {
    if (timer !== null) options.clock.clearInterval(timer);
    timer = null;
    signature = '';
  };
  const canCapture = () => captureActive && target !== null && !snapshot.awaitingRelease;
  const resetCapture = () => {
    stopTimer();
    peak = [];
    committed = false;
    publish({ activeIdx: 0, holdProgress: 0, confirming: null, awaitingRelease: heldCount > 0 });
  };
  const startTimer = (nextSignature: string) => {
    if (timer !== null && signature === nextSignature) return;
    stopTimer();
    signature = nextSignature;
    holdStart = options.clock.now();
    publish({ holdProgress: 0 });
    timer = options.clock.setInterval(() => {
      if (!canCapture() || committed || heldCount < 3) { stopTimer(); return; }
      const progress = Math.min(1, (options.clock.now() - holdStart) / HOLD_DURATION_MS);
      publish({ holdProgress: progress });
      if (progress < 1) return;
      stopTimer();
      const chords = snapshot.candidates;
      const chord = chords[Math.min(snapshot.activeIdx, chords.length - 1)];
      // A store write can advance the target and synchronously reset the
      // capture context. Keep this press committed until the full release.
      if (chord && options.onCommit(chord)) {
        committed = true;
        peak = [];
        publish({ candidates: [], activeIdx: 0, holdProgress: 0, confirming: null, awaitingRelease: true });
      } else resetCapture();
    }, PROGRESS_TICK_MS);
  };

  return {
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    setContext(active: boolean, nextTarget: string | null) {
      if (captureActive === active && target === nextTarget) return;
      captureActive = active;
      target = nextTarget;
      resetCapture();
    },
    notes(notes: number[]) {
      heldCount = notes.length;
      if (heldCount) {
        if (heldCount < 3) {
          stopTimer();
          publish({ candidates: [], activeIdx: 0, holdProgress: 0 });
        }
        return;
      }
      stopTimer();
      const confirming = canCapture() && !committed && peak.length
        ? { candidates: peak, activeIdx: Math.min(snapshot.activeIdx, peak.length - 1) } : snapshot.confirming;
      peak = [];
      committed = false;
      publish({ candidates: [], activeIdx: 0, holdProgress: 0, confirming, awaitingRelease: false });
    },
    detected(chords: Chord[]) {
      if (!chords.length) {
        stopTimer();
        publish({ candidates: [], activeIdx: 0, holdProgress: 0 });
        return;
      }
      if (committed) return;
      publish({ candidates: chords, activeIdx: 0 });
      if (!canCapture() || heldCount < 3) return;
      if ((chords[0].voicing?.length ?? 0) >= (peak[0]?.voicing?.length ?? 0)) peak = chords;
      publish({ confirming: null });
      startTimer(`${chords[0].root}:${chords[0].quality}:${chords[0].bass ?? ''}:${chords[0].voicing.join(',')}`);
    },
    choose(index: number) {
      if (Number.isInteger(index) && index >= 0 && index < snapshot.candidates.length) publish({ activeIdx: index });
    },
    chooseConfirm(index: number) {
      const confirming = snapshot.confirming;
      if (confirming && Number.isInteger(index) && index >= 0 && index < confirming.candidates.length) {
        publish({ confirming: { ...confirming, activeIdx: index } });
      }
    },
    confirm() {
      const confirming = snapshot.confirming;
      if (!canCapture() || !confirming) return;
      const chord = confirming.candidates[confirming.activeIdx] ?? confirming.candidates[0];
      if (chord) options.onCommit(chord);
      publish({ confirming: null });
    },
    cancel() { publish({ confirming: null }); },
    reset() {
      heldCount = 0;
      resetCapture();
      publish({ candidates: [] });
    },
    dispose() {
      stopTimer();
      peak = [];
      heldCount = 0;
      committed = false;
      snapshot = { candidates: [], activeIdx: 0, holdProgress: 0, confirming: null, awaitingRelease: false };
      listeners.clear();
    },
  };
}
