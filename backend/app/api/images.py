from typing import cast

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse

from app.auth.service import AuthError
from app.services.image_catalog import ImageCatalogInfo, ImageEndpointInfo
from app.services.images import ImageInput, ImageQuote, ImageService, ImageStart, MediaJobInfo

router = APIRouter(prefix="/api")


def service(request: Request) -> ImageService:
    return cast(ImageService, request.app.state.images)


@router.get("/images/models", response_model=ImageCatalogInfo)
async def models(request: Request) -> ImageCatalogInfo:
    return await service(request).catalog.get()


@router.post("/images/models/refresh", response_model=ImageCatalogInfo)
async def refresh(request: Request) -> ImageCatalogInfo:
    return await service(request).catalog.get(refresh=True)


@router.get("/images/capabilities", response_model=ImageEndpointInfo)
async def capabilities(
    request: Request, model_id: str = Query(max_length=200)
) -> ImageEndpointInfo:
    return await service(request).catalog.endpoints(model_id)


@router.post("/images/quote", response_model=ImageQuote)
async def quote(body: ImageInput, request: Request) -> ImageQuote:
    return await service(request).preview(request.state.owner_session.owner_id, body)


@router.post("/images/jobs", response_model=MediaJobInfo, status_code=202)
async def start(body: ImageStart, request: Request) -> MediaJobInfo:
    return await service(request).start(request.state.owner_session.owner_id, body)


@router.get("/images/jobs", response_model=list[MediaJobInfo])
def history(request: Request) -> list[MediaJobInfo]:
    return service(request).history(request.state.owner_session.owner_id)


@router.get("/images/jobs/{job_id}", response_model=MediaJobInfo)
def get(job_id: str, request: Request) -> MediaJobInfo:
    return service(request).get(request.state.owner_session.owner_id, job_id)


@router.delete("/images/jobs/{job_id}", status_code=204)
def remove(job_id: str, request: Request, confirm: bool = False) -> Response:
    if not confirm:
        raise AuthError(409, "confirmation_required", "Confirm image job deletion explicitly.")
    service(request).remove(request.state.owner_session.owner_id, job_id)
    return Response(status_code=204)


@router.get("/media/{asset_id}")
def media(asset_id: str, request: Request, download: bool = False) -> FileResponse:
    path, item = service(request).asset(request.state.owner_session.owner_id, asset_id)
    return FileResponse(
        path,
        media_type=item.mime,
        filename=f"{item.id}.webp",
        content_disposition_type="attachment" if download else "inline",
    )
