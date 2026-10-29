# Controlled song-form comparison

[Comparison](comparison.md) pools the 20 public fixtures across chord-sampling seeds 1380, 1381 and 1382. Both arms use the same `ft_f1` chord checkpoint, normalized request, derived sampling seed, temperatures and postprocessing. The treatment is the complete Muse Spark planning/judging pipeline, including bounded regeneration. The Meta planner itself is not seeded. These are repeated measurements of 20 fixtures, not 60 independent songs or a listening study.

Each seed directory contains `rules.json` and `meta-medium.json`, including the saved request, full final trace, initial/regenerated section provenance, API request IDs and token usage. `agent/report_fixed_seed_plans.py` rechecks the pairing, all neural generation attempts, structural contracts and cost reconciliation before pooling the data. It makes no API calls.

The preserved `seed-1379` pilot cost $0.357468. It verified final sections but did not retain the source of every initial generation attempt before regeneration. The pilot is excluded from the main comparison for that reason; its outcome was not used to select the three main seeds. The pilot cost is additional to the main comparison's reported cost. All four batches shared a dedicated $10 evaluation ledger and retained the product's per-call, per-run and turn limits.

The seed-1381 Python runner completed all 20 pairs and wrote both complete result files. Its surrounding shell wrapper returned exit code 2 after the runner finished because the wrapper was edited while that process was running. A separate execution of the strict offline reporter subsequently validated all 40 traces, pairing, generation provenance and cost records. The completed music was retained without rerunning or selecting outcomes.

[Listening samples](listening/README.md) provides three predetermined pairs from seed 1380: new pop, new jazz and an A-minor hip-hop completion. The six MIDI files preserve the saved sketch and first-ranked final chord suggestions and use the same canonical voicing and arrangement renderer in each pair. The filenames disclose the planner. No audio listening or preference rating was performed.

The scripts have separate roles:

- `agent/run_fixed_seed_plans.py`: live paired generation; requires a fresh output directory and an explicit evaluation ledger. Run seeds sequentially so each run's API usage attribution stays exclusive.
- `agent/report_fixed_seed_plans.py`: validate and pool saved results; repeat `--results` for each seed and supply the same public `--requests` directory.
- `agent/export_plan_samples.py`: render the three predetermined saved pairs as MIDI, validate paired inputs and playback controls, and verify the exported song lengths.

Structural validity, section-type variety and pitch-collection diagnostics are reported separately. A completed trace can still have a final judge requesting regeneration, and the judge examines diagnostic reports rather than hearing the music. These results do not establish musical superiority.
