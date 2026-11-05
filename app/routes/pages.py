"""Farmer dashboard pages (Phase 9, HTML only, $0 cost).

Simple version:
- 8 HTML pages under /pages/* plus home at / (see main.py).
- Pages call the SAME backend JSON APIs with fetch; no API is
  changed, renamed, or removed here.
- Page URLs use the /pages prefix on purpose so they can never
  collide with API paths like /weather or /mandi.
- No secrets in HTML or JS. Language (en/ta/hi) is picked in the
  page header and sent with every API call.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/pages", tags=["pages"], include_in_schema=False)

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
templates = Jinja2Templates(directory=os.path.abspath(_TEMPLATES_DIR))


def _page(request: Request, name: str) -> HTMLResponse:
    """Render one dashboard template. No secrets are ever passed in."""
    return templates.TemplateResponse(request, name, {"app_name": "KrishiMitra"})


@router.get("/register", response_class=HTMLResponse)
def page_register(request: Request) -> HTMLResponse:
    """Farmer registration form page."""
    return _page(request, "register.html")


@router.get("/dashboard", response_class=HTMLResponse)
def page_dashboard(request: Request) -> HTMLResponse:
    """Module status dashboard page."""
    return _page(request, "dashboard.html")


@router.get("/chat", response_class=HTMLResponse)
def page_chat(request: Request) -> HTMLResponse:
    """Chatbot page (uses POST /chat)."""
    return _page(request, "chat.html")


@router.get("/image", response_class=HTMLResponse)
def page_image(request: Request) -> HTMLResponse:
    """Crop photo upload page (uses POST /image/analyse)."""
    return _page(request, "image.html")


@router.get("/voice", response_class=HTMLResponse)
def page_voice(request: Request) -> HTMLResponse:
    """Voice note upload page (uses POST /voice/transcribe)."""
    return _page(request, "voice.html")


@router.get("/weather", response_class=HTMLResponse)
def page_weather(request: Request) -> HTMLResponse:
    """Weather page (uses GET /weather)."""
    return _page(request, "weather.html")


@router.get("/mandi", response_class=HTMLResponse)
def page_mandi(request: Request) -> HTMLResponse:
    """Mandi price page (uses GET /mandi)."""
    return _page(request, "mandi.html")


@router.get("/plan", response_class=HTMLResponse)
def page_plan(request: Request) -> HTMLResponse:
    """Rescue plan page (uses GET /plan/{id} and the card link)."""
    return _page(request, "plan.html")
