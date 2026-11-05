# KrishiMitra – 3-Minute Hackathon Demo Script

Total: ~3 minutes. Language: start in Tamil, finish in English.
Server must be running: `uvicorn main:app --host 127.0.0.1 --port 8000`
Dashboard: <http://127.0.0.1:8000/>

## 0:00 – Pre-demo checklist (before the clock starts)

- Backend running, dashboard open, language set to தமிழ்.
- One farmer registered (note the ID; form auto-fills it).
- One crop photo ready (JPG/PNG, under 10 MB).
- Service card shows AI: Ready (real key) — if it shows Not
  connected, the whole demo still works in mock; say so honestly.
- Backup tab: `/docs` in case you want to show an API response.

## 0:00–0:40 – Farmer asks in Tamil (AI chat, real mode)

1. Open AI Chat. Say: "A tomato farmer in Madurai has a problem."
2. Send: `என் தக்காளி இலைகளில் மஞ்சள் புள்ளிகள் உள்ளன. என்ன செய்ய வேண்டும்?`
3. Point out: reply arrives in Tamil, topic detected, safety note
   included, history saved (open Recent on the dashboard).

Fallback line: "If the network is slow, KrishiMitra labels the safe
fallback instead of guessing — you always see which mode answered."

## 0:40–1:20 – Crop photo analysis (real vision)

1. Open Crop Scan, upload the leaf photo, press Analyze.
2. Point out: observation in Tamil, possible issues marked as
   possibilities only, confidence shown, clearer-photo honesty,
   organic-first guidance, expert safety note.
3. Say: "It never claims a confirmed diagnosis from one photo."

## 1:20–2:10 – Rescue Plan form (structured AI plan)

1. Open Rescue Plan. Fill: crop Tomato, symptoms yellow spots,
   area 30%, 7 days, soil red, drip, Madurai, attach the photo.
2. Press Send report & get plan.
3. Point out: 8-part AI plan (issue, causes, confidence,
   explanation, organic treatment first, actions, prevention,
   expert referral) with the real-AI badge, plus safe steps,
   follow-up schedule (Day 1-2 / 3-4 / 7), and the shareable card
   link (open it — printable, works on a phone).

## 2:10–2:40 – Weather (real data) + mandi (honest)

1. Open Weather, city Madurai → real temperature, rain guidance.
   Say: "Live Open-Meteo data with farming precautions."
2. Open Mandi, crop Tomato → shows the honest unavailable message
   (or live prices if a data.gov.in key is configured).
   Say: "KrishiMitra never invents prices — it says so when the
   source is not configured."

## 2:40–3:00 – Close (English)

1. Dashboard service card: AI Ready, WhatsApp status honest.
2. Say: "Real Meta Muse Spark 1.3 for chat, vision, and rescue
   plans; Tamil, Hindi, English; 260 automated tests green; every
   answer labeled real, mock, or fallback. WhatsApp receiver is
   built and mock-verified — it goes live with Meta credentials."
3. End on the rescue card in Tamil.

## Emergency fallbacks

- API slow/down: answers arrive labeled fallback with safe generic
  guidance — present the badge as a feature ("never silent").
- No internet: chat, plan form, and card still demo in mock;
  weather correctly shows unavailable.
- WhatsApp: do NOT claim it is connected. Show the service card
  (Not connected) and the code-complete webhook instead.
