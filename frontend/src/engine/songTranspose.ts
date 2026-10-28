import type { Chord, Song } from '../models/types.ts';
import { NOTE_VALUES, VALUE_TO_FLAT_NAME } from './constants.ts';
import { calculateRomanNumeral } from './romanNumeral.ts';
import { generatePianoVoicing } from './voicingEngine.ts';

const LETTERS = ['C', 'D', 'E', 'F', 'G', 'A', 'B'];

function transposeNote(note: string, semitones: number, letters: number): string {
  const pitch = NOTE_VALUES[note];
  if (pitch === undefined) return note;
  const nextPitch = (pitch + semitones) % 12;
  const letter = LETTERS[(LETTERS.indexOf(note[0]) + letters + 7) % 7];
  const spelled = [letter, `${letter}#`, `${letter}b`].find((name) => NOTE_VALUES[name] === nextPitch);
  // The editor/export contract supports single accidentals. Retain the
  // existing enharmonic fallback for a double-accidental spelling.
  return spelled ?? VALUE_TO_FLAT_NAME[nextPitch];
}

/** The existing Key control transposes the score, retaining note-letter
 *  relationships as well as pitch, so vii° does not become a flattened I. */
export function transposeSongKey(song: Song, key: string): Song {
  const oldRoot = song.key.split(' ')[0];
  const newRoot = key.split(' ')[0];
  const semitones = ((NOTE_VALUES[newRoot] ?? 0) - (NOTE_VALUES[oldRoot] ?? 0) + 12) % 12;
  const letters = (LETTERS.indexOf(newRoot[0]) - LETTERS.indexOf(oldRoot[0]) + 7) % 7;
  return {
    ...song,
    key,
    measures: song.measures.map((measure) => ({
      ...measure,
      chords: measure.chords.map((chord) => {
        if (!chord) return null;
        const transposed: Chord = {
          ...chord,
          root: transposeNote(chord.root, semitones, letters),
          ...(chord.bass ? { bass: transposeNote(chord.bass, semitones, letters) } : {}),
        };
        return {
          ...transposed,
          romanNumeral: calculateRomanNumeral(transposed, key),
          voicing: generatePianoVoicing(transposed),
        };
      }) as [Chord | null, Chord | null],
    })),
  };
}
