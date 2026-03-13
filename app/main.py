from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.api import router
from app.services.reference_service import load_reference_documents

settings = get_settings()

app = FastAPI(title=settings.app_name)

# Include API routes
app.include_router(router)

# Serve static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.on_event("startup")
def startup() -> None:
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.processed_dir).mkdir(parents=True, exist_ok=True)
    load_reference_documents()


@app.get("/")
def root():
    """Serve the main frontend page"""
    return FileResponse(str(Path(__file__).parent / "static" / "index.html"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}
