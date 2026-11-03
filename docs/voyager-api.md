# Voyager API quick start

TheVoyager defaults to MCP `build_song` (`THEARTIST_TRANSPORT=mcp`); its REST compatibility mode uses `POST /api/generate/song` when `THEARTIST_TRANSPORT=rest`. Both invoke the same song service. Send a genre and length to receive one three-track arrangement. Artist picks the key, BPM, time signature, chord checkpoint and instruments; Voyager handles mood→genre mapping and audio rendering. The REST examples below exercise that same contract.

**1) Curl smoke-test**

```bash
curl -sS http://localhost:8000/api/generate/song \
  -H 'Content-Type: application/json' \
  -d '{"genre": "jazz", "length_bars": 8}' | jq '.key, .bpm, .model_used, (.tracks | keys)'
```

```
"F major"
110
"ft_f4"
[
  "bass",
  "drum",
  "harmony"
]
```

**2) Python client (example shape)**

```python
import base64
import io
import requests
import pretty_midi   # caller-side render

BASE = "http://localhost:8000"

def generate_song(genre: str, length_bars: int = 8) -> dict:
    r = requests.post(f"{BASE}/api/generate/song", json={
        "genre": genre,
        "length_bars": length_bars,
    })
    r.raise_for_status()
    return r.json()

def to_pretty_midi(song: dict) -> pretty_midi.PrettyMIDI:
    return pretty_midi.PrettyMIDI(io.BytesIO(base64.b64decode(song["midi_b64"])))

song = generate_song("country", length_bars=4)
print(song["bars"])               # [{"chords": [...]}, ...]
print(song["tracks"]["harmony"]["instrument"])   # "acoustic_guitar_steel"
midi = to_pretty_midi(song)       # ready for a soundfont render
```

**3) Request fields** (`SongGenerateRequest`)

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `genre` | string | ✓ | — | One of `jazz, pop, rock, blues, bossa, classical, country, rnb_soul, hip_hop, electronic, funk, folk, gospel`. 400 if not in list. |
| `length_bars` | int | — | `8` | Range 1–64. |
| `n_candidates` | int | — | `1` | Must be exactly `1`; unsupported candidate fan-out returns 422. |
| `seed` | int \| null | — | `null` | Strict integer `0..2^32-1`; request-local sampling, echoed in the response. Reproducibility requires the same model and runtime. |
| `harmony_rhythm` | string \| null | — | `null` | A comping-rhythm preset id (`charleston`, `eighth_pulse`, `boom_chick`, `shuffle`, `bossa`, `chorale`, `folk_pocket`, `neo_soul_offbeat`, `boom_bap`, `sidechain_offbeat`, `funky_drummer`, `block`, `half`). `null` = the genre's. |
| `drum_pattern` | int \| `"off"` \| null | — | `null` | A drum pattern id 1–15, or `"off"` for no drums. `null` = the genre's. |
| `harmony_instrument` | string \| null | — | `null` | One of the editor's 31 harmony instruments (GM Soundfont names). `null` = the genre's. |

The three optional fields are the editor's Play-panel choices; [API_SPEC.md](https://github.com/PearlLeeStudio/TheArtist-DAW/blob/6ed1b50914c78c205ee7aabdde924c648caf292d/API_SPEC.md) lists every preset, pattern and instrument.

**4) Response shape** (`SongGenerateResponse` — top-level keys)

