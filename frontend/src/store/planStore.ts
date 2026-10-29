/**
 * PlanStore — one "Complete the form" run at a time: its chips as the
 * stream reports them, the planned sections, the spend so far and the
 * trace, then Apply / Undo on the staff.
 *
 * Nothing touches the song until applyPlan: a run that fails or is
 * cancelled leaves the score as it was. Apply appends every planned
 * section's first suggestion through the song-form section APIs the
 * section flow uses (placeSection, setChords, commitSection), after a
 * snapshot that undoPlan restores with setSong.
 */
import { create } from 'zustand';
import type { Song } from '../models/types';
import { parseSuggestionChords } from '../engine/chordGenerator';
import type { TargetChord } from '../engine/generationComparison';
import {
  buildPlanRequest,
  runPlan,
  type PlanEvent,
  type PlanOptions,
  type PlanSectionResult,
  type PlanTrace,
  type PlannerKind,
} from '../engine/planClient';
import { CHORDS_PER_BAR, sectionLabel } from '../engine/songForm';
import { useSongStore } from './songStore';

export type PlanStatus = 'idle' | 'running' | 'done' | 'failed';
export type PlanChipStep = 'plan' | 'validate' | 'revise' | 'generate_section' | 'judge' | 'error';
/** Who did the step: Muse Spark, the author's chord model, or the rules. */
export type PlanChipBadge = 'Muse Spark plan' | 'own model' | 'rules';

/** One step of the run as the band shows it, in run order. */
export interface PlanChip {
  step: PlanChipStep;
  ok: boolean;
  label: string;
  badge: PlanChipBadge | null;
  /** 'cadence: rules (n)' for a section with slots the song-form rules wrote. */
  note: string | null;
  latencyMs: number | null;
  costUsd: number | null;
  requestId: string | null;
  /** Details for the tooltip: the plan, the validator's issues, a reason, the failure. */
  message: string | null;
}

interface PlanState {
  status: PlanStatus;
  planner: PlannerKind | null;
  chips: PlanChip[];
  /** The generated sections by plan index; a regeneration replaces its entry. */
  sections: PlanSectionResult[];
  spendUsd: number;
  error: string | null;
  /** The terminal frame's trace (also of a failed run), for Export trace. */
  trace: PlanTrace | null;
  applied: boolean;
  /** The song before Apply; undoPlan restores it. */
  snapshot: Song | null;
  /** Id of the newest run; events and results of older runs are ignored. */
  runId: number;

  /** Start a run for the current song; a run in flight is aborted first. */
  startPlan: (options: PlanOptions) => Promise<void>;
  /** Abort the run in flight and hide the band; the song is untouched. */
  cancelPlan: () => void;
  /** Append every planned section's first suggestion to the song, in order. */
  applyPlan: () => void;
  /** Restore the song from before Apply. */
  undoPlan: () => void;
  /** The trace as JSON, or null before a terminal frame arrived. */
  exportTrace: () => string | null;
  /** Hide the band (cancelling a run in flight); applied sections stay. */
  dismiss: () => void;
}

/** Store fields of no run at all. */
function idleState(): Pick<PlanState, 'status' | 'planner' | 'chips' | 'sections' | 'spendUsd' | 'error' | 'trace' | 'applied' | 'snapshot'> {
  return {
    status: 'idle', planner: null, chips: [], sections: [], spendUsd: 0, error: null, trace: null,
    applied: false, snapshot: null,
  };
}

/** 'chorus 8 (authentic) · verse 8 (half)': the plan as one line. */
function planSummary(event: Extract<PlanEvent, { event: 'plan' | 'revise' }>['data']): string {
  return event.plan.sections.map((s) => `${s.type} ${s.bars} (${s.cadence})`).join(' · ');
}

function sectionChip(section: PlanSectionResult): PlanChip {
  const rules = section.rulesSlots.length;
  return {
    step: 'generate_section',
    ok: true,
    label: `${sectionLabel(section.sectionType)} · ${section.bars} bars${section.regenerated ? ' · regenerated' : ''}`,
    // The backend's rule-based generator answers as 'rules' when the model is unavailable.
    badge: section.source === 'ai' ? 'own model' : 'rules',
    note: rules > 0 ? `cadence: rules (${rules})` : null,
    latencyMs: null,
    costUsd: null,
    requestId: null,
    message: [section.modelUsed ? `model ${section.modelUsed}` : null, section.cadence ? `cadence ${section.cadence}` : null, section.reason || null]
      .filter(Boolean).join(' · ') || null,
  };
}

/** The chip for one stream event, or null for the terminal frames. */
function chipFor(event: PlanEvent): PlanChip | null {
  switch (event.event) {
    case 'plan':
    case 'revise': {
      const { call, source, attempt } = event.data;
      return {
        step: event.event,
        ok: true,
        label: event.event === 'plan' ? 'plan' : `revise ${attempt}`,
        badge: source === 'meta' ? 'Muse Spark plan' : 'rules',
        note: null,
        latencyMs: call?.latencyMs ?? null,
        costUsd: call?.costUsd ?? null,
        requestId: call?.requestId ?? null,
        message: [call ? `${call.provider} ${call.model}` : null, planSummary(event.data)].filter(Boolean).join(' · '),
      };
    }
    case 'validate': {
      const { ok, errors } = event.data;
      return {
        step: 'validate',
        ok,
        label: ok ? 'validate ok' : `validate failed (${errors.length})`,
        badge: null,
        note: null,
        latencyMs: null,
        costUsd: null,
        requestId: null,
        message: errors.length ? errors.map((issue) => `${issue.code}: ${issue.message}`).join('; ') : null,
      };
    }
    case 'generate_section':
      return sectionChip(event.data);
    case 'judge': {
      const { decision, targets, provider, model, latencyMs, costUsd, requestId } = event.data;
      return {
        step: 'judge',
        ok: true,
        label: `judge: ${decision}${targets.length ? ` (${targets.length})` : ''}`,
        badge: null,
        note: null,
        latencyMs,
        costUsd,
        requestId,
        message: [`${provider} ${model}`, ...targets.map((t) => `section ${t.section + 1}: ${t.reason}`)].join(' · '),
      };
    }
    default:
      return null;
  }
}

