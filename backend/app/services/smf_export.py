"""Deterministic type-1 MIDI export of the editor's actual two-slot voicings."""

import io
import math
import re
import threading
import unicodedata
from dataclasses import dataclass

import mido

from app.models.export import MAX_EXPORT_BYTES, MAX_EXPORT_NOTES, NOTE_PC, ExportSpec
from app.services.genre_tables import (
    DRUM_PATTERNS, DRUM_VOICE_TO_GM_NOTE, GM_PROGRAM, bass_instrument, bass_pattern,
    genre_drum_pattern_id, harmony_instrument, harmony_pattern, harmony_rhythm_preset,
    harmony_strikes,
)

PPQ = 480
_MIDI_CHARSET_LOCK = threading.Lock()  # mido's text charset is process-global while saving
_MAJOR_KEYS = {"Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"}
_MINOR_KEYS = {"Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#"}
_CANONICAL_MAJOR = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
_CANONICAL_MINOR = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B")


class ExportError(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Note:
    start: float  # quarter-note beats, after meter scaling and swing
    end: float
    pitch: int
    velocity: float


def safe_title(title: str) -> str:
    text = unicodedata.normalize("NFKC", title)
    text = "".join(char for char in text if char.isalnum() or char in " -_")
    return re.sub(r"\s+", " ", text).strip(" -_")[:48] or "Untitled"


def midi_key(key: str) -> str:
    root, mode = key.split(" ")
    allowed = _MINOR_KEYS if mode == "minor" else _MAJOR_KEYS
    if root not in allowed:
        root = (_CANONICAL_MINOR if mode == "minor" else _CANONICAL_MAJOR)[NOTE_PC[root]]
    return root + ("m" if mode == "minor" else "")


def _meter_rhythm(pattern: list[float], numerator: int) -> list[float]:
    # Slot-only patterns [0,2] follow half-bars in every meter, as in Play.
    if pattern and all(position in (0, 2) for position in pattern):
        return [0 if position == 0 else numerator / 2 for position in pattern]
    return pattern


def _swing(position: float, amount: float) -> float:
    return amount if abs(position % 1 - 0.5) < 1e-9 else 0.0


def _note_messages(notes: list[Note], channel: int, end_tick: int) -> list[mido.Message]:
    """Validate, deduplicate and cut retriggers of each pitch before delta encoding."""
    combined: dict[tuple[int, int], tuple[int, int]] = {}
    for note in notes:
        if (not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                    for value in (note.start, note.end, note.velocity))
                or note.start < 0 or note.end <= note.start or not 0 < note.velocity <= 1
                or isinstance(note.pitch, bool) or not isinstance(note.pitch, int) or not 0 <= note.pitch <= 127):
            raise ExportError("Cannot export an invalid MIDI note or timing.")
        on = round(note.start * PPQ)
        off = min(end_tick, max(on + 1, round(note.end * PPQ)))
        if not 0 <= on < off <= end_tick:
            raise ExportError("A MIDI note falls outside the song.")
        velocity = max(1, min(127, round(note.velocity * 127)))
        previous = combined.get((on, note.pitch), (off, velocity))
        combined[(on, note.pitch)] = (max(off, previous[0]), max(velocity, previous[1]))
    next_on: dict[int, int] = {}
    events: list[tuple[int, int, int, int]] = []
    for (on, pitch), (off, velocity) in sorted(combined.items(), reverse=True):
        off = min(off, next_on.get(pitch, off))
        next_on[pitch] = on
        events.extend(((on, 1, pitch, velocity), (off, 0, pitch, 0)))
    result = []
    last = 0
    for tick, is_on, pitch, velocity in sorted(events):
        result.append(mido.Message("note_on" if is_on else "note_off", channel=channel,
                                   note=pitch, velocity=velocity, time=tick - last))
        last = tick
    return result


