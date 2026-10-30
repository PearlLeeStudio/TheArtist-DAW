"""Three bounded live Meta plans with actual F1 and chorus reuse; not a preference test."""
import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

from app.models.plan import PlanRequest
from app.services import inference, planner
from app.services.contracts import capabilities
from app.services.env_flags import meta_enabled
from app.services.llm import Ledger, LLMClient, LLMConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    if not args.out.is_absolute() or args.out.exists() or not args.ledger.is_absolute():
        parser.error("Use a new absolute output and an absolute ledger path")
    if not meta_enabled() or not os.getenv("MODEL_API_KEY"):
        parser.error("Meta must be explicitly available with MODEL_API_KEY")
    if capabilities().data["rag"]["sources"] != {"omt": "ready", "berklee": "disabled"}:
        raise SystemExit("Prepare OMT and disable Berklee first")
    if inference.ModelRegistry.get().load_model("ft_f1") is None:
        raise SystemExit("F1 is required before any paid call")
    client = LLMClient(LLMConfig(provider="meta", base_url="https://api.meta.ai/v1", model="muse-spark-1.3",
                               api_key=os.environ["MODEL_API_KEY"], key_source="MODEL_API_KEY"), Ledger(args.ledger, .30))
    output = dict(method="Three functional live plans; no paired quality or latency inference", maxUsd=.30, runs=[])
    for genre, key in (("pop", "C major"), ("pop", "A minor"), ("rock", "E major")):
        start = client.ledger.snapshot()["entries"]
        request = PlanRequest(genre=genre, key=key, targetBars=64, wantOutro=True, chorusMode="reuse",
                              planner="meta", modelKey="ft_f1", seed=17)
        with patch.object(planner, "get_client", return_value=client):
            trace = planner.complete_form(request)
        saved = trace.model_dump(mode="json")
        for section in saved["sections"]:
            for suggestion in section["suggestions"]:
                suggestion["explanations"] = None
        fields = ("label", "provider", "model", "request_id", "usage", "status", "settled_usd", "latency_ms")
        entries = json.loads(client.ledger.path.read_text())["entries"][start:]
        output["runs"].append(dict(request=request.model_dump(mode="json"), trace=saved,
                                   apiUsage=[{field: row.get(field) for field in fields} for row in entries]))
        totals = client.ledger.snapshot()
        output["spendUsd"], output["outstandingUsd"] = totals["spent_usd"], totals["outstanding_usd"]
        args.out.write_text(json.dumps(output, indent=2) + "\n")
        print(f"{genre}/{key}: {trace.status}, reused {sum(s.reuse is not None for s in trace.sections)}, "
              f"judge {trace.judge[-1].decision if trace.judge else 'none'}, ${trace.spendUsd:.6f}", flush=True)
        if trace.status != "ok" or any(s.source not in {"ai", "reuse"} for s in trace.sections):
            raise SystemExit("Smoke failed; retained failure record and stopped further calls")
    print(f"Completed three plans; ${output['spendUsd']:.6f}, outstanding ${output['outstandingUsd']:.6f}")


if __name__ == "__main__":
    main()
