"""
Deduplication: Garmin-Schritte haben Priorität.
Google Fit wird nur als Fallback genutzt wenn Garmin keine Daten liefert
(z.B. Uhr nicht getragen).
"""
from typing import Optional


# Garmin gilt als "getragen" wenn > 500 Schritte erfasst wurden
_GARMIN_WORN_THRESHOLD = 500


def merge_steps(
    garmin_steps: Optional[int],
    gfit_steps: Optional[int],
) -> tuple[int, str]:
    """
    Gibt (schritte, quelle) zurück.
    Quelle ist 'garmin', 'google_fit' oder 'unbekannt'.
    """
    garmin = garmin_steps or 0
    gfit = gfit_steps or 0

    if garmin >= _GARMIN_WORN_THRESHOLD:
        return garmin, "garmin"

    if gfit > 0:
        return gfit, "google_fit"

    if garmin > 0:
        return garmin, "garmin"

    return 0, "unbekannt"


def garmin_was_worn(garmin_steps: Optional[int]) -> bool:
    return (garmin_steps or 0) >= _GARMIN_WORN_THRESHOLD
