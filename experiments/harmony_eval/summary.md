# Harmony evaluation: does Meta read chords from notes better than the local analyzer?

Every engine saw the same notes and the same key, and never a chord symbol. A bar is scored on the editor's two slots; a slot without a proposal is wrong in the all-slot columns and left out of the covered ones. Matches are cumulative (triad needs root, seventh needs triad, exact needs all four); bass stands alone. A truth slot whose symbol the scorer cannot read is left out of every column and counted in each engine's status line.

## Real songs

Source: 130-song test split of the training corpora, private; excerpts realized with the product's voicing code. N = 40 excerpts from 40 songs, 320 bars, 640 slots. An excerpt is eight consecutive bars of one song whose every bar holds one or two chords (bars left out of every excerpt: more_than_two_chords 72; songs dropped: meter 1), realized in one of the six variants of the synthetic set: block 7, rootless 7, inversion 8, melody 6, sparse 6, waltz 6. Genres blues 3, bossa 3, classical 3, country 3, electronic 3, folk 4, funk 3, gospel 3, hip_hop 3, jazz 3, pop 3, rnb_soul 3, rock 3; realized meters 4/4 34, 3/4 6 (waltz excerpts are 3/4 whatever the song's meter). Key: the file's for 8 excerpts; for 32 the file holds C major, which the corpus preprocessing also writes for a song without a key, so the key is the product's own estimate over the excerpt's chords. The estimate is rough, and the Billboard and JHT files write every key as major, so a minor song's key can be wrong; every engine got the same key, so the comparison stays fair. Seed 20261029, sha256 of the private realized dataset `b5dcef9c9fde…`. Only these aggregates are public: the songs, their chords and the realized notes stay outside the repository.

| engine | slots | coverage | root | triad | seventh | bass | exact | root (covered) | exact (covered) | p50 ms | p95 ms | calls | cost | USD/bar | JSON valid | retry rate | provider / model |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| local | 640 | 81.6% | 77.8% | 77.8% | 77.8% | 77.8% | 77.8% | 95.4% | 95.4% | 0.1 | 0.6 | 320 | $0.0000 | $0.00000 | 100.0% | 0.0% | local / harmony_analysis |
| meta | 640 | 100.0% | 90.5% | 90.5% | 90.0% | 90.3% | 89.5% | 90.5% | 89.5% | 5078.9 | 9736.4 | 40 | $0.3380 | $0.00106 | 100.0% | 0.0% | meta / muse-spark-1.3 |
| auto | 640 | 95.3% | 84.5% | 84.5% | 84.5% | 83.9% | 83.9% | 88.7% | 88.0% | 6274.3 | 11584.9 | 6 | $0.0501 | $0.00016 | 100.0% | 0.0% | meta / muse-spark-1.3 |

