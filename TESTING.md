# KrishiMitra Testing Checklist

260 pytest tests green, real `uvicorn` boot green, `check_setup.py` green.
Last full run: 2026-11-04 (see final report in chat).

## Quick commands (PowerShell, from this folder, .venv on)

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -q    # full suite, ~15 s, $0 (hermetic mock)
python check_setup.py          # setup gate
uvicorn main:app --host 127.0.0.1 --port 8000   # real server, Ctrl+C to stop
```

Tests use an isolated temp SQLite DB (`tests/conftest.py`) and temp upload
dirs — they never touch `data/krishimitra.db` or `uploads/`. Network is
mocked; `conftest.py` blanks API keys and forces mock mode, so the suite
can never spend real API quota even with real keys in `.env`.

## Coverage (all green)

- Core: `/`, `/health`, real boot, setup gate.
- Farmers + database: register, unique phone, get/list, 404s, language
  validation, conversation round-trip + order, AI reply option.
- Chat multilingual (Tamil/Hindi/English): auto-detect, explicit
  override, 5-key shape, history + preference persistence.
- Real AI paths (mocked HTTP): chat success/shape/fallbacks, vision
  success/shape/dosage scrub, shared-credential fallback, key precedence.
- Structured AI plan: prompt content, JSON parsing, broken-output
  fallback, dosage scrubbing, Tamil/Hindi/English mock content.
- Voice upload: extensions, size, language, mock transcript, no Whisper.
- Image upload: extensions, magic bytes, size, language, analysis shape.
- Rescue plan: personalised JSON + shareable card, follow-up schedule,
  report form validation (all fields, ranges, Tamil), report history
  endpoint, banned-token scans.
- Weather + mandi: Open-Meteo parsers, honest unavailable, no invented
  data, key never leaks.
- WhatsApp: webhook verify (200/403), receiver shape tolerance,
  signature check, dedupe, send mock/success/failure shapes, status flags.
- Frontend: pages serve, trilingual keys, backend contracts, relative
  fetch only, no secret markers in HTML/JS/CSS.
- Security: validation errors are 400s, unknown farmers 404, uploads
  isolated, `.env`/DB/uploads gitignored.

## Live verifications (this session, real API)

- Chat completions EN/TA/HI genuine replies, model `muse-spark-1.3`.
- Vision EN/TA genuine analysis via documented image_url format.
- Rescue-plan JSON: all 8 keys parsed from a live response.
- Report flow end-to-end in real mode (EN + Tamil).
- Weather live (Madurai), mandi honestly unavailable.
- Invalid key → 401 handled; timeout → explicit fallback.
- WhatsApp: code + mock tests only — live send NOT verified (needs
  Meta credentials + phone verification; see README).

## Known non-issues (do not "fix")

- `starlette.testclient` deprecation warning: upstream warning only.
- Voice transcript is mock until Meta speech access is configured.
- Mandi needs a data.gov.in key (manual step in README).