def render_midi(spec: ExportSpec) -> bytes:
    numerator, denominator = spec.timeSignature
    factor = 4 / denominator  # pattern beats are written denominator units; SMF beats are quarters
    half = numerator / 2
    song_quarters = len(spec.measures) * numerator * factor
    end_tick = round(song_quarters * PPQ)
    genre = (spec.genre or "").strip().lower()
    if genre == "bossa nova":
        genre = "bossa"
    play = spec.play
    preset = harmony_rhythm_preset(play.harmonyRhythmId) if play.harmonyRhythmId else None
    rhythm = _meter_rhythm(preset["pattern"] if preset else harmony_pattern(genre), numerator)
    bass_rhythm = _meter_rhythm(bass_pattern(genre), numerator)
    drum_id = play.drumPatternId if play.drumMode == "manual" else genre_drum_pattern_id(genre)
    drums = DRUM_PATTERNS.get(drum_id)
    swing = drums["swing"] if drums else 0
    harmony_notes: list[Note] = []
    bass_notes: list[Note] = []
    drum_notes: list[Note] = []
    for bar, measure in enumerate(spec.measures):
        first, second = measure.chords
        changed = (first.symbol if first else None) != (second.symbol if second else None)
        positions = [position for position in rhythm if 0 <= position < numerator]
        if positions and first and not any(position < half for position in positions):
            positions.append(0)
        if positions and second and changed and not any(position >= half for position in positions):
            positions.append(half)
        for position, duration in harmony_strikes(positions, numerator):
            chord = first if position < half else second
            if chord is None:
                continue
            if changed and position < half:
                duration = min(duration, half - position)
            # Swing moves the onset; harmony still releases at the original intended time.
            start = (bar * numerator + position + _swing(position, swing)) * factor
            end = min(song_quarters, (bar * numerator + min(numerator, position + duration)) * factor)
            for pitch in sorted(set(chord.voicing)):
                harmony_notes.append(Note(start, end, pitch, 0.7))
        if play.bassEnabled:
            bass_positions = sorted({position for position in bass_rhythm if 0 <= position < numerator})
            for index, position in enumerate(bass_positions):
                chord = first if position < half else second
                if chord is not None:
                    start = (bar * numerator + position + _swing(position, swing)) * factor
                    next_position = bass_positions[index + 1] if index + 1 < len(bass_positions) else numerator
                    slot_end = half if position < half else numerator
                    duration = min(0.9, next_position - position, slot_end - position)
                    end = (bar * numerator + position + duration) * factor
                    bass_notes.append(Note(start, end, chord.bass_pitch, 0.6))
        if drums:
            for voice, hits in drums["voices"].items():
                for step, velocity in hits:
                    position = step / 4
                    if not 0 <= position < numerator:
                        continue
                    start = (bar * numerator + position + _swing(position, swing)) * factor
                    drum_notes.append(Note(start, min(song_quarters, start + 0.25 * factor),
                                           DRUM_VOICE_TO_GM_NOTE[voice], velocity))
    if sum(map(len, (harmony_notes, bass_notes, drum_notes))) > MAX_EXPORT_NOTES:
        raise ExportError("The arrangement exceeds the 100,000-note export limit.", 413)

    midi = mido.MidiFile(type=1, ticks_per_beat=PPQ, charset="utf8")
    meta = mido.MidiTrack([
        mido.MetaMessage("track_name", name=spec.title or "Untitled", time=0),
        mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(spec.bpm), time=0),
        mido.MetaMessage("time_signature", numerator=numerator, denominator=denominator, time=0),
        mido.MetaMessage("key_signature", key=midi_key(spec.key), time=0),
    ])
    last_tick = 0
    for section in sorted(spec.sections, key=lambda part: part.startMeasure):
        tick = round(section.startMeasure * numerator * factor * PPQ)
        meta.append(mido.MetaMessage("marker", text=section.label, time=tick - last_tick))
        last_tick = tick
    meta.append(mido.MetaMessage("end_of_track", time=end_tick - last_tick))
    midi.tracks.append(meta)

    def add_track(name: str, notes: list[Note], channel: int, program: int | None, volume: float) -> None:
        track = mido.MidiTrack([mido.MetaMessage("track_name", name=name, time=0)])
        if program is not None:
            track.append(mido.Message("program_change", channel=channel, program=program, time=0))
        track.append(mido.Message("control_change", channel=channel, control=7,
                                  value=round(play.masterVolume * volume * 127), time=0))
        track.extend(_note_messages(notes, channel, end_tick))
        track.append(mido.MetaMessage("end_of_track", time=end_tick - sum(message.time for message in track)))
        midi.tracks.append(track)

    instrument = play.harmonyOverride or harmony_instrument(genre)
    add_track(f"Harmony – {instrument.replace('_', ' ')}", harmony_notes, 0, GM_PROGRAM[instrument], play.harmonyVolume)
    if play.bassEnabled:
        add_track("Bass", bass_notes, 1, GM_PROGRAM[bass_instrument(genre)], play.bassVolume)
    if drums:
        add_track("Drums", drum_notes, 9, None, play.drumVolume)
    buffer = io.BytesIO()
    with _MIDI_CHARSET_LOCK:
        midi.save(file=buffer)
    data = buffer.getvalue()
    if not data.startswith(b"MThd") or len(data) > MAX_EXPORT_BYTES:
        raise ExportError("The MIDI exceeds the 4 MiB export limit or could not be encoded.", 413)
    return data
