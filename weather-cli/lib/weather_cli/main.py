"""
Weather CLI using Bright Sky API (German Weather Service / DWD data)
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

BRIGHTSKY_API = "https://api.brightsky.dev"
NOMINATIM_API = "https://nominatim.openstreetmap.org"

CONDITION_ICONS: dict[str, str] = {
    "dry": "☀️",
    "fog": "🌫️",
    "rain": "🌧️",
    "sleet": "🌨️",
    "snow": "❄️",
    "hail": "🧊",
    "thunderstorm": "⛈️",
}
DEFAULT_ICON = "🌤️"


@dataclass
class WeatherEntry:
    timestamp: datetime
    temperature: float | None
    apparent_temperature: float | None
    relative_humidity: float | None
    wind_speed: float | None
    wind_direction: float | None
    wind_gust_speed: float | None
    pressure_msl: float | None
    precipitation: float | None
    cloud_cover: float | None
    visibility: float | None
    condition: str

    @classmethod
    def from_api(cls, raw: dict[str, object]) -> "WeatherEntry":
        return cls(
            timestamp=datetime.fromisoformat(str(raw["timestamp"])),
            temperature=_float_or_none(raw.get("temperature")),
            apparent_temperature=_float_or_none(raw.get("apparent_temperature")),
            relative_humidity=_float_or_none(raw.get("relative_humidity")),
            wind_speed=_float_or_none(raw.get("wind_speed")),
            wind_direction=_float_or_none(raw.get("wind_direction")),
            wind_gust_speed=_float_or_none(raw.get("wind_gust_speed")),
            pressure_msl=_float_or_none(raw.get("pressure_msl")),
            precipitation=_float_or_none(raw.get("precipitation")),
            cloud_cover=_float_or_none(raw.get("cloud_cover")),
            visibility=_float_or_none(raw.get("visibility")),
            condition=str(raw.get("condition", "unknown")),
        )

    @property
    def icon(self) -> str:
        return CONDITION_ICONS.get(self.condition, DEFAULT_ICON)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


def _api_get(url: str, headers: dict[str, str] | None = None) -> object:
    """Fetch JSON from a URL. Only https URLs are permitted."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        msg = f"Only https URLs are allowed, got: {parsed.scheme}"
        raise ValueError(msg)
    request = Request(url, headers=headers or {})  # noqa: S310
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310
            return json.loads(response.read().decode())
    except (URLError, HTTPError) as e:
        msg = f"HTTP request failed: {url}: {e}"
        raise RuntimeError(msg) from e


def geocode_location(location: str) -> tuple[float, float, str]:
    """
    Geocode a location name to (lat, lon, display_name) using OpenStreetMap
    Nominatim.
    """
    params = urlencode(
        {
            "q": location,
            "format": "json",
            "limit": 1,
        }
    )
    url = f"{NOMINATIM_API}/search?{params}"
    headers = {"User-Agent": "weather-cli/1.0 (https://github.com/Mic92/mics-skills)"}

    data = _api_get(url, headers)
    if not isinstance(data, list) or not data:
        msg = f"Location not found: {location}"
        raise ValueError(msg)

    result = data[0]
    return (
        float(result["lat"]),
        float(result["lon"]),
        result.get("display_name", location),
    )


def get_weather(
    lat: float,
    lon: float,
    date_str: str | None = None,
    last_date: str | None = None,
) -> list[WeatherEntry]:
    """
    Get weather data from Bright Sky API, parsed into WeatherEntry objects.
    """
    params: dict[str, object] = {
        "lat": lat,
        "lon": lon,
        "date": date_str or datetime.now(tz=UTC).strftime("%Y-%m-%d"),
    }

    if last_date:
        params["last_date"] = last_date

    url = f"{BRIGHTSKY_API}/weather?{urlencode(params)}"
    data = _api_get(url)
    if not isinstance(data, dict):
        msg = "Unexpected API response format"
        raise TypeError(msg)

    return [WeatherEntry.from_api(entry) for entry in data.get("weather", [])]


def _find_closest_to_now(entries: list[WeatherEntry]) -> WeatherEntry:
    """Pick the observation closest to the current time."""
    now = datetime.now(tz=UTC)
    return min(entries, key=lambda e: abs((e.timestamp - now).total_seconds()))


def _fmt_optional(value: float | None, fmt: str, suffix: str) -> str | None:
    """Format a value with suffix, returning None if the value is missing."""
    if value is None:
        return None
    return f"{value:{fmt}}{suffix}"


