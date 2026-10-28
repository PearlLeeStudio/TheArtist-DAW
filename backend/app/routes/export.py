from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.models.export import DawOpenRequest, DawOpenResponse, DawTargetsResponse, ExportSpec
from app.services.daw_launcher import DawError, daw_targets, open_daw
from app.services.smf_export import ExportError, render_midi, safe_title

class ExportRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # Omit raw input values, including NaN/Infinity which cannot appear in JSON errors.
                error = exc.errors()[0]
                location = ".".join(str(part) for part in error["loc"])
                raise HTTPException(status_code=422, detail=f"Invalid export data at {location}: {error['msg']}") from None
        return validated


router = APIRouter(route_class=ExportRoute)


@router.post("/export/midi")
def export_midi_route(spec: ExportSpec) -> Response:
    try:
        data = render_midi(spec)
    except ExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    filename = quote(safe_title(spec.title) + ".mid", safe="")
    return Response(content=data, media_type="audio/midi", headers={
        "Content-Disposition": f"attachment; filename=\"score.mid\"; filename*=UTF-8''{filename}",
        "Cache-Control": "no-store",
    })


@router.get("/daw/targets", response_model=DawTargetsResponse)
def daw_targets_route() -> DawTargetsResponse:
    return daw_targets()


@router.post("/daw/open", response_model=DawOpenResponse)
def open_daw_route(req: DawOpenRequest) -> DawOpenResponse:
    try:
        return open_daw(req.target, req.spec)
    except (DawError, ExportError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
