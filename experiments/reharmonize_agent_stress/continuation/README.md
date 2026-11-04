# Completing the original Spark 1.3 schedule

After the operator stopped the campaign, the participant explicitly requested
finishing Spark 1.3. This continuation schedules only the original **2,524 unstarted
rows**. It adds no input, repetition or provider. The completed Open schedule,
all started Meta results, 42 failures and one cancellation are preserved exactly.

The earlier [partial report](../summary.md) and [stop decision](../stop-decision.json)
remain historical records. The continuation does not turn the earlier stop into a
preregistered rule. It introduces a temporal break and smaller accounting batches,
which may affect cache conditions, latency and cost. It does not support a musical
superiority or prize-probability claim.

The [plan](plan.json) maps every continuation batch to its original job and repeat.
Each batch contains one original repeat's unstarted inputs, in their original order.
The unchanged campaign runner uses `repeat: 1` within each such batch; the plan's
`originalRepeat` restores its place in the original 8,480-row schedule. Case IDs,
requests, F1 weights, product code, UX, prompts, tools, provider settings and all
per-run bounds are unchanged. Raw results stay in this directory, leaving every
previous result, ledger and report untouched.

Two Meta workers retain their original job ownership. Their remaining caps are
$29.60513855 and $29.66437645, after deducting all earlier accounting, including
unknown usage. Additional nominal accounting is capped at **$59.26951500**;
the estimate from observed average usage is approximately **$30.49**. The original
combined $120 cap remains enforced. These are configured-price budget estimates,
not confirmed invoices or measured credit deductions. Each new batch receives at
most $6, each run remains bounded at $0.15, and the continuation stops within twelve
elapsed hours or on an authentication, credit or ledger error.

The [continuation wrapper](../tools/continue_meta.py) invokes the frozen
`campaign.py` execution function. It refuses duplicate launches and snapshots the
original artifact hashes. [Offline tests](../tools/test_continue_meta.py) check exact
unstarted membership, original worker ownership, failure/cancellation retention,
unchanged requests, duplicate rejection and remaining-budget accounting.

There is no additional experiment after this original schedule. Final work is
offline verification, documentation and synchronization of the two public repositories.
