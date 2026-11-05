"""Weather info service (Phase 6 verification, Open-Meteo).

Real API, verified 2026-11-03 against official Open-Meteo docs:
- Geocoding: https://geocoding-api.open-meteo.com/v1/search
  (docs: https://open-meteo.com/en/docs/geocoding-api)
- Forecast: https://api.open-meteo.com/v1/forecast
  (docs: https://open-meteo.com/en/docs)
Free for non-commercial use, no API key needed, $0 cost.

Honesty rule: any failure (no network, bad response, unknown place)
returns status "unavailable" with an explanatory note. This module
never invents weather values. The WMO weather-code lookup below is a
static code table from the same docs, not live data.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
REQUEST_TIMEOUT = 15.0  # seconds per API call (Phase 6)

SUPPORTED_LANGUAGES = ("en", "ta", "hi")

# Safe fallback note. Always English so callers can match it; it keeps
# both "unavailable" (old checks) and the plain fallback sentence.
FALLBACK_NOTE = (
    "Weather data unavailable: weather not available, check local source."
)

# Farming guidance picked by simple rules from REAL numbers only.
# Keys: rain (rain now or soon), heat (very hot), wind (strong wind),
# clear (normal fieldwork). Translated, never invented advice.
GUIDANCE = {
    "en": {
        "rain": (
            "Rain is expected. Delay spraying and fertilizer; "
            "make sure field drains are open."
        ),
        "heat": (
            "Very hot weather. Give water early morning or evening; "
            "avoid midday field work."
        ),
        "wind": (
            "Strong wind. Do not spray chemicals today; "
            "they will drift away."
        ),
        "clear": (
            "No rain expected. Good time for normal field work; "
            "watch your crop daily."
        ),
    },
    "ta": {
        "rain": (
            "மழை எதிர்பார்க்கப்படுகிறது. மருந்து தெளிப்பதையும் "
            "உரமிடுவதையும் தள்ளிவையுங்கள்; வடிகால்களை திறந்து வையுங்கள்."
        ),
        "heat": (
            "மிகவும் வெப்பமாக உள்ளது. காலை அல்லது மாலையில் "
            "தண்ணீர் விடுங்கள்; நண்பகலில் வேலை செய்ய வேண்டாம்."
        ),
        "wind": (
            "பலத்த காற்று வீசுகிறது. இன்று மருந்து தெளிக்க வேண்டாம்; "
            "காற்றில் அடித்துச் செல்லும்."
        ),
        "clear": (
            "மழை எதிர்பார்க்கப்படவில்லை. வழக்கமான வயல் வேலைக்கு "
            "ஏற்ற நேரம்; தினமும் பயிரை கவனியுங்கள்."
        ),
    },
    "hi": {
        "rain": (
            "बारिश की संभावना है। छिड़काव और खाद रोकें; "
            "खेत की नालियां खुली रखें।"
        ),
        "heat": (
            "बहुत गर्मी है। सुबह या शाम को पानी दें; "
            "दोपहर में खेत का काम न करें।"
        ),
        "wind": (
            "तेज हवा चल रही है। आज दवा न छिड़कें; "
            "हवा में उड़ जाएगी।"
        ),
        "clear": (
            "बारिश की संभावना नहीं है। सामान्य खेत के काम के लिए "
            "अच्छा समय है; रोज फसल देखें।"
        ),
    },
}

# WMO weather codes (Open-Meteo docs) -> plain words. Lookup only.
WEATHER_CODE_TEXT = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "icy fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light showers",
    81: "showers",
    82: "heavy showers",
    85: "snow showers",
    86: "snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}


def _config() -> tuple[str, str]:
    """Read endpoint config fresh each call (env overrides for tests)."""
    forecast_url = (os.getenv("WEATHER_API_BASE_URL") or "").strip()
    geocode_url = (os.getenv("WEATHER_GEOCODE_URL") or "").strip()
    return forecast_url or DEFAULT_FORECAST_URL, geocode_url or DEFAULT_GEOCODE_URL


def describe_weather_code(code: object) -> str:
    """Plain words for a WMO weather code; 'unknown' when not a known code."""
    try:
        return WEATHER_CODE_TEXT.get(int(code), "unknown")  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "unknown"


def parse_geocode_response(data: object) -> tuple | None:
    """First match as (lat, lon, name, country); None when unusable."""
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    if not isinstance(first, dict):
        return None
    try:
        lat = float(first["latitude"])
        lon = float(first["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    name = first.get("name") or ""
    country = first.get("country") or ""
    return (lat, lon, str(name), str(country))


def parse_forecast_response(data: object) -> dict | None:
    """Current-weather block as plain values; None when unusable."""
    if not isinstance(data, dict):
        return None
    current = data.get("current")
    if not isinstance(current, dict):
        return None
    try:
        temperature = float(current["temperature_2m"])
    except (KeyError, TypeError, ValueError):
        return None

    def _num(key: str) -> float | None:
        try:
            return float(current[key])
        except (KeyError, TypeError, ValueError):
            return None

    code = current.get("weather_code")
    return {
        "temperature_c": temperature,
        "feels_like_c": _num("apparent_temperature"),
        "humidity_pct": _num("relative_humidity_2m"),
        "precipitation_mm": _num("precipitation"),
        "wind_kph": _num("wind_speed_10m"),
        "weather_code": code if isinstance(code, int) else None,
        "condition": describe_weather_code(code),
        "observed_at": current.get("time") if isinstance(current.get("time"), str) else None,
    }


def parse_daily_response(data: object) -> list:
    """Daily forecast rows from Open-Meteo; [] when missing or unusable.

    Documented shape: {"daily": {"time": [...], "temperature_2m_max": [...],
    "temperature_2m_min": [...], "precipitation_sum": [...], ...}}.
    Never raises; bad rows are skipped, never invented.
    """
    if not isinstance(data, dict):
        return []
    daily = data.get("daily")
    if not isinstance(daily, dict):
        return []
    times = daily.get("time")
    if not isinstance(times, list) or not times:
        return []
    highs = daily.get("temperature_2m_max")
    lows = daily.get("temperature_2m_min")
    rains = daily.get("precipitation_sum")
    codes = daily.get("weather_code", daily.get("weathercode"))
    rows = []
    for i, day in enumerate(times):
        if not isinstance(day, str):
            continue
        row = {"date": day}

        def _at(values: object) -> float | None:
            if not isinstance(values, list) or i >= len(values):
                return None
            try:
                return float(values[i])
            except (TypeError, ValueError):
                return None

        row["temp_max_c"] = _at(highs)
        row["temp_min_c"] = _at(lows)
        row["rain_mm"] = _at(rains)
        code = None
        if isinstance(codes, list) and i < len(codes) and isinstance(codes[i], int):
            code = codes[i]
        row["weather_code"] = code
        row["condition"] = describe_weather_code(code)
        rows.append(row)
    return rows


def _clean_language(language: str | None) -> str:
    """Keep only en/ta/hi; anything else becomes English."""
    return language if language in SUPPORTED_LANGUAGES else "en"


def farming_guidance(
    current: dict, daily: list, language: str = "en"
) -> str:
    """Pick safe guidance from REAL numbers only, in ta/hi/en.

    Rules: rain now or soon -> rain advice; else max heat >= 38C ->
    heat advice; else wind >= 40 kph -> wind advice; else normal
    fieldwork. Never invents values; it only reads what the API gave.
    """
    lang = _clean_language(language)
    try:
        rain_now = float(current.get("precipitation_mm") or 0.0)
    except (TypeError, ValueError):
        rain_now = 0.0
    try:
        wind = float(current.get("wind_kph") or 0.0)
    except (TypeError, ValueError):
        wind = 0.0
    day_max = None
    day_rain = 0.0
    for row in daily or []:
        if not isinstance(row, dict):
            continue
        try:
            if row.get("temp_max_c") is not None:
                value = float(row["temp_max_c"])
                day_max = value if day_max is None else max(day_max, value)
        except (TypeError, ValueError, KeyError):
            pass
        try:
            if row.get("rain_mm") is not None:
                day_rain = max(day_rain, float(row["rain_mm"]))
        except (TypeError, ValueError, KeyError):
            pass
    if rain_now > 0 or day_rain > 2:
        key = "rain"
    elif day_max is not None and day_max >= 38:
        key = "heat"
    elif wind >= 40:
        key = "wind"
    else:
        key = "clear"
    return GUIDANCE[lang][key]


def _unavailable(location: str, reason: str | None = None) -> dict:
    """Honest 'data unavailable' result. No values invented."""
    return {
        "status": "unavailable",
        "location": location,
        "note": reason or FALLBACK_NOTE,
    }


def _fetch_forecast(lat: float, lon: float) -> tuple[dict | None, list]:
    """Current + daily forecast for coords. (None, []) when unusable."""
    forecast_url, _ = _config()
    fc_resp = httpx.get(
        forecast_url,
        params={
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,weather_code,wind_speed_10m"
            ),
            "daily": (
                "temperature_2m_max,temperature_2m_min,"
                "precipitation_sum,weather_code"
            ),
            "timezone": "auto",
        },
        timeout=REQUEST_TIMEOUT,
    )
    fc_resp.raise_for_status()
    data = fc_resp.json()
    return parse_forecast_response(data), parse_daily_response(data)


def _ok_result(
    place: str,
    resolved_name: str,
    country: str,
    current: dict,
    daily: list,
    language: str,
) -> dict:
    """Success body: source, UTC timestamp, current, daily, guidance."""
    stamp = datetime.now(timezone.utc).isoformat(timespec="minutes")
    return {
        "status": "ok",
        "location": place,
        "resolved_name": resolved_name or place,
        "country": country,
        "source": "open-meteo",
        "fetched_at": stamp,
        "timestamp": stamp,
        "language": _clean_language(language),
        **current,
        "daily": daily,
        "guidance": farming_guidance(current, daily, language),
    }


def get_weather(location: str, language: str = "en") -> dict:
    """Real weather for a place name, or an honest 'unavailable' result."""
    place = (location or "").strip()
    if not place:
        return _unavailable(location, "Weather data unavailable: empty location.")
    _, geocode_url = _config()
    try:
        geo_resp = httpx.get(
            geocode_url,
            params={"name": place, "count": 1, "language": "en", "format": "json"},
            timeout=REQUEST_TIMEOUT,
        )
        geo_resp.raise_for_status()
        geo = parse_geocode_response(geo_resp.json())
        if geo is None:
            return _unavailable(place, "Weather data unavailable: place not found.")
        lat, lon, resolved_name, country = geo
        current, daily = _fetch_forecast(lat, lon)
        if current is None:
            return _unavailable(place)
    except (httpx.HTTPError, ValueError):
        return _unavailable(place)
    return _ok_result(place, resolved_name, country, current, daily, language)


def get_weather_by_coords(
    lat: float, lon: float, language: str = "en"
) -> dict:
    """Real weather for lat/lon (no geocode call), or 'unavailable'."""
    place = f"{lat},{lon}"
    try:
        current, daily = _fetch_forecast(float(lat), float(lon))
        if current is None:
            return _unavailable(place)
    except (httpx.HTTPError, ValueError, TypeError):
        return _unavailable(place)
    return _ok_result(place, place, "", current, daily, language)
