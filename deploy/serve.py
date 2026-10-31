"""One-origin CPU demo server. Configuration and keys come from the environment."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("THEARTIST_PUBLIC_HOST", "1")
os.environ.setdefault("THEARTIST_SERVE_FRONTEND", "1")
os.environ.setdefault("THEARTIST_META_ENABLED", "0")
os.environ.setdefault("THEARTIST_WARMUP", "1")
os.environ.setdefault("THEARTIST_WARMUP_KEYS", "")


def main():
    import uvicorn
    from app.main import app
    from app.services.contracts import capabilities
    from app.services.serving_readiness import require_full_catalog
    from app.services.env_flags import meta_enabled

    models = require_full_catalog()
    print(f"Serving all {len(models)} released model choices", flush=True)
    sources = capabilities().data["rag"]["sources"]
    if sources != {"omt": "ready", "berklee": "disabled"}:
        raise SystemExit("Serving requires prepared OMT and disabled Berklee; run backend/scripts/setup_omt.py")
    if meta_enabled() and not os.getenv("MODEL_API_KEY"):
        raise SystemExit("THEARTIST_META_ENABLED=1 requires the server-side MODEL_API_KEY")
    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "7860")),
                workers=1, limit_concurrency=32, timeout_keep_alive=5, proxy_headers=False)


if __name__ == "__main__":
    main()
