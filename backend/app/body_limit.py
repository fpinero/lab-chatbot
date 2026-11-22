import asyncio
from uuid import uuid4

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyLimitMiddleware:
    """Buffer only bounded JSON bodies before framework deserialization."""

    def __init__(self, app: ASGIApp, maximum: int = 65536, upload_maximum: int = 26476544) -> None:
        self.app, self.maximum = app, maximum
        self.upload_maximum = upload_maximum
        self.temporary_slots = asyncio.Semaphore(2)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope.get("path", "").startswith("/api/temporary-chats/")
            and scope.get("path", "").endswith("/attachments")
            and scope.get("method") == "POST"
        ):
            if self.temporary_slots.locked():
                response = JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "upload_busy",
                            "message": "The upload processor is busy. Try again shortly.",
                            "request_id": uuid4().hex,
                            "retryable": False,
                        }
                    },
                    headers={"Cache-Control": "no-store", "Retry-After": "5"},
                )
                await response(scope, receive, send)
                return
            async with self.temporary_slots:
                await self.bounded(scope, receive, send)
            return
        await self.bounded(scope, receive, send)

    async def bounded(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PATCH", "PUT"}:
            await self.app(scope, receive, send)
            return
        if scope.get("path") == "/api/attachments":
            total = 0

            async def upload_receive() -> Message:
                nonlocal total
                message = await receive()
                total += len(message.get("body", b""))
                if total > self.upload_maximum:
                    raise MultiPartException("Upload byte ceiling exceeded.")
                return message

            await self.app(scope, upload_receive, send)
            return
        data = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            ceiling = (
                self.upload_maximum * 4 // 3 + 65536
                if scope.get("path", "").startswith("/api/temporary-chats/")
                and scope.get("path", "").endswith("/attachments")
                else self.maximum
            )
            if len(data) + len(chunk) > ceiling:
                request_id = uuid4().hex
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "body_too_large",
                            "message": "Request body exceeds its size limit.",
                            "request_id": request_id,
                            "retryable": False,
                        }
                    },
                    headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return
            data.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(data), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