/** The red chip of a failed run. */
function errorChip(label: string, message: string, requestId: string | null = null): PlanChip {
  return { step: 'error', ok: false, label, badge: null, note: null, latencyMs: null, costUsd: null, requestId, message };
}

/** The section's chords, re-keyed from the server's absolute measure
 *  indices to where placeSection put the section. */
function sectionUpdates(section: PlanSectionResult, startMeasure: number): TargetChord[] {
  const suggestion = section.suggestions[0];
  if (!suggestion) return [];
  const chords = parseSuggestionChords(suggestion);
  const updates: TargetChord[] = [];
  for (let bar = 0; bar < section.bars; bar++) {
    for (let slot = 0; slot < CHORDS_PER_BAR; slot++) {
      const chord = chords.get(`${section.startMeasure + bar}-${slot}`);
      if (chord) updates.push({ address: { measureIndex: startMeasure + bar, slotIndex: slot as 0 | 1 }, chord });
    }
  }
  return updates;
}

/** Module-level because it is not UI state. */
let controller: AbortController | null = null;
/** True while undoPlan replaces the song: that epoch bump is the plan's own. */
let restoringSnapshot = false;

export const usePlanStore = create<PlanState>((set, get) => {
  const isCurrent = (runId: number) => get().runId === runId;

  const onEventFor = (runId: number) => (event: PlanEvent) => {
    if (!isCurrent(runId)) return;
    const chip = chipFor(event);
    if (!chip) return;
    set((state) => {
      const sections = [...state.sections];
      if (event.event === 'generate_section') sections[event.data.index] = event.data;
      return { chips: [...state.chips, chip], sections, spendUsd: state.spendUsd + (chip.costUsd ?? 0) };
    });
  };

  return {
    ...idleState(),
    runId: 0,

    startPlan: async (options) => {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      const runId = get().runId + 1;
      set({ ...idleState(), runId, status: 'running', planner: options.planner });
      try {
        const request = buildPlanRequest(useSongStore.getState().song, options);
        const trace = await runPlan(request, { signal: current.signal, onEvent: onEventFor(runId) });
        if (!isCurrent(runId)) return;
        if (trace.status === 'ok') {
          set({ status: 'done', sections: trace.sections, spendUsd: trace.spendUsd, trace });
        } else {
          const failure = trace.error;
          const label = failure ? `failed: ${failure.kind}` : 'failed';
          const message = failure?.message ?? 'The run failed';
          set((state) => ({
            status: 'failed', error: message, spendUsd: trace.spendUsd, trace,
            chips: [...state.chips, errorChip(label, message, failure?.requestId ?? null)],
          }));
        }
      } catch (err) {
        if (!isCurrent(runId) || current.signal.aborted) return;
        const message = err instanceof Error ? err.message : String(err);
        set((state) => ({ status: 'failed', error: message, chips: [...state.chips, errorChip('failed', message)] }));
      } finally {
        if (controller === current) controller = null;
      }
    },

    cancelPlan: () => {
      controller?.abort();
      controller = null;
      set((state) => ({ ...idleState(), runId: state.runId + 1 }));
    },

    applyPlan: () => {
      const { status, sections, applied } = get();
      if (status !== 'done' || applied || sections.length === 0) return;
      const { song, placeSection, setChords, commitSection } = useSongStore.getState();
      const snapshot = structuredClone(song);
      for (const section of sections) {
        // After the last used measure, so the sections follow each other.
        const placed = placeSection(section.sectionType, section.bars);
        const updates = sectionUpdates(section, placed.startMeasure);
        if (updates.length > 0) setChords(updates);
        // Its chords landed, so a reload keeps the section.
        commitSection(placed.id);
      }
      set({ applied: true, snapshot });
    },

    undoPlan: () => {
      const { applied, snapshot } = get();
      if (!applied || !snapshot) return;
      // setSong replaces the whole song; the import undo it would clear is unrelated to this plan
      const { previousImportSong } = useSongStore.getState();
      restoringSnapshot = true;
      try {
        useSongStore.getState().setSong(snapshot);
      } finally {
        restoringSnapshot = false;
      }
      useSongStore.setState({ previousImportSong });
      set({ applied: false, snapshot: null });
    },

    exportTrace: () => {
      const trace = get().trace;
      return trace ? JSON.stringify(trace, null, 2) : null;
    },

    dismiss: () => {
      if (get().status === 'running') {
        get().cancelPlan();
        return;
      }
      set(idleState());
    },
  };
});

// A replaced song (Initialize, Load, Import) is not the sketch the plan was
// made for: drop the run, in flight or done, as generationStore drops its
// suggestions. undoPlan's own replacement is the exception.
useSongStore.subscribe((state, prev) => {
  if (state.songEpoch === prev.songEpoch || restoringSnapshot) return;
  if (usePlanStore.getState().status !== 'idle') usePlanStore.getState().dismiss();
});
