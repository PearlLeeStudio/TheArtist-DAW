"""Exercise every released model on CPU without Meta calls; print JSON measurements."""
import os
os.environ["THEARTIST_PUBLIC_HOST"] = "1"
os.environ["THEARTIST_META_ENABLED"] = "0"
os.environ["THEARTIST_SERVE_FRONTEND"] = "1"
os.environ["THEARTIST_RAG_OMT_ENABLED"] = "1"
os.environ["THEARTIST_RAG_BERKLEE_ENABLED"] = "0"
os.environ["THEARTIST_DISABLE_RAG"] = "0"
os.environ["THEARTIST_WARMUP"] = "1"
os.environ["THEARTIST_WARMUP_KEYS"] = ""
os.environ["CUDA_VISIBLE_DEVICES"] = ""
import sys, json, time, resource
from pathlib import Path
from statistics import median
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import torch
from app.services.inference import CHECKPOINTS, ModelRegistry
from app.models.schemas import SectionGenerateRequest
from app.routes.generate import compose_section
from app.services.contracts import capabilities
torch.set_num_threads(2)
torch.set_num_interop_threads(1)
def peak_mib():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2 if sys.platform == "darwin" else 1024), 1)
registry = ModelRegistry.get()
rows = []
from app.services.serving_readiness import require_full_catalog
start = time.perf_counter()
require_full_catalog()
for key in CHECKPOINTS:
    loaded = registry.load_model(key)
    if loaded is None or loaded.name != key or str(loaded.device) != "cpu":
        raise RuntimeError(f"Not the requested CPU model: {key}")
    rows.append({"key":key, "parameters":sum(p.numel() for p in loaded.model.parameters())})
load_seconds = round(time.perf_counter()-start, 3)
loaded_peak = peak_mib()
print(json.dumps({"loaded":len(rows),"allModelsResident":True,"loadSeconds":load_seconds,"loadedPeakMiB":loaded_peak}), flush=True)
rag = capabilities().data["rag"]["sources"]
assert rag == {"omt":"ready","berklee":"disabled"}, rag
for row in rows:
    key = row["key"]
    genre = key.removeprefix("ft_f1_lora_") if key.startswith("ft_f1_lora_") else "pop" if key in ("phase0","ft_f1") else "jazz"
    row["timings"] = {}
    for bars in (8,32,64):
        elapsed = []
        for seed in (17,18,19):
            start = time.perf_counter()
            response = compose_section(SectionGenerateRequest(key="C major", genre=genre, sectionType="verse", chordCount=bars*2, modelKey=key, seed=seed))
            elapsed.append(round(time.perf_counter()-start,4))
            assert response.source == "ai" and response.modelUsed == key, (key,response.source,response.modelUsed)
            assert len(response.suggestions) == 3 and all(len(s.chords)==bars for s in response.suggestions), key
        row["timings"][str(bars)] = {"seconds":elapsed,"medianSeconds":round(median(elapsed),4)}
    row["processPeakMiB"] = peak_mib()
    print(json.dumps(row),flush=True)
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    health = client.get("/api/health")
    assert health.status_code == 200, health.text
    frontend = client.get("/")
    assert frontend.status_code == 200 and "<html" in frontend.text.lower()
weight_files = set()
for path in CHECKPOINTS.values():
    if path.is_file():
        weight_files.add(path)
    else:
        weight_files.update(p for p in path.rglob("*") if p.is_file() and p.suffix in (".pt",".safetensors"))
report = {
    "scope":"CPU runtime probe with all released models resident in one process; sequential requests, not GPU, concurrent-user or end-to-end network capacity.",
    "platform":sys.platform,"python":sys.version.split()[0],"torch":torch.__version__,"threads":2,"interopThreads":1,"device":"cpu",
    "modelCount":len(rows),"baseCount":sum(not r["key"].startswith("ft_f1_lora_") for r in rows),
    "loraCount":sum(r["key"].startswith("ft_f1_lora_") for r in rows),
    "requestCount":len(rows)*9,"candidateCount":len(rows)*27,"allModelsResident":True,
    "weightsBytes":sum(p.stat().st_size for p in weight_files),
    "parameterBytes":sum(r["parameters"]*4 for r in rows),
    "loadSeconds":load_seconds,"loadedPeakMiB":loaded_peak,"processPeakMiB":peak_mib(),
    "healthHttp":health.status_code,"frontendHttp":frontend.status_code,"rag":rag,"metaCalls":0,"models":rows
}

print(json.dumps(report),flush=True)

