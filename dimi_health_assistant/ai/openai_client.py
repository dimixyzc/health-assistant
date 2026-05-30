import logging
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

def _hm(minutes) -> str:
    """Konvertiert Minuten zu 'Xh Ymin' — nie rohe Minuten wenn >= 60."""
    if not minutes:
        return "k.A."
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return "k.A."
    h, mins = divmod(m, 60)
    return f"{h}h {mins}min" if h else f"{mins}min"


_ATHLETE_PROFILE = """
Du bist ein persönlicher Fitness-Assistent für Dimitri, einen Hybrid-Athleten.
Trainingsziel: 3x pro Woche Krafttraining im Gym + 3x Laufen pro Woche.
Dimitri ist sportlich aktiv, verfolgt seine Daten mit einer Garmin-Uhr und einer Renpho-Waage.

AUSGABEFORMAT — immer einhalten:
- Antworte auf Deutsch
- Kein Fließtext — stattdessen strukturierte Bullet-Points (•)
- Jeder Bullet beginnt mit einem passenden Emoji zur schnellen Einordnung
- Emojis als Status-Signale: ✅ gut/erreicht, ⚠️ Achtung, 🔴 kritisch, 💡 Tipp, 📈 Trend positiv, 📉 Trend negativ
- Maximal 2–4 Bullets pro Antwort
- Keine langen Sätze — prägnant, direkt, umsetzbar
- Keine Einleitung, kein Abschluss-Satz wie "Viel Erfolg!" — nur die Bullets
- Wiederhole keine Rohdatenliste, wenn die Daten separat formatiert werden
- Schlaf NIEMALS in Minuten angeben — immer als "Xh Ymin" (z.B. "1h 45min" statt "105 Min")
"""