| Key | Type | Description |
|---|---|---|
| `genre` | string | Echo of request. |
| `seed` | int \| null | Echo of the sampling seed; `null` keeps stochastic generation. |
| `key` | string | Picked from `GENRE_DEFAULTS` — e.g. jazz→`F major`, electronic→`A minor`. |
| `bpm` | int | Picked from `GENRE_DEFAULTS` — e.g. blues→90, electronic→128. |
| `time_signature` | `[int, int]` | `[4, 4]` for all 13 genres in v1. |
| `harmony_rhythm` | string | The comping-rhythm preset that played (the request's, else the genre's). |
| `drum_pattern` | int \| `"off"` | The drum pattern that played, or `"off"`. Sent back in a request, it replays the same drums. |
| `bars` | `[{"chords": [str, str]}]` | Exactly `length_bars` bars of two chord slots. Slot 0 covers `[0, beats/2)`, slot 1 covers `[beats/2, beats)`. |
| `tracks.harmony.events[]` | `[TrackEvent]` | Chord voicing struck on the 1-bar comping rhythm; a strike lasts until just before the next one. Each event = `{bar, beat, pitch, duration, velocity}`. |
| `tracks.bass.events[]` | `[TrackEvent]` | Chord root struck on `GENRE_BASS_RHYTHM` positions, anchored at MIDI 36 (C2). |
| `tracks.drum.events[]` | `[TrackEvent]` | The drum pattern that played (empty when `"off"`). `voice` is `K`/`S`/`H`/`O`/`X`/`C`/`R`/`T`/`M`/`L`; `pitch` is `null`. |
| `tracks.<name>.instrument` | string | GM Soundfont name (e.g. `electric_piano_1`, `contrabass`) for harmony/bass — harmony is `harmony_instrument` when sent; `gm_drum_kit` for drum. |
| `tracks.<name>.source` | `"rule"` | All three layers rule-based in v1. |
| `midi_b64` | string | Convenience MIDI render. 4 internal tracks: meta (tempo+time-sig), harmony ch 0, bass ch 1, drum ch 9. |
| `model_used` | string | Chord-generation checkpoint (`ft_f4`, `ft_f1_lora_country`, …) or `"rules"` if the AI path was unavailable. |

Drum voice letters → GM percussion (channel 10) mapping lives in `backend/app/services/genre_tables.py:DRUM_VOICE_TO_GM_NOTE` if you want to remap to a custom kit.

**5) Genre defaults table** (artist's internal picks)

| Genre | Key | BPM | Harmony instrument | Bass instrument | Drum |
|---|---|---|---|---|---|
| jazz | F major | 110 | electric_piano_1 (Rhodes) | contrabass | Jazz Swing |
| pop | C major | 110 | acoustic_grand_piano | electric_bass_finger | Pop |
| rock | E major | 120 | overdriven_guitar | electric_bass_finger | Rock Anthem |
| blues | E major | 90 | electric_guitar_clean | electric_bass_finger | Blues Shuffle |
| bossa | F major | 110 | acoustic_guitar_nylon | contrabass | Bossa |
| classical | C major | 80 | acoustic_grand_piano | contrabass | Classical |
| country | G major | 100 | acoustic_guitar_steel | electric_bass_finger | Country |
| rnb_soul | Bb major | 90 | electric_piano_1 | electric_bass_finger | R&B / Soul |
| hip_hop | A minor | 90 | electric_piano_1 | electric_bass_finger | Hip-hop |
| electronic | A minor | 128 | pad_2_warm | electric_bass_finger | Electronic |
| funk | F major | 110 | electric_guitar_clean | electric_bass_finger | Funk 16 |
| folk | G major | 100 | acoustic_guitar_steel | contrabass | Folk / Ballad |
| gospel | F major | 90 | drawbar_organ | electric_bass_finger | Gospel |

The full per-genre 1-bar harmony / bass rhythm patterns live in `frontend/src/engine/genreTables.ts` (`HARMONY_RHYTHM_PRESETS`, `GENRE_BASS_RHYTHM`; mirrored in `backend/app/services/genre_tables.py`).

**6) Errors**

| Status | Body | When |
|---|---|---|
| 400 | `{"detail": "Unsupported genre '<x>'. Expected one of: ..."}` | Genre not in the 13-genre vocabulary. |
| 422 | Pydantic validation | `length_bars` out of `[1, 64]`, missing `genre`, or an unknown `harmony_rhythm` / `drum_pattern` / `harmony_instrument` (the message lists the valid values). |

For the older `/api/generate/chords` programmatic chord-only endpoint (no arrangement), see [API_SPEC.md](https://github.com/PearlLeeStudio/TheArtist-DAW/blob/6ed1b50914c78c205ee7aabdde924c648caf292d/API_SPEC.md).
