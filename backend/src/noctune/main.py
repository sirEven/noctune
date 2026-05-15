"""FastAPI application entry point."""

from fastapi import FastAPI

from noctune.api import router as api_router

app = FastAPI(title="Noctune", version="0.1.0")

# Include API routes
app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint (root level)."""
    return {"status": "ok"}