"""Phase 1 setup checker for KrishiMitra.

Run:  python check_setup.py
Pass: prints ALL CHECKS PASSED at the end.
"""

from __future__ import annotations

import importlib.util
import os
import sys

EXPECTED_FILES = [
    "main.py",
    "requirements.txt",
    ".env",
    ".env.example",
    ".gitignore",
    "README.md",
    "check_setup.py",
    "app/__init__.py",
    "app/database.py",
    "app/models.py",
    "app/schemas.py",
    "app/services/__init__.py",
    "app/services/meta_ai_service.py",
    "app/services/whatsapp_service.py",
    "app/services/voice_service.py",
    "app/services/image_service.py",
    "app/services/weather_service.py",
    "app/services/mandi_service.py",
    "app/services/rescue_plan_service.py",
    "app/routes/__init__.py",
    "app/routes/chat.py",
    "app/routes/whatsapp.py",
    "app/routes/farmer.py",
]

EXPECTED_DIRS = ["app", "app/services", "app/routes", "data", "uploads", "static", "templates"]

REQUIRED_PACKAGES = ["fastapi", "uvicorn", "dotenv", "sqlalchemy", "httpx", "jinja2"]

failures: list[str] = []


def check(name: str, ok: bool, hint: str = "") -> None:
    """Print one check line and record failures."""
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" - {hint}" if hint and not ok else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    print("KrishiMitra Phase 1 setup check")
    print(f"Python: {sys.version.split()[0]} (need 3.10+)")
    check("Python version >= 3.10", sys.version_info >= (3, 10), "Install Python 3.10+")

    root = os.path.dirname(os.path.abspath(__file__))
    for folder in EXPECTED_DIRS:
        check(f"Folder {folder}/", os.path.isdir(os.path.join(root, folder)))
    for filename in EXPECTED_FILES:
        check(f"File {filename}", os.path.isfile(os.path.join(root, filename)))

    for package in REQUIRED_PACKAGES:
        found = importlib.util.find_spec(package) is not None
        check(
            f"Package {package}",
            found,
            "Run: .\\.venv\\Scripts\\Activate.ps1 then pip install -r requirements.txt",
        )

    # .env must be ignored by git (never commit real keys)
    gitignore = os.path.join(root, ".gitignore")
    ignored = False
    if os.path.isfile(gitignore):
        with open(gitignore, encoding="utf-8") as handle:
            ignored = any(line.strip() == ".env" for line in handle)
    check(".env in .gitignore", ignored, "Add a line with exactly .env to .gitignore")

    # main.py must define the FastAPI app with GET /
    try:
        sys.path.insert(0, root)
        import main as app_module

        has_app = hasattr(app_module, "app")
        check("main.py defines app", has_app)
        if has_app:
            routes = [getattr(r, "path", "") for r in app_module.app.routes]
            check("GET / route exists", "/" in routes)
    except Exception as exc:  # noqa: BLE001 - show the real error to a beginner
        check("main.py imports cleanly", False, str(exc))

    print()
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED. Fix the lines above, then re-run.")
        return 1
    print("ALL CHECKS PASSED - Phase 1 setup is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
