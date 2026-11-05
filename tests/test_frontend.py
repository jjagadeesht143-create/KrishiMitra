"""Phase 9: farmer dashboard pages render with no key leaks.

Covers: GET / 200 HTML home, all 8 /pages/* render, static files serve,
no secret markers in HTML/JS, and backend APIs unchanged. All checks
use the local TestClient only; no real network happens here.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

PAGES = [
    "/pages/register",
    "/pages/dashboard",
    "/pages/chat",
    "/pages/image",
    "/pages/voice",
    "/pages/weather",
    "/pages/mandi",
    "/pages/plan",
]

# Markers that must never appear in served HTML, CSS, or JS.
SECRET_MARKERS = [
    "META_API_KEY",
    "MODEL_API_KEY",
    "MANDI_API_KEY",
    "WHATSAPP_TOKEN",
    "API_KEY=",
    "Bearer ",
]


def test_home_is_200_html_with_links() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "KrishiMitra" in body
    for page in PAGES:
        assert page in body
    assert "/static/app.js" in body
    assert "/static/style.css" in body


def test_all_pages_render_200() -> None:
    for page in PAGES:
        resp = client.get(page)
        assert resp.status_code == 200, page
        assert "text/html" in resp.headers["content-type"], page
        assert "KrishiMitra" in resp.text, page
        assert "data-lang" in resp.text, page  # language selector present


def test_pages_have_loading_and_error_slots() -> None:
    for page in PAGES:
        if page == "/pages/dashboard":
            continue  # dashboard loads tiles on open; checked below
        body = client.get(page).text
        assert "data-loading" in body, page
        assert "data-error" in body, page
        assert "data-result" in body, page


def test_dashboard_loads_status_tiles() -> None:
    body = client.get("/pages/dashboard").text
    assert "status-tiles" in body
    assert "data-loading" in body


def test_upload_pages_mention_file_rules() -> None:
    image = client.get("/pages/image").text
    assert "10 MB" in image
    assert "accept=" in image
    voice = client.get("/pages/voice").text
    assert "10 MB" in voice
    assert "accept=" in voice


def test_static_files_serve() -> None:
    css = client.get("/static/style.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]
    assert "fetch" in js.text


def test_no_secret_markers_in_frontend() -> None:
    bodies = [client.get("/").text]
    bodies += [client.get(page).text for page in PAGES]
    bodies.append(client.get("/static/app.js").text)
    bodies.append(client.get("/static/style.css").text)
    for body in bodies:
        for marker in SECRET_MARKERS:
            assert marker not in body, marker


def test_js_uses_relative_fetch_only() -> None:
    js = client.get("/static/app.js").text
    assert "http://" not in js
    assert "https://" not in js
    assert '"/farmers/"' in js
    assert '"/chat"' in js
    assert "/image/analyse" in js
    assert "/voice/transcribe" in js


def test_backend_apis_unchanged() -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/health").json()["status"] == "healthy"
    for status_url in (
        "/ai/status",
        "/chat/status",
        "/voice/status",
        "/image/status",
        "/weather/status",
        "/mandi/status",
        "/plan/status",
        "/whatsapp/status",
    ):
        assert client.get(status_url).status_code == 200, status_url
    # Classic API paths still JSON (pages did not steal them).
    resp = client.get("/weather", params={"location": "x" * 121})
    assert resp.status_code == 400
    assert client.get("/mandi", params={"crop": "   "}).status_code == 400


# ---- Premium dashboard (single page at /) ----

PREMIUM_VIEWS = [
    "view-dashboard",
    "view-chat",
    "view-image",
    "view-voice",
    "view-weather",
    "view-mandi",
    "view-plan",
    "view-register",
]


def test_home_loads_premium_assets() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "KrishiMitra" in body
    assert "/static/css/style.css" in body
    assert "/static/js/i18n.js" in body
    assert "/static/js/app.js" in body


def test_home_has_all_views_nav_and_language() -> None:
    body = client.get("/").text
    for view in PREMIUM_VIEWS:
        assert view in body, view
    for key in ("nav_dashboard", "nav_chat", "nav_image", "nav_voice",
                "nav_weather", "nav_mandi", "nav_plan", "nav_register"):
        assert key in body, key
    assert "data-i18n" in body
    assert "data-lang-btn" in body
    # Upload rules stay visible without running JS.
    assert "10 MB" in body
    assert "accept=" in body


def test_premium_static_files_serve() -> None:
    css = client.get("/static/css/style.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert "--primary" in css.text
    assert "@media" in css.text
    for path in ("/static/js/i18n.js", "/static/js/app.js"):
        js = client.get(path)
        assert js.status_code == 200, path
        assert "javascript" in js.headers["content-type"], path
    assert "fetch" in client.get("/static/js/app.js").text


def test_premium_js_uses_backend_contracts() -> None:
    js = client.get("/static/js/app.js").text
    # Exact backend routes only; ai_reply conversation contract for chat.
    assert '"/farmers/"' in js
    assert "/conversations?ai_reply=true" in js
    assert 'role: "farmer"' in js
    assert '"role":"farmer"' in js or '"farmer"' in js
    assert "/image/analyse" in js
    assert "/voice/transcribe" in js
    assert "/weather?" in js
    assert "/mandi?" in js
    assert "/plan/" in js
    # No legacy role placeholder that would 422.
    assert "role:user" not in js
    assert '"role": "user"' not in js
    assert '"role":"user"' not in js


def test_premium_js_relative_fetch_only() -> None:
    for path in ("/static/js/i18n.js", "/static/js/app.js"):
        js = client.get(path).text
        assert "http://" not in js, path
        assert "https://" not in js, path


def test_no_secret_markers_in_premium_frontend() -> None:
    bodies = [
        client.get("/").text,
        client.get("/static/css/style.css").text,
        client.get("/static/js/i18n.js").text,
        client.get("/static/js/app.js").text,
    ]
    for body in bodies:
        for marker in SECRET_MARKERS:
            assert marker not in body, marker
    home = bodies[0]
    assert "MODEL_API_KEY" not in home
    assert "WHATSAPP_TOKEN" not in home


def test_i18n_covers_three_languages() -> None:
    js = client.get("/static/js/i18n.js").text
    for code in ("en", "ta", "hi"):
        assert ('"%s"' % code) in js or ("'%s'" % code) in js, code
    # Spot-check keys rendered by the home page exist in the dictionary.
    for key in ("nav_dashboard", "chat_send", "image_analyze",
                "weather_get", "mandi_get", "plan_get", "reg_submit"):
        assert key in js, key