class OpenAIHealthAssistant:
    def __init__(self, api_key: str, model: str = "gpt-5.5"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate_morning_briefing(self, snapshot: dict) -> str:
        readiness = snapshot.get("readiness") or {}
        prompt = f"""
Morgen-Briefing — bewerte Erholung und gib 1 konkreten Trainingstipp für heute.

Readiness: {readiness.get('score', 'k.A.')}/100 ({readiness.get('recommendation', 'k.A.')})
Limitierende Faktoren: {', '.join(readiness.get('limiting_factors') or []) or 'k.A.'}
Schlaf: {_hm(snapshot.get('sleep_duration_minutes'))}, Score: {snapshot.get('sleep_score', 'k.A.')}
Tiefschlaf: {_hm(snapshot.get('deep_sleep_minutes'))} | REM: {_hm(snapshot.get('rem_sleep_minutes'))}
HRV: {snapshot.get('avg_hrv', 'k.A.')} ms ({snapshot.get('hrv_status', 'k.A.')})
Body Battery: {snapshot.get('body_battery', 'k.A.')} | Ruhe-Puls: {snapshot.get('resting_hr', 'k.A.')} bpm

Format: 2 Bullets — 1 kurze Einordnung, 1 konkrete Trainingsempfehlung. Keine Wiederholung aller Rohwerte.
"""
        return await self._chat(prompt)

    async def generate_evening_summary(self, snapshot: dict, activities: list) -> str:
        activity_lines = "\n".join(
            f"- {a.get('type', '?')}: {a.get('duration_minutes')} Min, {a.get('distance_km', 0)} km, HR: {a.get('avg_hr', '?')} bpm"
            for a in activities
        ) or "Keine Aktivitäten heute"

        prompt = f"""
Tages-Zusammenfassung — bewerte den Tag und gib 1 Tipp für morgen.

Schritte: {snapshot.get('steps', 0)} | Aktive Min: {snapshot.get('active_minutes', 0)}
Kalorien: {snapshot.get('calories', 0)} kcal | Stress: {snapshot.get('avg_stress', 'k.A.')}
Body Battery: {snapshot.get('body_battery', 'k.A.')}

Aktivitäten:
{activity_lines}

Format: 2 Bullets — Tagesbewertung + 1 konkreter Ausblick für morgen. Keine Rohdatenliste.
"""
        return await self._chat(prompt)

    async def generate_weekly_summary(self, weekly: dict) -> str:
        w_available = weekly.get('weight_available', False)
        weight_section = f"""
KÖRPERKOMPOSITION (letzte 30 Tage):
Gewicht: {weekly.get('latest_weight')} kg ({_delta_str(weekly.get('weight_delta'))} kg Trend)
Körperfett: {weekly.get('latest_body_fat')} % ({_delta_str(weekly.get('fat_delta'))} %)
Muskelmasse: {weekly.get('latest_muscle_mass')} kg ({_delta_str(weekly.get('muscle_delta'))} kg)
Unterhautfett: {weekly.get('latest_subfat')} % · Viszeralfett Level: {weekly.get('latest_visceral_fat')}
Protein: {weekly.get('latest_protein')} % · Körperalter: {weekly.get('latest_metabolic_age')} Jahre
""" if w_available else "\nKÖRPERKOMPOSITION: Keine Renpho-Daten diese Woche.\n"

        prompt = f"""
Erstelle eine strukturierte wöchentliche Trainings-, Schlaf- und Körperkompositions-Zusammenfassung:

📅 Woche: {weekly.get('week_start')} bis {weekly.get('week_end')}

TRAINING:
Gym-Einheiten: {weekly.get('gym_days')} (Ziel: 3)
Lauf-Einheiten: {weekly.get('run_days')} (Ziel: 3)
Gesamtdistanz: {weekly.get('total_distance_km')} km
Trainingsdauer: {_hm(weekly.get('total_duration_minutes'))}
Kalorien (Training): {weekly.get('total_calories_burned')} kcal
Training Load: {weekly.get('total_load', 'k.A.')}
Fitness/Fatigue/Form: {(weekly.get('training_trend') or {}).get('fitness', 'k.A.')} / {(weekly.get('training_trend') or {}).get('fatigue', 'k.A.')} / {(weekly.get('training_trend') or {}).get('form', 'k.A.')}

SCHLAF (Wochendurchschnitt):
Schlafdauer: {_hm(weekly.get('avg_sleep_minutes'))}
Schlaf-Score: {weekly.get('avg_sleep_score', 'k.A.')}
Tiefschlaf: {_hm(weekly.get('avg_deep_sleep_minutes'))}
REM-Schlaf: {_hm(weekly.get('avg_rem_sleep_minutes'))}

ERHOLUNG (aktuell):
HRV: {weekly.get('today_hrv', 'k.A.')} ms
Body Battery: {weekly.get('today_body_battery', 'k.A.')}
Ruhe-Puls: {weekly.get('today_resting_hr', 'k.A.')} bpm
{weight_section}
Format: 3 Bullets — 1 Wochenfazit, 1 stärkster Hebel, 1 konkrete Empfehlung für nächste Woche.
Keine Wiederholung der Rohdaten, die kommen separat im Statistikblock.

Setze die Werte in Perspektive für einen Hybrid-Athleten (3x Gym + 3x Laufen/Woche).
"""
        return await self._chat(prompt)

    async def generate_weight_insight(self, trend: dict) -> str:
        if not trend.get("available"):
            return "📊 Keine Renpho-Daten vorhanden. Bitte wiege dich!"

        prompt = f"""
Analysiere diese Körperkompositions-Daten der letzten {trend.get('period_days')} Tage:

GEWICHT & BMI:
Gewicht: {trend.get('latest_weight')} kg ({_delta_str(trend.get('weight_delta'))} kg Trend)
BMI: {trend.get('latest_bmi')}

KÖRPERFETT:
Gesamtkörperfett: {trend.get('latest_body_fat')} % ({_delta_str(trend.get('fat_delta'))} % Trend)
Unterhautfett: {trend.get('latest_subfat')} %
Viszeralfett Level: {trend.get('latest_visceral_fat')}

MUSKELN & MASSE:
Muskelmasse: {trend.get('latest_muscle_mass')} kg ({_delta_str(trend.get('muscle_delta'))} kg Trend)
Fettfreie Masse: {trend.get('latest_lean_mass')} kg
Fettfreies Gewicht: {trend.get('latest_fat_free_weight')} kg
Knochenmasse: {trend.get('latest_bone_mass')} kg

STOFFWECHSEL & WEITERE:
Körperwasser: {trend.get('latest_body_water')} %
Protein: {trend.get('latest_protein')} %
Grundumsatz (BMR): {trend.get('latest_bmr')} kcal
Körperalter: {trend.get('latest_metabolic_age')} Jahre

Anzahl Messungen: {trend.get('measurements_count')} in {trend.get('period_days')} Tagen

Format: 2-3 Bullets — Trend-Einordnung + 1 konkreter Tipp. Keine Wiederholung der Rohdatenliste.
"""
        return await self._chat(prompt)

    async def answer_free_question(
        self, question: str, snapshot: dict, activities: list, weight_trend: dict | None = None
    ) -> str:
        recent = "\n".join(
            f"- {a.get('start_time', '')[:10]} | {a.get('name', a.get('type', '?'))} | "
            f"{a.get('duration_minutes')} Min | {a.get('distance_km', 0)} km | "
            f"Ø HR: {a.get('avg_hr', '?')} bpm | Pace: {a.get('avg_pace_min_km', '?')} min/km | "
            f"SPM: {a.get('avg_spm', '?')} | +{a.get('elevation_gain_m', 0)} m"
            for a in activities[:10]
        ) or "Keine Aktivitäten verfügbar"

        wt = weight_trend or {}
        if wt.get("available"):
            weight_section = f"""
RENPHO KÖRPERKOMPOSITION (letzte 30 Tage):
Gewicht: {wt.get('latest_weight')} kg ({_delta_str(wt.get('weight_delta'))} kg Trend)
BMI: {wt.get('latest_bmi')}
Körperfett gesamt: {wt.get('latest_body_fat')} % ({_delta_str(wt.get('fat_delta'))} %)
Unterhautfett: {wt.get('latest_subfat')} % · Viszeralfett Level: {wt.get('latest_visceral_fat')}
Muskelmasse: {wt.get('latest_muscle_mass')} kg ({_delta_str(wt.get('muscle_delta'))} kg)
Fettfreie Masse: {wt.get('latest_lean_mass')} kg · Fettfreies Gewicht: {wt.get('latest_fat_free_weight')} kg
Körperwasser: {wt.get('latest_body_water')} % · Protein: {wt.get('latest_protein')} %
Knochenmasse: {wt.get('latest_bone_mass')} kg · BMR: {wt.get('latest_bmr')} kcal
Körperalter: {wt.get('latest_metabolic_age')} Jahre
Messungen: {wt.get('measurements_count')} in 30 Tagen · Letzte: {wt.get('latest_date')}"""
        else:
            weight_section = "\nRENPHO: Keine Daten verfügbar."

        prompt = f"""
Beantworte diese Frage von Dimitri basierend auf seinen aktuellen Gesundheits- und Trainingsdaten:

FRAGE: {question}

AKTUELLE DATEN (heute):
Schlaf: {_hm(snapshot.get('sleep_duration_minutes'))}, Score: {snapshot.get('sleep_score', 'k.A.')}
HRV: {snapshot.get('avg_hrv', 'k.A.')} ms ({snapshot.get('hrv_status', 'k.A.')})
Body Battery: {snapshot.get('body_battery', 'k.A.')}
Ruhe-Puls: {snapshot.get('resting_hr', 'k.A.')} bpm
Schritte: {snapshot.get('steps', 0)}
{weight_section}

LETZTE AKTIVITÄTEN:
{recent}

Format: Bullets — beantworte die Frage direkt, nutze die Daten zur Einordnung.
"""
        return await self._chat(prompt)

    async def generate_training_tip(self, snapshot: dict, recent_activities: list) -> str:
        recent_types = [a.get("type") for a in recent_activities[:5]]
        readiness = snapshot.get("readiness") or {}
        prompt = f"""
Gib einen konkreten Trainingstipp basierend auf:

Aktuelle Erholung:
- Readiness: {readiness.get('score', 'k.A.')}/100 ({readiness.get('recommendation', 'k.A.')})
- Body Battery: {snapshot.get('body_battery', 'k.A.')}
- HRV: {snapshot.get('avg_hrv', 'k.A.')} ms (Status: {snapshot.get('hrv_status', 'k.A.')})
- Training Readiness: {snapshot.get('training_readiness_score', 'k.A.')}
- Ruhe-Puls: {snapshot.get('resting_hr', 'k.A.')} bpm

Letzte 5 Aktivitäten: {', '.join(str(t) for t in recent_types)}

Trainingsziel: 3x Gym + 3x Laufen pro Woche als Hybrid-Athlet.
Format: 3-4 Bullets — 1 Erholungs-Status, dann 2-3 spezifische, umsetzbare Tipps.
"""
        return await self._chat(prompt)

    async def _chat(self, user_message: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _ATHLETE_PROFILE},
                    {"role": "user", "content": user_message},
                ],
                max_completion_tokens=10000,
            )
            choice = response.choices[0]
            content = choice.message.content
            # gpt-5.5 kann refusal oder leeren content liefern
            refusal = getattr(choice.message, "refusal", None)
            logger.debug(f"OpenAI content: {repr(content)} | refusal: {repr(refusal)} | finish: {choice.finish_reason}")
            if refusal:
                logger.warning(f"OpenAI refusal: {refusal}")
                return ""
            if not content:
                logger.warning(f"OpenAI returned empty content (finish_reason={choice.finish_reason})")
                return ""
            return content.strip()
        except Exception as e:
            logger.error(f"OpenAI Fehler: {e}", exc_info=True)
            return ""


def _delta_str(delta: Optional[float]) -> str:
    if delta is None:
        return "k.A."
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta}"
