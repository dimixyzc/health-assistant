"""
Deduplication: nimmt immer den höheren Schrittwert aus Garmin oder Google Fit.
Garmin kann durch unvollständigen Sync niedriger sein — Google Fit zählt
zusätzlich Telefon-Schritte und ist oft aktueller.
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
    Wenn beide Quellen Daten haben → höheren Wert nehmen.
    Quelle ist 'garmin', 'google_fit' oder 'unbekannt'.
    """
    garmin = garmin_steps or 0
    gfit = gfit_steps or 0

    if garmin > 0 and gfit > 0:
        if gfit > garmin:
            return gfit, "google_fit"
        return garmin, "garmin"

    if garmin >= _GARMIN_WORN_THRESHOLD:
        return garmin, "garmin"

    if gfit > 0:
        return gfit, "google_fit"

    if garmin > 0:
        return garmin, "garmin"

    return 0, "unbekannt"


def garmin_was_worn(garmin_steps: Optional[int]) -> bool:
    return (garmin_steps or 0) >= _GARMIN_WORN_THRESHOLD
