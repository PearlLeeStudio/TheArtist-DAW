# Repository consistency checks

The audit started from development commit `8fc40e0`: 1,009 tracked files,
906 text files and 103 binary files, including 46 Markdown documents. Every
tracked file was read by the scan. Current product documentation was compared
with runtime contracts and implementations; historical experiment records and
model cards retain their original conditions. The backend README and this report
were added as part of the fixes.
The final scan covered 1,011 tracked files, including 48 Markdown documents,
with no parsing, local-link or heading-anchor errors.

This is a tracked-repository consistency check, not a claim that every code path
was manually exercised. Ignored checkpoints, downloaded corpora, environments,
user data and separate repositories are outside this inventory.

## Corrected mismatches

| Area | Documentation or configuration correction |
| --- | --- |
| Import | Current Reader names and independent file/Reader selection; explicit **Analyze score**; stale review clearing and cancellation limits |
| Theory retrieval | OMT defaults on after setup, Berklee off; local text relevance and attributed excerpts; old embedding/LLM research is separate |
| Performance | Saved speed measurements explicitly use retrieval off; they do not measure the new default end-to-end experience or cold audio latency |
| Models | All 18 runtime choices have released model directories; base vocabulary 351 versus served vocabulary 359 |
| Installation | Added the README required by backend package metadata; corrected F1-only `--smoke` download and frozen-environment commands |
| Deployment | Environment template preserves the localhost CORS origin; public-host log describes bounded Meta assist correctly |
| Playback/export | Shared note placement is distinguished from real-host sound equivalence; Scripter has harmony/bass but no drums |
| Evidence | Screenshots, historical work-log rows and prior evaluations are distinguished from the latest controls and retrieval policy |

## Contract checks

| Contract | Implementation evidence |
| --- | --- |
| HTTP | All 20 OpenAPI paths are documented in [API_SPEC](../API_SPEC.md) |
| MCP | Eleven registered tools match the [MCP contract](mcp.md) |
| Models | Eighteen checkpoint/adapter keys; tokenizer length 359 |
| Source readiness | A fresh local app with prepared corpus reports OMT ready and Berklee disabled |
| Import limits | 8 MiB file, local 512 measures, attachment Meta 128; assist at most 16 measures/3 calls/$0.30 |
| Planner limits | Target lengths 16/32/48/64; at most 5 LLM calls/$0.10/120 seconds |
| Dependencies | Frontend manifest matches lockfile root dependencies; backend declared dependency names match its lockfile package entry |

Retrieval runs in passage/section generation, including planner-generated
sections. Direct `/api/generate/chords` and `/api/generate/song` bypass that
ranking/notes pipeline. Import does not use RAG. See [the source guide](theory-retrieval.md).

## Automated results

- Python syntax, JSON/JSONL and TOML parsing passed. The two JSONC TypeScript
  configurations were checked by the frontend build rather than a strict JSON parser.
- All 416 YAML files parsed, 65 MIDI files and 3 PDFs opened, 27 PNG headers
  matched their format, and 11 FLAC headers matched. This is format validation,
  not a visual or listening assessment.
- Relative Markdown/HTML links and Markdown heading anchors resolved. A limited
  credential-pattern scan found no matches; it is not an exhaustive secrets audit.
- Backend: **516 tests**, `OK`; frontend: **231 tests**, `fail 0`;
  Logic Scripter mock host: **14 tests**, `fail 0`.
- Backend import, frontend build and lint passed. The build still warns about a
  chunk over 500 kB; passing the build does not resolve initial-download performance.

## Remaining verification

The full suites do not replace a clean-checkout installation, external hosted
walkthrough, listening comparison, real Scripter transport/GM/CC checks, physical
MIDI-device testing or wider score-reading evaluation. The new OMT citation cards
and changing Reader during an active request still require manual browser checks.
See the [manual checklist](manual-checks.md) and [evaluation limits](evaluation.md).

No new paid Meta evaluation was run for this documentation audit. Prior failures,
including notes-only PNG reading and final planner judgments requesting further
regeneration, remain in the evaluation records.
