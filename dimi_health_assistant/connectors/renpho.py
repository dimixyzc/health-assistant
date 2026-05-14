import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def _make_client(email: str, password: str):
    from renpho import RenphoClient
    client = RenphoClient(email, password)
    client.login()
    return client


async def get_latest_measurement(email: str, password: str) -> Optional[dict]:
    """Holt die letzte Renpho-Körpermessung."""
    def _fetch():
        try:
            client = _make_client(email, password)
            measurements = client.get_all_measurements()
            if not measurements:
                return None
            return _parse_measurement(measurements[0])  # neueste zuerst
        except Exception as e:
            logger.error(f"Renpho Fehler: {e}")
            return None

    return await asyncio.to_thread(_fetch)


async def get_measurements_since(email: str, password: str, days: int = 30) -> list[dict]:
    """Holt Renpho-Messungen der letzten N Tage für Trendanalyse."""
    def _fetch():
        try:
            client = _make_client(email, password)
            measurements = client.get_all_measurements()
            if not measurements:
                return []
            cutoff = date.today() - timedelta(days=days)
            result = []
            for m in measurements:
                parsed = _parse_measurement(m)
                if parsed and parsed.get("date") and parsed["date"] >= cutoff.isoformat():
                    result.append(parsed)
            return sorted(result, key=lambda x: x["date"])
        except Exception as e:
            logger.error(f"Renpho Trend-Fehler: {e}")
            return []

    return await asyncio.to_thread(_fetch)


def _parse_measurement(m: dict) -> Optional[dict]:
    if not m:
        return None

    # Timestamp: Unix-Sekunden
    ts = m.get("timeStamp") or m.get("time_stamp") or m.get("timestamp") or ""
    if isinstance(ts, (int, float)) and ts > 0:
        from datetime import datetime
        ts = datetime.fromtimestamp(ts).date().isoformat()
    elif ts and "T" in str(ts):
        ts = str(ts)[:10]

    return {
        "date": str(ts)[:10] if ts else None,
        "weight_kg":        _f(m.get("weight")),
        "bmi":              _f(m.get("bmi")),
        "body_fat_pct":     _f(m.get("bodyfat")),
        "subfat_pct":       _f(m.get("subfat")),        # Unterhautfett %
        "visceral_fat":     _f(m.get("visfat")),        # Viszeralfett Level
        "muscle_mass_kg":   _f(m.get("muscle")),        # Muskelmasse kg
        "lean_mass_kg":     _f(m.get("sinew")),         # Fettfreie Masse kg
        "fat_free_weight_kg": _f(m.get("fatFreeWeight")),
        "bone_mass_kg":     _f(m.get("bone")),
        "body_water_pct":   _f(m.get("water")),
        "protein_pct":      _f(m.get("protein")),
        "bmr_kcal":         _f(m.get("bmr")),
        "metabolic_age":    _f(m.get("bodyage")),       # Körperalter
        "body_age":         _f(m.get("bodyage")),
    }


def _f(val) -> Optional[float]:
    try:
        return round(float(val), 2) if val is not None else None
    except (ValueError, TypeError):
        return None
