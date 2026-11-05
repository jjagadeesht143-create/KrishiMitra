# KrishiMitra – AI Farmer Friend

AI farming assistant for Indian farmers, built for the Meta AI Developer
Hackathon. Farmers chat in Tamil, Hindi, and English with text, voice
notes, and crop photos, and get a personalised Crop Rescue Plan.

Live status: real Meta Model API connected (`muse-spark-1.3`, verified),
260/260 tests green, dashboard + API running locally.

## What is Meta and what is not

- **Meta AI:** Meta Model API (`muse-spark-1.3`, chat + image
  understanding), Meta WhatsApp Cloud API. Verified against
  <https://dev.meta.ai/docs> — no invented endpoints.
- **Supporting infrastructure (NOT Meta services):** Python + FastAPI
  (web server), SQLite (local database), HTML/CSS/JS (dashboard),
  Open-Meteo (free weather data), data.gov.in (mandi prices when
  configured). These carry messages and store history only.

We never use OpenAI, Groq, Gemini, Whisper, Twilio, or Supabase.

## Features

- AI chatbot (Tamil/Hindi/English, auto-detect, remembers history).
- Crop disease photo analysis (real vision, low-confidence honesty,
  organic-first guidance, expert referral, never a certain diagnosis).
- Rescue Plan form (crop, stage, symptoms, area %, days, soil,
  irrigation, location, weather, photo) → structured 8-key AI plan +
  rule-based safe steps + follow-up schedule + shareable card.
- Real weather (Open-Meteo) with farming precautions.
- Mandi prices only from data.gov.in when configured — otherwise an
  honest "unavailable", never invented numbers.
- WhatsApp webhook receiver + AI replies (mock until Meta credentials
  and phone verification are configured; see below).
- Voice note upload (mock transcript until Meta speech access exists).
- Trilingual responsive dashboard with service-status card.

## Real vs mock

- Real mode needs `META_API_KEY` (+ verified chat URL, already in
  `.env.example`) and `USE_MOCK_AI=false`. Every AI answer carries its
  mode (`real` / `mock` / `fallback`) and the UI badges it — failures
  are never silent.
- Mock mode (empty keys or `USE_MOCK_AI=true`) returns safe generic
  guidance for free development and offline demos. Tests always run
  hermetic-mock and can never spend API quota.

## Project layout

```text
main.py                 FastAPI app (routers, dashboard, /health)
app/
  config.py             settings (.env, mock/real switch, WhatsApp)
  database.py models.py schemas.py   SQLite + validation
  ai_service.py         Muse Spark text client (mock-safe)
  services/             chatbot, meta_ai, image, voice, weather,
                        mandi, rescue_plan, ai_plan, whatsapp, language
  routes/               farmer, chat, ai, image, voice, plan,
                        weather, mandi, whatsapp, pages
templates/ static/      dashboard + trilingual JS/CSS
tests/                  260 pytest tests (mocked HTTP, temp DB)
data/ uploads/          local SQLite DB + farmer files (gitignored)
.env.example            config template (no secrets)
DEMO_SCRIPT.md          3-minute hackathon demo
```

## Setup on Windows 11 (PowerShell)

```powershell
cd C:\Users\jjaga\OneDrive\Desktop\KrishiMitra
python --version   # need 3.10+
python -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env   # then fill keys by hand, never commit .env
python check_setup.py   # expect ALL CHECKS PASSED
python -m pytest tests/ -q   # expect 260 passed (no API spend)
```

## Run locally

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/> in your browser — dashboard,
API docs at <http://127.0.0.1:8000/docs>. Press Ctrl+C to stop.

## Key API routes

- `POST /farmers/` — register; `GET /farmers/{id}/conversations` — history.
- `POST /chat` — multilingual chatbot turn.
- `POST /image/analyse` — crop photo analysis (jpg/png/webp, 10 MB).
- `POST /plan/{id}/report` — rescue-report form + structured AI plan.
- `GET /plan/{id}`, `/plan/{id}/card`, `/plan/{id}/reports` — plan outputs.
- `GET /weather?city=`, `GET /mandi?crop=` — weather + prices.
- `POST /voice/transcribe` — voice note (mock transcript for now).
- `GET/POST /whatsapp/webhook`, `POST /whatsapp/send` — WhatsApp.
- `GET /{module}/status` — honest per-module status incl. AI mode.

## WhatsApp setup (manual, needs your Meta account)

1. At <https://developers.facebook.com> create an app, add the WhatsApp
   product, and open API Setup.
2. Copy the temporary token → `WHATSAPP_TOKEN`, the Phone number ID →
   `WHATSAPP_PHONE_NUMBER_ID` in `.env`.
3. Webhook → Subscribe: callback URL = your public server URL +
   `/whatsapp/webhook`, verify token = your `WHATSAPP_VERIFY_TOKEN`
   (default `test123`); subscribe to `messages`.
4. App settings → App Secret → `WHATSAPP_APP_SECRET` (enables
   signature verification).
5. Restart the backend and send a message to the test number.
   Dashboard service card flips to WhatsApp: Ready. Localhost needs a
   public tunnel (e.g. ngrok) for Meta to reach the webhook.

Without steps 1–5 the receiver stays in honest mock mode: webhooks are
accepted and answered locally but no real messages flow.

## Mandi setup (manual)

Get a free key at <https://data.gov.in>, then set `MANDI_API_KEY` and
the Agmarknet resource URL (`MANDI_API_BASE_URL`) from its API page.
Until then `/mandi` honestly reports unavailable.

## Safety rules (enforced in code + tests)

- Never a certain diagnosis; confidence shown, clearer photo requested.
- Never pesticide names/doses (model output is scrubbed), weather, or
  prices invented.
- Organic and cultural methods first, always.
- Missing details produce follow-up questions + expert referral.
- Secrets live only in `.env` (gitignored); nothing secret reaches the
  frontend, logs, or tests.

## Demo

See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for the 3-minute Tamil-first demo
with fallback lines.
