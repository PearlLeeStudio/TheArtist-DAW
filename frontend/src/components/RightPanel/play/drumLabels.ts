/** Key-cap labels for the Drums pane's pattern keys, by drum pattern id
 *  (engine/drumPatterns.ts DRUM_PATTERNS). Short enough for a 4-column grid. */
export const DRUM_KEY_LABELS: Record<number, string> = {
  1: 'Pop',
  2: 'HipHop',
  3: 'EDM',
  4: 'Swing',
  5: 'Bossa',
  6: 'Folk',
  7: 'Funk16',
  8: 'Shufl',
  9: 'Rock',
  10: 'FunkSh',
  11: 'Samba',
  12: 'Cntry',
  13: 'R&B',
  14: 'Gospl',
  15: 'Class',
};

/** The key label for a pattern id; the id itself for an unmapped pattern. */
export function drumKeyLabel(id: number): string {
  return DRUM_KEY_LABELS[id] ?? String(id);
}
