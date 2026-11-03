# Models, training data and theory sources

The served checkpoints, their training-log metrics and caveats, the corpora
behind them and the theory retrieval sources. The [README](https://github.com/PearlLeeStudio/TheArtist-DAW/blob/6ed1b50914c78c205ee7aabdde924c648caf292d/README.md#models-and-data)
keeps the summary.

## AI Model

TheArtist serves a custom Music Transformer (~25M parameters) from a pop→jazz genre-adaptation study ([arXiv:2605.04998](https://arxiv.org/abs/2605.04998)). The Pop / Jazz top-1 columns are each run's best-epoch training-log metrics; note that the *released* F1 base coincides with Phase 0 (see the F1 row and note below):

| Run | Data | Focus | Pop top-1 | Jazz top-1 |
|-----|------|-------|----------:|-----------:|
| **Phase 0** | Chordonomicon + Billboard, ~544K songs × 3 ep | Pop baseline | 84.21% | 72.86% |
| **F1** `ft_jazz_pop80` | Phase 0 + 10K pop mix | Preserve pop (paper run) | **84.60%** | 81.03% |
| **F1 v2** `ft_jazz_pop80_v2` | Phase 0 + 10K pop mix (jazz_val-selected) | Selection-corrected F1 (served as `ft_f1_v2`) | 83.73% | 80.31% |
| **F2** `ft_jazz_pop67` | Phase 0 + 5K pop mix | Balanced | 84.06% | 79.91% |
| **F3** `ft_jazz_pop50` | Phase 0 + 2.5K pop mix | Paper sweet-spot finding (no longer default) | 84.20% | 80.99% |
| **F4** `ft_jazz_pop29` | Phase 0 + 1K pop mix | Jazz-leaning | 83.02% | 81.50% |
| **F5** `ft_jazz_only` | Phase 0 + 0 pop | Jazz only (catastrophic forgetting) | 82.10% | 81.30% |

> **F1 served-weights note.** The *released* F1 `best.pt` is weight-identical to Phase 0 — a best-checkpoint-selection artifact (a seed/data-dependent worst case where min-mixed-val selection retained the un-adapted init, not a deterministic outcome), so the served v1 F1 evaluates at the Phase 0 numbers (84.21% pop / 72.86% jazz); the 84.60 / 81.03 above are the paper's epoch-6 training-log figures, never released as `best.pt`. The selection-corrected retrain `ft_jazz_pop80_v2` (`select_best_on: jazz_val`, served as `ft_f1_v2`) is hash-distinct from Phase 0 and embodies the intended jazz adaptation; the 11 LoRA adapters remain paired with the v1 base.

> **Jazz top-1 comparability note.** The F-series and `ft_f1_v2` Jazz top-1 figures in the table above are measured on the **6-source jazz test (167 seqs)** and are **not** directly comparable to the expanded **9-source jazz test (501 seqs)** used for multi-seed validation: the same `ft_jazz_pop80_v2` weights score 80.31 on the 6-src test but 75.05 on the 9-src test, and the matched-data 9-src multi-seed retrains {seeds 42, 123, 7; n=3} land at jazz top-1 75.76 ± 0.03 (per-seed 75.78 / 75.78 / 75.72), all hash-distinct from Phase 0. Compare like-for-like within a single test set only.

The backend defaults to F1 (`ft_f1`, pop-preserving baseline). Recommended ⭐ picks are F1 / F1 v2 (pop-leaning) and F4 (jazz-leaning). F3 — the paper's sweet-spot finding — remains served but is no longer the default. The model selector exposes the other paper checkpoints + the selection-corrected `ft_f1_v2` + 11 LoRA per-genre adapters covering the 13-genre vocabulary (jazz/pop run on the F-series base directly).

These weights are gitignored — they live on HuggingFace as public repos under [PearlLeeStudio](https://huggingface.co/PearlLeeStudio) (seven F-series base — incl. the selection-corrected F1 v2 retrain `ft-pop80-v2` — + eleven LoRA adapters, CC BY-NC). Fetch them into `ai/checkpoints/` with `uv run --with huggingface_hub python /absolute/path/TheArtist-DAW/model/_download.py`; without them the backend serves rule-based fallback.

### R1 ranking and local theory retrieval

**R1 is active in the product.** The backend uses mean Sethares sensory roughness
from [`ai/physics/`](https://github.com/PearlLeeStudio/TheArtist-DAW/tree/6ed1b50914c78c205ee7aabdde924c648caf292d/ai/physics) to order the author's model candidates.
Roughness measures sensory consonance; it is not a next-chord accuracy or listener
preference score. The same directory also contains Stolzenburg periodicity,
composite metrics and diversity experiments from the pre-existing research.

**OMT retrieval is enabled by default once its corpus is prepared.** The product
uses local TF-IDF over 29 reviewed prose passages from seven chapters of the
original [Open Music Theory GitHub edition](https://openmusictheory.github.io/).
It adds text relevance to R1 ranking and displays related source excerpts with
attribution and CC BY-SA 4.0 links. These are references, not generated musical
explanations or evidence of a quality improvement. Berklee is independently
switchable and **off by default**; public hosts reject enabling it.

[Setup, source controls and license handling](theory-retrieval.md) describe
the corpus boundaries and missing-data status. The older Snowflake/Chroma/Gemma
research modules remain separate and are not loaded by the product. The product's
AI runtime continues to use the author's Music Transformer and Meta models.
The mix-ratio papers describe the training study, not a quality evaluation of
this retrieval or the hackathon planner.

The training and evaluation pipeline is included under `ai/training/` (preprocess → dataset splits → config-driven training → evaluation → aggregation, plus the checkpoint-selection audit scripts `check_claims.py` and `model/_verify_release.py` and the selection-criterion analysis under `ai/analysis/`). The experiments themselves (mix-ratio sweep, 13-genre LoRA grid, rank sweep, multi-seed validation) are documented in [arXiv:2605.04998](https://arxiv.org/abs/2605.04998) and [arXiv:2606.07334](https://arxiv.org/abs/2606.07334), and the per-model evaluation summaries live on the [HuggingFace model cards](https://huggingface.co/PearlLeeStudio). Datasets and checkpoints are not redistributed here — data comes from the upstream sources above, checkpoints from the Hub.

## Datasets

### Training corpora

| Dataset | Songs (used) | Genre | License |
|---|---:|---|---|
| [Chordonomicon](https://huggingface.co/datasets/ailsntua/Chordonomicon) | ~679K | Pop / rock + community-tagged subsets (country, alt, rap, soul, electronic) | CC BY-NC 4.0 |
| [McGill Billboard](https://ddmal.music.mcgill.ca/research/The_McGill_Billboard_Project_(Chord_Analysis_Dataset)/) | ~890 | Pop / rock | CC0 |
| [Jazz Harmony Treebank (JHT)](https://github.com/DCMLab/JazzHarmonyTreebank) | ~1,170 | Jazz | Public |
| [Weimar Jazz Database (WJazzD)](https://jazzomat.hfm-weimar.de/) | ~283 | Jazz | ODbL |
| [JAAH](https://mtg.github.io/JAAH/) | ~113 | Jazz | Research |
| [JazzStandards / iReal-derived](https://github.com/mikeoliphant/JazzStandards) | ~293 | Jazz | Community corpus |
| [Bach 371 chorales (via music21)](https://web.mit.edu/music21/) | 371 | Tonal chorales (used as the "classical" LoRA target) | Public domain |

Raw datasets are **not redistributed** in this repo. Chordonomicon is CC BY-NC; the others have their own per-source terms. Acquire each from the upstream link above.

For the LoRA expansion, 10 of the 11 target genres draw from Chordonomicon's genre-labeled subsets (classical uses the Bach chorales above, since Chordonomicon has no classical slice); see paper §4 for selection-bias notes (e.g., the "electronic" slice is biased toward synthwave / melodic house, "hip-hop" toward jazz-rap / neo-soul).

### Theory retrieval

- **Open Music Theory** — the default source is a reviewed subset of the original
  GitHub edition, not the complete v2 book. Setup fetches hash-checked prose only;
  music examples, images, block quotations and external-link paragraphs are excluded.
  Retrieved excerpts retain author/editor credit, source, license and modification notices.
- **The Berklee Book of Jazz Harmony** — disabled by default. Neither its text nor
  its index is distributed. Explicit private opt-in is separate from the legal
  permission needed for a particular use; public hosts reject it.

See [theory retrieval](theory-retrieval.md) for configuration and limitations.
