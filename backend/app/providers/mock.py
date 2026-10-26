from typing import Protocol

from pydantic import BaseModel


class PreviewResult(BaseModel):
    model: str
    text: str
    simulated: bool


class PreviewProvider(Protocol):
    async def preview(self, prompt: str) -> PreviewResult: ...


class MockProvider:
    """Deterministic, network-free bootstrap adapter. Never reports real provider usage."""

    async def preview(self, prompt: str) -> PreviewResult:
        return PreviewResult(
            model="mock/echo",
            text=f"Local preview: {prompt}",
            simulated=True,
        )
