"""Exercise actual CPU F1 + OMT in the serving environment without paid calls."""
import json
import os
from pathlib import Path
import resource
from statistics import median
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["THEARTIST_PUBLIC_HOST"] = "1"
os.environ["THEARTIST_META_ENABLED"] = "0"
os.environ["THEARTIST_SERVE_FRONTEND"] = "1"
os.environ["THEARTIST_WARMUP_KEYS"] = "ft_f1"


def main():
    import torch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.schemas import SectionGenerateRequest
    from app.routes.generate import compose_section
    from app.services.contracts import capabilities
    from app.services.inference import ModelRegistry

    torch.set_num_threads(2)
    started = time.perf_counter()
    loaded = ModelRegistry.get().load_model("ft_f1")
    if loaded is None or str(loaded.device) != "cpu":
        raise RuntimeError("Expected actual F1 on CPU")
    load_seconds = time.perf_counter() - started
    rag = capabilities().data["rag"]["sources"]
    if rag != {"omt": "ready", "berklee": "disabled"}:
        raise RuntimeError("OMT must be ready and Berklee disabled")
    elapsed = []
    for seed in (17, 18, 19):
        started = time.perf_counter()
        response = compose_section(SectionGenerateRequest(key="C major", genre="pop", sectionType="verse",
                                                           chordCount=16, modelKey="ft_f1", seed=seed))
        elapsed.append(time.perf_counter() - started)
        if response.source != "ai" or response.modelUsed != "ft_f1" or len(response.suggestions) != 3:
            raise RuntimeError("F1 inference did not produce the expected candidates")
        if any(len(s.chords) != 8 for s in response.suggestions):
            raise RuntimeError("Incomplete eight-bar result")
    with TestClient(app) as client:
        health = client.get("/api/health")
        if health.status_code != 200:
            raise RuntimeError("Health endpoint failed")
        frontend = client.get("/")
        if frontend.status_code != 200 or "<html" not in frontend.text.lower():
            raise RuntimeError("Built frontend not served")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB. This is process peak, not VM sizing.
    rss_mib = rss / (1024 ** 2 if sys.platform == "darwin" else 1024)
    print(json.dumps({"platform": sys.platform, "python": sys.version.split()[0], "torch": torch.__version__,
                      "threads": 2, "device": str(loaded.device), "rag": rag, "healthHttp": health.status_code,
                      "frontendHttp": frontend.status_code, "modelLoadSeconds": round(load_seconds, 3),
                      "eightBarSeconds": [round(t, 3) for t in elapsed], "medianSeconds": round(median(elapsed), 3),
                      "processPeakMiB": round(rss_mib, 1), "metaCalls": 0,
                      "scope": "Local serving-environment probe, not container/Linux/cloud capacity verification."}), flush=True)


if __name__ == "__main__":
    main()
