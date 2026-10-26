from typing import cast

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from app.auth.service import AuthError
from app.services.attachments import AttachmentInfo, AttachmentService

router = APIRouter(prefix="/api/attachments")


def service(request: Request) -> AttachmentService:
    return cast(AttachmentService, request.app.state.attachments)


class UploadLimits(BaseModel):
    files: int
    file_bytes: int
    total_bytes: int
    allowed_extensions: list[str]
    vision_allowance_microusd: int


@router.get("/limits", response_model=UploadLimits)
def limits(request: Request) -> UploadLimits:
    from app.services.attachments import MIMES
    from app.services.runs import allowance_microusd

    config = service(request).settings
    return UploadLimits(
        files=config.max_upload_files,
        file_bytes=config.max_upload_file_bytes,
        total_bytes=config.max_upload_total_bytes,
        allowed_extensions=list(MIMES),
        vision_allowance_microusd=allowance_microusd(config.vision_request_allowance_usd),
    )


@router.post(
    "",
    response_model=list[AttachmentInfo],
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["files"],
                        "properties": {
                            "files": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                            }
                        },
                    }
                }
            },
        }
    },
)
async def upload(request: Request) -> list[AttachmentInfo]:
    assets = service(request)
    if assets.upload_slots.locked():
        raise AuthError(429, "upload_busy", "The upload processor is busy. Try again shortly.")
    assets.reserve_upload(request.state.owner_session.owner_id)
    async with assets.upload_slots:
        try:
            async with request.form(
                max_files=assets.settings.max_upload_files + 1, max_fields=0
            ) as form:
                files = [
                    value
                    for key, value in form.multi_items()
                    if key == "files" and isinstance(value, UploadFile)
                ]
                if len(files) != len(form.multi_items()):
                    raise AuthError(422, "invalid_upload", "Send files in the files field only.")
                return await assets.upload(request.state.owner_session.owner_id, files)
        except HTTPException as exc:
            if exc.detail == "Upload byte ceiling exceeded.":
                raise AuthError(
                    413, "upload_size", "Upload exceeds the total streamed byte limit."
                ) from None
            raise AuthError(
                422, "invalid_upload", "Check multipart upload fields and file count."
            ) from None


@router.get("/{attachment_id}/metadata", response_model=AttachmentInfo)
def metadata(attachment_id: str, request: Request) -> AttachmentInfo:
    assets = service(request)
    with Session(assets.engine) as db:
        return assets.info(assets.get(db, request.state.owner_session.owner_id, attachment_id))


@router.get("/{attachment_id}")
def download(attachment_id: str, request: Request) -> FileResponse:
    assets = service(request)
    with Session(assets.engine) as db:
        item = assets.get(db, request.state.owner_session.owner_id, attachment_id)
        path = assets.path(item)
        if not path.is_file():
            raise AuthError(404, "not_found", "Attachment is unavailable.")
        name = (
            item.display_name
            if item.kind == "document"
            else item.display_name.rsplit(".", 1)[0] + ".webp"
        )
        return FileResponse(
            path,
            media_type=item.mime,
            filename=name,
            content_disposition_type="inline" if item.kind == "image" else "attachment",
        )


@router.delete("/{attachment_id}", status_code=204)
def remove(attachment_id: str, request: Request) -> Response:
    service(request).remove(request.state.owner_session.owner_id, attachment_id)
    return Response(status_code=204)
