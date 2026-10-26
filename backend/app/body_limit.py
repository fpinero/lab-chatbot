from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyLimitMiddleware:
    """Buffer only bounded JSON bodies before framework deserialization."""

    def __init__(self, app: ASGIApp, maximum: int = 65536) -> None:
        self.app, self.maximum = app, maximum

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PATCH", "PUT"}:
            await self.app(scope, receive, send)
            return
        data = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(data) + len(chunk) > self.maximum:
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
