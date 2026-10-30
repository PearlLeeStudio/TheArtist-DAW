# Theory retrieval

The product enables Open Music Theory (OMT) by default and disables Berklee.
Source switches are independent; disabling a source prevents even opening or
checking its corpus file. Changes to source settings or corpus files select a
new index and transition cache, so previously retrieved Berklee material cannot
appear in OMT-only results.

## Prepare OMT

After installing backend dependencies, run once with network access:

```sh
uv run --frozen --directory /absolute/path/TheArtist-DAW/backend python /absolute/path/TheArtist-DAW/backend/scripts/setup_omt.py
```

This fetches **29 prose passages from seven chapters** of the original
[Open Music Theory GitHub edition](https://openmusictheory.github.io/), not the
complete v2 book. The tracked manifest contains titles, source links, sections,
attribution and paragraph hashes, not book text. Setup accepts only matching
paragraphs; changed material or a missing license notice fails preparation.
The resulting `ai/data/openmusictheory/reviewed.json` is ignored by Git. Prepare
it on each host before starting the backend; an existing host can rerun setup
without rebuilding the app. Corpus replacement is atomic.

The selected text covers harmonic functions, two harmonic-syntax chapters,
cadences, applied chords, modal mixture and pop/rock harmony. Images, embedded
music, block quotations, tables and paragraphs with external links are excluded.
This is a small reviewed reference set, not comprehensive harmony coverage.

## Source controls

| Environment variable | Default | Effect |
| --- | --- | --- |
| `THEARTIST_DISABLE_RAG` | `0` | `1` disables both sources and all retrieval |
| `THEARTIST_RAG_OMT_ENABLED` | `1` | Enables the reviewed OMT corpus |
| `THEARTIST_RAG_BERKLEE_ENABLED` | `0` | Explicit private opt-in for existing Berklee chunks |
| `THEARTIST_RAG_OMT_PATH` | `ai/data/openmusictheory/reviewed.json` under repo | Optional absolute corpus path |
| `THEARTIST_RAG_BERKLEE_PATH` | `ai/data/cache/berklee.chunks.jsonl` under repo | Optional absolute private corpus path |
| `THEARTIST_DISABLE_EXPLANATIONS` | `0` | Hides source notes; retrieval ranking remains active |

An inherited `THEARTIST_DISABLE_RAG=1` still overrides the new defaults. Restart
the backend after changing its environment. `THEARTIST_PUBLIC_HOST=1` rejects
active Berklee configuration before its file is accessed. An explicit private
opt-in is a technical switch, not a grant of copyright permission. Buying the
book does not itself authorize public retrieval, excerpt distribution or API use.

`GET /api/capabilities` exposes `data.rag`, for example:

```json
{
  "enabled": true,
  "ready": true,
  "sources": {"omt": "ready", "berklee": "disabled"},
  "method": "local_tfidf",
  "notes": "source_excerpt"
}
```

Missing or invalid corpora report `missing` or `invalid` and a backend warning.
Unavailable sources contribute no ranking or notes; OMT failure never enables
Berklee. With no ready source, generation uses R1 alone and emits no Theory phase.

## Retrieval and output

Local TF-IDF matches chord-transition concept queries to reviewed prose. It adds
text relevance to R1 roughness ranking and returns up to 16 distinct transition
references per candidate after song-form rules and voice leading. An excerpt is
at most 400 characters, marked `source_excerpt`, with its actual matched source.
The UI labels these **Theory references**, shows author/editor credits, links the
source and license, and retains copyright and modification notices.

This path makes no network, embedding-model or LLM calls during generation.
The older Chroma/Snowflake/Gemma research pipeline and `_setup_corpora.sh` are
separate and unused by the product. Text relevance is not harmonic correctness;
two chords alone do not establish key or cadence. This feature has not established
a musical-quality improvement through listener or reference-based evaluation.

## Attribution and license

OMT's original edition credits **Kris Shaffer, Bryn Hughes and Brian Moseley**
as authors, **Kris Shaffer and Robin Wharton** as editors, and
**© 2022 Hybrid Pedagogy Publishing**. The selected prose is licensed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), as described by
[the source's About page](https://openmusictheory.github.io/about.html).

Downloaded text and displayed excerpts retain that license. Changes consist of
prose selection, HTML whitespace normalization, media exclusion and possible
excerpt shortening. When distributing adaptations of this prose, preserve
attribution, source/license links, change notices and the applicable ShareAlike
terms. The app's original code remains MIT; its license does not replace the
source text's license. Third-party material in the wider textbook must be
assessed separately and is not licensed by this manifest.

Berklee text, PDFs and indexes are neither included nor downloaded by product
setup. Keep them out of public repositories and hosts.
