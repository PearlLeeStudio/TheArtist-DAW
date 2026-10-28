import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { Chord } from '../models/types.ts';
import { calculateRomanNumeral } from './romanNumeral.ts';

const chord = (root: string, quality = 'maj', bass?: string): Chord => ({
  root, quality, bass, extensions: [], voicing: [], romanNumeral: '',
});

test('C major analysis uses the chord quality for Roman case and seventh symbols', () => {
  const progression = [chord('C'), chord('D', 'min'), chord('E', 'min'), chord('F'),
    chord('G', '7'), chord('A', 'min'), chord('B', 'dim')];
  assert.deepEqual(progression.map((c) => calculateRomanNumeral(c, 'C major')),
    ['I', 'ii', 'iii', 'IV', 'V7', 'vi', 'vii°']);
});

test('the same unchanged chord is analyzed relative to the selected review key', () => {
  const c = chord('C');
  assert.equal(calculateRomanNumeral(c, 'C major'), 'I');
  assert.equal(calculateRomanNumeral(c, 'G major'), 'IV');
  assert.equal(calculateRomanNumeral(c, 'F major'), 'V');
  assert.equal(c.root, 'C');
});

test('borrowed and altered roots retain their written degree instead of the nearest pitch', () => {
  const roots = ['Bb', 'Eb', 'Ab', 'F#', 'Gb', 'C#', 'Db'];
  assert.deepEqual(roots.map((root) => calculateRomanNumeral(chord(root), 'C major')),
    ['bVII', 'bIII', 'bVI', '#IV', 'bV', '#I', 'bII']);
  assert.equal(calculateRomanNumeral(chord('F'), 'G major'), 'bVII');
  assert.equal(calculateRomanNumeral(chord('Ab'), 'Eb major'), 'IV');
});

test('minor keys retain their natural-minor degrees and minor extensions do not duplicate m', () => {
  const progression = [chord('A', 'min'), chord('B', 'dim'), chord('C'), chord('D', 'min'),
    chord('E', 'min'), chord('F'), chord('G')];
  assert.deepEqual(progression.map((c) => calculateRomanNumeral(c, 'A minor')),
    ['i', 'ii°', 'III', 'iv', 'v', 'VI', 'VII']);
  assert.equal(calculateRomanNumeral(chord('D', 'm11'), 'C major'), 'ii11');
  assert.equal(calculateRomanNumeral(chord('D', 'm13'), 'C major'), 'ii13');
});

test('slash bass and voicing do not change the harmonic root degree', () => {
  const inversion = { ...chord('C', 'maj', 'E'), voicing: [52, 55, 60] };
  assert.equal(calculateRomanNumeral(inversion, 'C major'), 'I');
  assert.equal(calculateRomanNumeral(chord('B', 'm7b5'), 'C major'), 'viiø7');
  assert.equal(calculateRomanNumeral(chord('H'), 'C major'), '?');
});
