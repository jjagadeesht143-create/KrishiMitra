"""KrishiMitra FastAPI entry point.

Phase 10: + weather (real Open-Meteo API) and mandi prices (real
data.gov.in API when configured). Honest "data unavailable" whenever
data is missing - nothing invented.
FastAPI + SQLite are supporting infrastructure, not Meta services.
"""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

from app import models
from app.database import engine
from app.routes import (
    ai,
    chat,
    farmer,
    image,
    mandi,
    pages,
    plan,
    voice,
    weather,
    whatsapp,
)

# Create the SQLite tables (farmers, conversations) if missing.
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="KrishiMitra", version="0.2.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.include_router(farmer.router)
app.include_router(ai.router)
app.include_router(chat.router)
app.include_router(whatsapp.router)
app.include_router(whatsapp.alias_router)
app.include_router(voice.router)
app.include_router(image.router)
app.include_router(plan.router)
app.include_router(weather.router)
app.include_router(mandi.router)
app.include_router(pages.router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> HTMLResponse:
    """Farmer dashboard home page (Phase 9). JSON health stays at /health."""
    return templates.TemplateResponse(
        request, "index.html", {"app_name": "KrishiMitra"}
    )


@app.get("/health")
def health() -> dict:
    """Health check: app + SQLite database."""
    return {"status": "healthy", "database": "sqlite connected"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Stop browser favicon 404. Returns empty 204 response."""
    return Response(status_code=204)