- **local**: the product's deterministic analyzer, no model — complete; truth slots left unscored: 0
- **meta**: Muse Spark over the same notes, 8-bar batches, key given, no printed chords — complete; truth slots left unscored: 0
- **auto**: local first, Meta only for bars local left without chords (the product's engine=auto rule) — complete; truth slots left unscored: 0
- **openweight**: Muse Spark Open on Baseten, effort high, own ledger — not run: BASETEN_API_KEY is not set, so provider baseten cannot be called

Against local, in percentage points (all slots unless noted):

- **meta**, real songs: exact +11.7 (89.5% vs 77.8%), coverage +18.4 (100.0% vs 81.6%), exact on covered slots -5.9 (89.5% vs 95.4%); largest gain rootless +47.3, largest loss inversion -3.1; $0.3380 for 40 calls, p50 5.1 s per call
- **auto**, real songs: exact +6.1 (83.9% vs 77.8%), coverage +13.7 (95.3% vs 81.6%), exact on covered slots -7.4 (88.0% vs 95.4%); largest gain rootless +34.8, no variant lost; $0.0501 for 6 calls, p50 6.3 s per call

### By variant (real songs, all slots)

| variant | engine | slots | coverage | root | triad | seventh | bass | exact | exact (covered) |
|---|---|---|---|---|---|---|---|---|---|
| block | local | 112 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| block | meta | 112 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| block | auto | 112 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| inversion | local | 128 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| inversion | meta | 128 | 100.0% | 99.2% | 99.2% | 99.2% | 97.7% | 96.9% | 96.9% |
| inversion | auto | 128 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| melody | local | 96 | 68.8% | 68.8% | 68.8% | 68.8% | 68.8% | 68.8% | 100.0% |
| melody | meta | 96 | 100.0% | 99.0% | 99.0% | 95.8% | 100.0% | 95.8% | 95.8% |
| melody | auto | 96 | 68.8% | 68.8% | 68.8% | 68.8% | 68.8% | 68.8% | 100.0% |
| rootless | local | 112 | 21.4% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| rootless | meta | 112 | 100.0% | 47.3% | 47.3% | 47.3% | 47.3% | 47.3% | 47.3% |
| rootless | auto | 112 | 100.0% | 38.4% | 38.4% | 38.4% | 34.8% | 34.8% | 34.8% |
| sparse | local | 96 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sparse | meta | 96 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sparse | auto | 96 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| waltz | local | 96 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| waltz | meta | 96 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| waltz | auto | 96 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

### By genre (real songs, all slots)

| genre | engine | slots | coverage | root | triad | seventh | bass | exact | exact (covered) |
|---|---|---|---|---|---|---|---|---|---|
| blues | local | 48 | 100.0% | 66.7% | 66.7% | 66.7% | 66.7% | 66.7% | 66.7% |
| blues | meta | 48 | 100.0% | 66.7% | 66.7% | 66.7% | 66.7% | 66.7% | 66.7% |
| blues | auto | 48 | 100.0% | 66.7% | 66.7% | 66.7% | 66.7% | 66.7% | 66.7% |
| bossa | local | 48 | 45.8% | 45.8% | 45.8% | 45.8% | 45.8% | 45.8% | 100.0% |
| bossa | meta | 48 | 100.0% | 75.0% | 75.0% | 75.0% | 75.0% | 75.0% | 75.0% |
| bossa | auto | 48 | 79.2% | 54.2% | 54.2% | 54.2% | 45.8% | 45.8% | 57.9% |
| classical | local | 48 | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 100.0% |
| classical | meta | 48 | 100.0% | 97.9% | 97.9% | 97.9% | 100.0% | 97.9% | 97.9% |
| classical | auto | 48 | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 100.0% |
| country | local | 48 | 87.5% | 87.5% | 87.5% | 87.5% | 87.5% | 87.5% | 100.0% |
| country | meta | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| country | auto | 48 | 87.5% | 87.5% | 87.5% | 87.5% | 87.5% | 87.5% | 100.0% |
| electronic | local | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| electronic | meta | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| electronic | auto | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| folk | local | 64 | 75.0% | 75.0% | 75.0% | 75.0% | 75.0% | 75.0% | 100.0% |
| folk | meta | 64 | 100.0% | 98.4% | 98.4% | 98.4% | 100.0% | 98.4% | 98.4% |
| folk | auto | 64 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| funk | local | 48 | 66.7% | 66.7% | 66.7% | 66.7% | 66.7% | 66.7% | 100.0% |
| funk | meta | 48 | 100.0% | 83.3% | 83.3% | 83.3% | 83.3% | 83.3% | 83.3% |
| funk | auto | 48 | 100.0% | 83.3% | 83.3% | 83.3% | 83.3% | 83.3% | 83.3% |
| gospel | local | 48 | 62.5% | 62.5% | 62.5% | 62.5% | 62.5% | 62.5% | 100.0% |
| gospel | meta | 48 | 100.0% | 75.0% | 75.0% | 75.0% | 75.0% | 75.0% | 75.0% |
| gospel | auto | 48 | 95.8% | 70.8% | 70.8% | 70.8% | 70.8% | 70.8% | 73.9% |
| hip_hop | local | 48 | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 100.0% |
| hip_hop | meta | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| hip_hop | auto | 48 | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 100.0% |
| jazz | local | 48 | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 100.0% |
| jazz | meta | 48 | 100.0% | 100.0% | 100.0% | 93.8% | 100.0% | 93.8% | 93.8% |
| jazz | auto | 48 | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 100.0% |
| pop | local | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| pop | meta | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| pop | auto | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| rnb_soul | local | 48 | 83.3% | 66.7% | 66.7% | 66.7% | 66.7% | 66.7% | 80.0% |
| rnb_soul | meta | 48 | 100.0% | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% |
| rnb_soul | auto | 48 | 100.0% | 75.0% | 75.0% | 75.0% | 75.0% | 75.0% | 75.0% |
| rock | local | 48 | 66.7% | 66.7% | 66.7% | 66.7% | 66.7% | 66.7% | 100.0% |
| rock | meta | 48 | 100.0% | 85.4% | 85.4% | 85.4% | 79.2% | 79.2% | 79.2% |
| rock | auto | 48 | 100.0% | 81.2% | 81.2% | 81.2% | 81.2% | 81.2% | 81.2% |

Each genre has three or four excerpts in different variants and each variant about seven genres, so compare engines within a row, not rows with each other.

## Results (synthetic scores)

Synthetic dataset: `experiments/harmony_eval/dataset.jsonl` — 42 scores, 344 bars, variants {'block': 7, 'rootless': 7, 'inversion': 7, 'melody': 7, 'sparse': 7, 'waltz': 7}, sha256 `7b0aa7f95512…`.

| engine | slots | coverage | root | triad | seventh | bass | exact | root (covered) | exact (covered) | p50 ms | p95 ms | calls | cost | USD/bar | JSON valid | retry rate | provider / model |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| local | 688 | 96.2% | 77.9% | 77.9% | 77.6% | 82.0% | 77.6% | 81.0% | 80.7% | 0.2 | 0.8 | 344 | $0.0000 | $0.00000 | 100.0% | 0.0% | local / harmony_analysis |
| meta | 688 | 93.0% | 81.0% | 80.8% | 80.4% | 81.1% | 79.9% | 87.0% | 85.9% | 4954.2 | 9011.4 | 44 | $0.3877 | $0.00113 | 100.0% | 0.0% | meta / muse-spark-1.3 |
| auto | 688 | 98.3% | 79.7% | 79.7% | 79.4% | 83.3% | 78.9% | 81.1% | 80.3% | 4244.4 | 4244.4 | 1 | $0.0061 | $0.00002 | 100.0% | 0.0% | meta / muse-spark-1.3 |

- **local**: the product's deterministic analyzer, no model — complete; truth slots left unscored: 0
- **meta**: Muse Spark over the same notes, 8-bar batches, key given, no printed chords — complete; failed calls: harmony_validation 3; truth slots left unscored: 0
- **auto**: local first, Meta only for bars local left without chords (the product's engine=auto rule) — complete; truth slots left unscored: 0
- **openweight**: Muse Spark Open on Baseten, effort high, own ledger — not run: BASETEN_API_KEY is not set, so provider baseten cannot be called

Against local, in percentage points (all slots unless noted):

- **meta**, synthetic: exact +2.3 (79.9% vs 77.6%), coverage -3.2 (93.0% vs 96.2%), exact on covered slots +5.3 (85.9% vs 80.7%); largest gain melody +12.5, largest loss waltz -13.3; $0.3877 for 44 calls, p50 5.0 s per call
- **meta**, real score (37 bars): coverage +35.1 (78.4% vs 43.2%), exact +10.8 (29.7% vs 18.9%), exact on covered slots -5.8 (37.9% vs 43.8%); $0.0775 for 5 calls
- **auto**, synthetic: exact +1.3 (78.9% vs 77.6%), coverage +2.0 (98.3% vs 96.2%), exact on covered slots -0.3 (80.3% vs 80.7%); largest gain rootless +8.0, no variant lost; $0.0061 for 1 call, p50 4.2 s per call
- **auto**, real score (37 bars): coverage +2.7 (46.0% vs 43.2%), exact +2.7 (21.6% vs 18.9%), exact on covered slots +3.3 (47.1% vs 43.8%); $0.0044 for 1 call

Latency is wall-clock per call: per bar for local, per batch of up to 8 bars for the model engines (auto: its Meta calls only). Cost is the ledger's settled USD; USD/bar divides it by every dataset bar, also for auto, which sends only the bars local left open. JSON validity counts replies that parsed as the schema over all attempts; the Meta API enforces the schema server-side and never retries, so its retry rate is 0 by construction. Request ids are kept in `results-<engine>.json` and `results-real-songs-<engine>.json` under `calls[].request_id`.

## Confidence calibration (synthetic, covered slots)

| engine | reported confidence | slots | root | exact |
|---|---|---|---|---|
| local | medium | 274 | 66.4% | 66.4% |
| local | low | 388 | 91.2% | 90.7% |
| meta | high | 592 | 88.3% | 87.7% |
| meta | medium | 32 | 65.6% | 65.6% |
| meta | low | 16 | 81.2% | 62.5% |
| auto | medium | 274 | 66.4% | 66.4% |
| auto | low | 402 | 91.0% | 89.8% |

## By variant (synthetic, all slots)

| variant | engine | slots | coverage | root | triad | seventh | bass | exact | exact (covered) |
|---|---|---|---|---|---|---|---|---|---|
| block | local | 112 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| block | meta | 112 | 100.0% | 100.0% | 99.1% | 96.4% | 100.0% | 96.4% | 96.4% |
| block | auto | 112 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| inversion | local | 112 | 100.0% | 75.0% | 75.0% | 75.0% | 100.0% | 75.0% | 75.0% |
| inversion | meta | 112 | 85.7% | 83.0% | 83.0% | 83.0% | 85.7% | 83.0% | 96.9% |
| inversion | auto | 112 | 100.0% | 75.0% | 75.0% | 75.0% | 100.0% | 75.0% | 75.0% |
| melody | local | 112 | 89.3% | 89.3% | 89.3% | 87.5% | 89.3% | 87.5% | 98.0% |
| melody | meta | 112 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| melody | auto | 112 | 89.3% | 89.3% | 89.3% | 87.5% | 89.3% | 87.5% | 98.0% |
| rootless | local | 112 | 87.5% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| rootless | meta | 112 | 85.7% | 14.3% | 14.3% | 14.3% | 12.5% | 11.6% | 13.5% |
| rootless | auto | 112 | 100.0% | 10.7% | 10.7% | 10.7% | 8.0% | 8.0% | 8.0% |
| sparse | local | 120 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sparse | meta | 120 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| sparse | auto | 120 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| waltz | local | 120 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| waltz | meta | 120 | 86.7% | 86.7% | 86.7% | 86.7% | 86.7% | 86.7% | 100.0% |
| waltz | auto | 120 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## By genre (synthetic, all slots)

| genre | engine | slots | coverage | root | triad | seventh | bass | exact | exact (covered) |
|---|---|---|---|---|---|---|---|---|---|
| blues | local | 96 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| blues | meta | 96 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| blues | auto | 96 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| bossa | local | 64 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| bossa | meta | 64 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| bossa | auto | 64 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| classical | local | 64 | 78.1% | 75.0% | 75.0% | 75.0% | 75.0% | 75.0% | 96.0% |
| classical | meta | 64 | 75.0% | 70.3% | 68.8% | 68.8% | 67.2% | 64.1% | 85.4% |
| classical | auto | 64 | 100.0% | 93.8% | 93.8% | 93.8% | 89.1% | 89.1% | 89.1% |
| country | local | 32 | 100.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% |
| country | meta | 32 | 100.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% |
| country | auto | 32 | 100.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% |
| electronic | local | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| electronic | meta | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| electronic | auto | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| folk | local | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| folk | meta | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| folk | auto | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| funk | local | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| funk | meta | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| funk | auto | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| gospel | local | 32 | 100.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% |
| gospel | meta | 32 | 100.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% |
| gospel | auto | 32 | 100.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% |
| hip_hop | local | 32 | 81.2% | 56.2% | 56.2% | 56.2% | 81.2% | 56.2% | 69.2% |
| hip_hop | meta | 32 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| hip_hop | auto | 32 | 81.2% | 56.2% | 56.2% | 56.2% | 81.2% | 56.2% | 69.2% |
| jazz | local | 112 | 100.0% | 59.8% | 59.8% | 59.8% | 71.4% | 59.8% | 59.8% |
| jazz | meta | 112 | 71.4% | 57.1% | 57.1% | 54.5% | 59.8% | 54.5% | 76.2% |
| jazz | auto | 112 | 100.0% | 59.8% | 59.8% | 59.8% | 71.4% | 59.8% | 59.8% |
| pop | local | 80 | 92.5% | 70.0% | 70.0% | 67.5% | 72.5% | 67.5% | 73.0% |
| pop | meta | 80 | 100.0% | 80.0% | 80.0% | 80.0% | 80.0% | 80.0% | 80.0% |
| pop | auto | 80 | 92.5% | 70.0% | 70.0% | 67.5% | 72.5% | 67.5% | 73.0% |
| rnb_soul | local | 32 | 100.0% | 37.5% | 37.5% | 37.5% | 50.0% | 37.5% | 37.5% |
| rnb_soul | meta | 32 | 100.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% |
| rnb_soul | auto | 32 | 100.0% | 37.5% | 37.5% | 37.5% | 50.0% | 37.5% | 37.5% |
| rock | local | 48 | 100.0% | 97.9% | 97.9% | 97.9% | 100.0% | 97.9% | 97.9% |
| rock | meta | 48 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| rock | auto | 48 | 100.0% | 97.9% | 97.9% | 97.9% | 100.0% | 97.9% | 97.9% |

## Real score (one private real score)

| engine | slots | coverage | root | triad | seventh | bass | exact | root (covered) | exact (covered) | p50 ms | p95 ms | calls | cost | USD/bar | JSON valid | retry rate | provider / model |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| local (one private real score, 37 bars) | 74 | 43.2% | 25.7% | 18.9% | 18.9% | 36.5% | 18.9% | 59.4% | 43.8% | 0.6 | 2.0 | 37 | $0.0000 | $0.00000 | 100.0% | 0.0% | local / harmony_analysis |
| meta (one private real score, 37 bars) | 74 | 78.4% | 54.0% | 50.0% | 44.6% | 46.0% | 29.7% | 69.0% | 37.9% | 12481.7 | 14571.2 | 5 | $0.0775 | $0.00210 | 100.0% | 0.0% | meta / muse-spark-1.3 |
| auto (one private real score, 37 bars) | 74 | 46.0% | 28.4% | 21.6% | 21.6% | 39.2% | 21.6% | 61.8% | 47.1% | 4604.1 | 4604.1 | 1 | $0.0044 | $0.00012 | 100.0% | 0.0% | meta / muse-spark-1.3 |

- **local**: complete; truth slots left unscored: 0; 52 bars in the score, 37 scored (left out: no_chord_sign 1, no_printed_chords 6, more_than_two_printed_chords 8); key G major (inferred, confidence 0.305); timing estimated in 30 scored bars, reader warnings in 30; meters {'4/4': 36, '2/4': 1}
- **meta**: complete; truth slots left unscored: 0; 52 bars in the score, 37 scored (left out: no_chord_sign 1, no_printed_chords 6, more_than_two_printed_chords 8); key G major (inferred, confidence 0.305); timing estimated in 30 scored bars, reader warnings in 30; meters {'4/4': 36, '2/4': 1}
- **auto**: complete; truth slots left unscored: 0; 52 bars in the score, 37 scored (left out: no_chord_sign 1, no_printed_chords 6, more_than_two_printed_chords 8); key G major (inferred, confidence 0.305); timing estimated in 30 scored bars, reader warnings in 30; meters {'4/4': 36, '2/4': 1}
- **openweight**: not run: BASETEN_API_KEY is not set, so provider baseten cannot be called

Aggregate rows only: the score, its notes and its per-bar outputs stay outside the repository. A bar counts when it carries both printed chords and read notes; bars with more than two printed chords have no two-slot truth and are left out. The key is the product's own estimate from the read notes, given to every engine alike.

## What the numbers do and do not show

- The real songs are real progressions held out from training, but their notes are the product's own voicings of the chord symbols, so they test reading real harmony, not a musician's voicing or a PDF. In the Chordonomicon-derived genres a bar is two consecutive chords as the corpus preprocessing grouped them, not a timed bar.
- The synthetic scores are the product's own voicings of its own progressions with controlled difficulty (rootless shells, slash inversions, melody passing and neighbor tones, sparse bars, 3/4). They show where an engine fails, not how often a musician's PDF fails.
- Every engine got the key. Without it, the local analyzer estimates one and the model is told none; neither case is measured here.
- Notes only: no printed chords were visible to any engine, also where the product would send a neighbor's printed symbol as context.
- One real score is evidence, not a benchmark, and its timing is estimated in most bars, which caps every engine's confidence at low by the product's rules.
- A chord is right or wrong against one truth symbol; a musically defensible alternative (Eb6 for Cm7, the relative minor of a rootless maj7) counts as wrong.
