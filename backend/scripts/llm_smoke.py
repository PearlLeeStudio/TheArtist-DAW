"""One real LLM call: plan a short pop song form in C major with the editor's section ids.

Run from backend/:
    uv run python -m scripts.llm_smoke --dry-run      print the request and its reserved cost; no network
    uv run python -m scripts.llm_smoke [--out PATH]   one billed call through app.services.llm

Prints the request id, model, token usage, cost and the JSON reply. --out writes that
record as JSON: never the key, and no response header other than the request id.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.sections import CHORDS_PER_BAR, SECTION_TYPES
from app.services.llm import LLMClient, LLMConfig, LLMError, LLMResult, PreparedRequest

LABEL = "smoke.song_form"
SCHEMA_NAME = "song_form"
MAX_COMPLETION_TOKENS = 1024
SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(SECTION_TYPES)},
                    "chordCount": {"type": "integer"},
                },
            },
        },
    },
}
MESSAGES = [
    {"role": "system", "content": (
        f"You plan song forms for a chord editor with {CHORDS_PER_BAR} chord slots per bar, so a "
        f"section's chordCount is {CHORDS_PER_BAR} times its bar count. Reply with JSON only.")},
    {"role": "user", "content": (
        "Plan a short pop song in C major: four to six sections, each with a chordCount between 4 and 16. "
        f"Use only these section ids: {', '.join(SECTION_TYPES)}.")},
]


def _print_dry_run(cfg: LLMConfig, prepared: PreparedRequest, ledger: dict[str, Any]) -> None:
    print("dry run: nothing is sent")
    print(f"provider  {cfg.provider}  {cfg.base_url}")
    print(f"model     {cfg.model}")
    print(f"key       {cfg.key_source} ({'set' if cfg.api_key else 'not set'})")
    print(f"prices    ${cfg.price_input_per_m:g} input / ${cfg.price_cached_per_m:g} cached / "
          f"${cfg.price_output_per_m:g} output per 1M tokens ({cfg.price_source})")
    print(f"timeout   {prepared.timeout_s:g}s, no retries")
    print(f"reserve   ${prepared.reserve_usd:.6f} (~{prepared.input_tokens_estimate} input tokens "
          f"+ {MAX_COMPLETION_TOKENS} completion tokens at the output price)")
    print(f"ledger    {ledger['path']}: spent ${ledger['spent_usd']:.4f}, outstanding "
          f"${ledger['outstanding_usd']:.4f}, cap ${ledger['cap_usd']:.2f}")
    print("request body:")
    print(json.dumps(prepared.body, indent=2))


def _print_result(client: LLMClient, result: LLMResult) -> None:
    usage = result.usage
    spent = client.ledger.snapshot()["spent_usd"]
    print(f"request_id  {result.request_id}")
    print(f"model       {result.model} ({result.provider})")
    print(f"tokens      in {usage.get('prompt_tokens')} (cached {usage.get('cached_tokens')}), "
          f"out {usage.get('completion_tokens')} (reasoning {usage.get('reasoning_tokens')})")
    print(f"cost        ${result.cost_usd:.6f} (ledger ${spent:.4f} of ${client.ledger.cap_usd:.2f})")
    print(f"latency     {result.latency_ms} ms")
    print(json.dumps(result.data, indent=2))


def _write_record(path: Path, result: LLMResult) -> None:
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **result.to_dict()}
    record.pop("text")  # the same reply as data, unparsed
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One real LLM call that plans a short pop song form.")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the request and its reserved cost, then exit without network I/O")
    parser.add_argument("--out", type=Path, help="write the call record as JSON (ignored with --dry-run)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")

    try:
        client = LLMClient()
        prepared = client.prepare(MESSAGES, SCHEMA, name=SCHEMA_NAME, max_completion_tokens=MAX_COMPLETION_TOKENS)
        ledger = client.ledger.snapshot()
    except LLMError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run(client.config, prepared, ledger)
        return 0

    try:
        result = client.chat_json(MESSAGES, SCHEMA, name=SCHEMA_NAME, label=LABEL,
                                  max_completion_tokens=MAX_COMPLETION_TOKENS)
    except LLMError as exc:
        print(f"FAILED ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    _print_result(client, result)
    if args.out:
        _write_record(args.out, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