def format_current_weather(entries: list[WeatherEntry], location: str) -> str:
    """Format the observation closest to now."""
    if not entries:
        return "No weather data available"

    current = _find_closest_to_now(entries)
    time_str = current.timestamp.strftime("%Y-%m-%d %H:%M %Z")

    lines = [
        f"\n{current.icon} Weather for {location}",
        "=" * 50,
        f"Time: {time_str}",
        f"Condition: {current.condition.capitalize()}",
    ]

    detail_lines = [
        _fmt_temp(current.temperature, current.apparent_temperature),
        _fmt_optional(current.relative_humidity, ".0f", "%"),
        _fmt_wind(current.wind_speed, current.wind_direction, current.wind_gust_speed),
        _fmt_optional(current.pressure_msl, ".0f", " hPa"),
        _fmt_optional(current.precipitation, ".1f", " mm"),
        _fmt_optional(current.cloud_cover, ".0f", "% cloud cover"),
        _fmt_visibility(current.visibility),
    ]

    labels = [
        "Temperature",
        "Humidity",
        "Wind",
        "Pressure",
        "Precipitation",
        "Cloud cover",
        "Visibility",
    ]

    for label, value in zip(labels, detail_lines, strict=True):
        if value is not None:
            lines.append(f"{label}: {value}")

    return "\n".join(lines)


def _fmt_temp(temp: float | None, feels_like: float | None) -> str | None:
    if temp is None:
        return None
    s = f"{temp:.1f}\u00b0C"
    if feels_like is not None:
        s += f" (feels like {feels_like:.1f}\u00b0C)"
    return s


def _fmt_wind(
    speed: float | None,
    direction: float | None,
    gust: float | None,
) -> str | None:
    if speed is None:
        return None
    s = f"{speed:.1f} km/h"
    if direction is not None:
        s += f" from {direction:.0f}\u00b0"
    if gust is not None:
        s += f" (gusts {gust:.1f} km/h)"
    return s


def _fmt_visibility(vis: float | None) -> str | None:
    if vis is None:
        return None
    if vis >= 1000:
        return f"{vis / 1000:.1f} km"
    return f"{vis:.0f} m"


def format_forecast(entries: list[WeatherEntry], location: str, days: int = 3) -> str:
    """Format a multi-day forecast summary."""
    if not entries:
        return "No forecast data available"

    lines = [f"\n\U0001f52e {days}-Day Forecast for {location}", "=" * 50]

    # Group by calendar date
    by_day: dict[str, list[WeatherEntry]] = {}
    for entry in entries:
        date_key = entry.timestamp.strftime("%Y-%m-%d")
        by_day.setdefault(date_key, []).append(entry)

    for date_key in sorted(by_day)[:days]:
        day_entries = by_day[date_key]

        temps = [e.temperature for e in day_entries if e.temperature is not None]
        if not temps:
            continue

        conditions = [e.condition for e in day_entries if e.condition]
        precip = sum(e.precipitation or 0 for e in day_entries)

        # Most common condition
        condition = (
            max(set(conditions), key=conditions.count) if conditions else "unknown"
        )
        icon = CONDITION_ICONS.get(condition, DEFAULT_ICON)

        day_str = date.fromisoformat(date_key).strftime("%a, %b %d")
        lines.append(
            f"\n{icon} {day_str}: {min(temps):.0f}\u00b0C - {max(temps):.0f}\u00b0C, "
            f"{condition.capitalize()}, {precip:.1f}mm precip"
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Weather CLI using Bright Sky API (DWD/MOSMIX, worldwide)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  weather-cli Berlin
  weather-cli Muenchen --forecast
  weather-cli "Garching bei Muenchen" --days 5
""",
    )

    parser.add_argument(
        "location",
        help="Location name (e.g., Berlin, London, New York)",
    )
    parser.add_argument(
        "-f",
        "--forecast",
        action="store_true",
        help="Show multi-day forecast instead of current weather",
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=3,
        help="Number of forecast days (default: 3)",
    )

    args = parser.parse_args()

    try:
        lat, lon, display_name = geocode_location(args.location)

        if args.forecast:
            today = datetime.now(tz=UTC)
            last_date = (today + timedelta(days=args.days)).strftime("%Y-%m-%d")
            entries = get_weather(lat, lon, last_date=last_date)
            print(format_forecast(entries, display_name, args.days))
        else:
            entries = get_weather(lat, lon)
            print(format_current_weather(entries, display_name))

    except (ValueError, RuntimeError, TypeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
