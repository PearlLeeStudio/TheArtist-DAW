"""Version and bounded result envelope shared by HTTP discovery and MCP."""

import base64
import binascii
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models.export import MAX_EXPORT_BYTES, MAX_EXPORT_MEASURES
from app.models.score_import import MAX_SCORE_BYTES, MAX_SCORE_MEASURES

SCHEMA_VERSION = "1.0"
MAX_JSON_STATE_BYTES = 1024 * 1024
MAX_MCP_RESULT_BYTES = 6 * 1024 * 1024
MAX_MCP_REQUEST_BYTES = 12 * 1024 * 1024
TOOLS = ("capabilities", "list_models", "list_genres", "get_genre_preset", "generate_section",
         "build_song", "render_midi", "import_score", "export_daw")


class ContractEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"] = SCHEMA_VERSION
    data: dict[str, Any]


def json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf8"))


def contract_result(data: BaseModel | dict) -> ContractEnvelope:
    payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
    # Binary content has its own limit; music JSON remains bounded independently.
    state = {key: value for key, value in payload.items() if key not in ("midi_b64", "dataBase64")}
    if json_size(state) > MAX_JSON_STATE_BYTES:
        raise ValueError("Music JSON exceeds the 1 MiB state limit.")
    for key in ("midi_b64", "dataBase64"):
        if key in payload:
            encoded = payload[key]
            if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_EXPORT_BYTES + 2) // 3):
                raise ValueError("MIDI exceeds the 4 MiB binary limit.")
            try:
                binary = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                raise ValueError("The MIDI result is not valid base64.") from None
            if not 14 <= len(binary) <= MAX_EXPORT_BYTES or not binary.startswith(b"MThd"):
                raise ValueError("The MIDI result is invalid or exceeds 4 MiB.")
    envelope = ContractEnvelope(data=payload)
    if json_size(envelope.model_dump()) > MAX_MCP_RESULT_BYTES:
        raise ValueError("The tool result exceeds the 6 MiB envelope limit.")
    return envelope


def capabilities() -> ContractEnvelope:
    return contract_result({
        "name": "TheArtist", "transport": "streamable-http", "endpoint": "/mcp/",
        "tools": list(TOOLS),
        "contracts": {"generate_section": "SectionGenerateRequest / SectionGenerateResponse",
                      "build_song": "SongGenerateRequest / SongGenerateResponse",
                      "render_midi": "ExportSpec / MIDI bytes", "import_score": "ScoreImportRequest / ScoreImportResponse"},
        "limits": {"jsonStateBytes": MAX_JSON_STATE_BYTES, "midiBytes": MAX_EXPORT_BYTES,
                   "toolResultBytes": MAX_MCP_RESULT_BYTES, "requestBytes": MAX_MCP_REQUEST_BYTES,
                   "scoreFileBytes": MAX_SCORE_BYTES, "scoreMeasures": MAX_SCORE_MEASURES,
                   "exportMeasures": MAX_EXPORT_MEASURES, "generatedBars": 64},
        "sourceFields": {"generate_section": ["source", "modelUsed"], "build_song": ["model_used", "tracks.*.source", "seed"],
                         "import_score": ["model", "requestId"]},
        "limitations": ["build_song returns one arrangement; candidate fan-out is not implemented.",
                        "Score import requires an explicitly attached PDF/image and may incur Meta API cost.",
                        "export_daw requires a loopback request, server opt-in, and explicit per-call confirmation.",
                        "Song planning and theory explanation are not MCP tools yet."],
    })
